from __future__ import annotations

import asyncio
import logging
import secrets
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import WebSocket

from app.quiz.schemas import Question
from app.scoring.scoring import points_for_answer

log = logging.getLogger(__name__)

CLOSE_BAD_REQUEST = 4400
CLOSE_UNAUTHORIZED = 4401
CLOSE_KICKED = 4403
CLOSE_NOT_FOUND = 4404
CLOSE_EXPIRED = 4408  # party usunięte przez sprzątanie
CLOSE_REPLACED = 4409


class PartyState(str, Enum):
    LOBBY = "lobby"
    QUESTION = "question"
    REVEAL = "reveal"
    GAME_OVER = "game_over"


class PartyError(Exception):
    pass


def message(type_: str, **data: Any) -> Dict[str, Any]:
    return {"type": type_, "data": data}


def clean_nick(raw: str) -> str:
    """Usuwa znaki sterujące i niewidoczne (np. zero-width) oraz zbędne spacje."""
    visible = "".join(ch for ch in unicodedata.normalize("NFC", raw)
                      if unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cs"))
    return " ".join(visible.split())


@dataclass
class Answer:
    choice: int
    elapsed: float
    points: int = 0


@dataclass
class Player:
    id: str
    nick: str
    reconnect_token: str
    ws: Optional[WebSocket] = None
    score: int = 0
    streak: int = 0
    user_id: Optional[int] = None  # None = gość bez konta

    @property
    def connected(self) -> bool:
        return self.ws is not None

    def public(self) -> Dict[str, Any]:
        return {"id": self.id, "nick": self.nick, "score": self.score, "connected": self.connected}


@dataclass
class Party:
    code: str
    host_token: str
    questions: List[Question]
    max_players: int = 50
    max_nick_length: int = 20
    quiz_id: Optional[str] = None  # None = przykładowy quiz
    title: str = "Przykładowy quiz"
    host_user_id: Optional[int] = None
    # Wołane po końcu gry (zapis wyników do bazy); party nie wie nic o bazie
    on_finish: Optional[Callable[[Party], Awaitable[None]]] = None

    state: PartyState = PartyState.LOBBY
    players: Dict[str, Player] = field(default_factory=dict)
    host_ws: Optional[WebSocket] = None
    current_index: int = -1
    question_started_at: float = 0.0
    started_at: Optional[datetime] = None
    answers: Dict[str, Answer] = field(default_factory=dict)  # answers to the current question
    history: List[Dict[str, Answer]] = field(default_factory=list)  # answers to finished questions
    question_stats: List[Dict[str, Any]] = field(default_factory=list)  # statystyki zakończonych pytań
    # Ostatnio wysłane komunikaty — do odtworzenia ekranu po ponownym połączeniu
    _last_reveal_host: Optional[Dict[str, Any]] = None
    _last_reveal_players: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _game_over_msg: Optional[Dict[str, Any]] = None
    _timer: Optional[asyncio.Task] = None
    # Do sprzątania (czas z time.monotonic): od kiedy nikt nie jest połączony, kiedy gra się skończyła
    created_at: float = field(default_factory=time.monotonic)
    idle_since: Optional[float] = field(default_factory=time.monotonic)
    finished_at: Optional[float] = None

    # ---------- helpers ----------

    @property
    def current_question(self) -> Optional[Question]:
        if 0 <= self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None

    @property
    def joinable(self) -> bool:
        return self.state == PartyState.LOBBY and len(self.players) < self.max_players

    def leaderboard(self) -> List[Dict[str, Any]]:
        ranked = sorted(self.players.values(), key=lambda p: p.score, reverse=True)
        return [{"rank": i + 1, **p.public()} for i, p in enumerate(ranked)]

    @property
    def has_connections(self) -> bool:
        return self.host_ws is not None or any(p.connected for p in self.players.values())

    def _update_idle(self) -> None:
        if self.has_connections:
            self.idle_since = None
        elif self.idle_since is None:
            self.idle_since = time.monotonic()

    def is_expired(self, now: float, idle_ttl: float, finished_ttl: float, max_age: float) -> bool:
        """Czy party można już usunąć z pamięci."""
        if now - self.created_at > max_age:
            return True
        if self.finished_at is not None and now - self.finished_at > finished_ttl:
            return True
        return self.idle_since is not None and now - self.idle_since > idle_ttl

    async def close_all(self, code: int, reason: str) -> None:
        """Zamyka wszystkie połączenia (przy usuwaniu party)."""
        sockets = [self.host_ws] + [p.ws for p in self.players.values()]
        await asyncio.gather(*(self._close(ws, code, reason) for ws in sockets if ws is not None))

    def summary(self) -> Dict[str, Any]:
        """Publiczny podgląd party (bez tokenów i odpowiedzi) — np. dla strony dołączania po skanie QR."""
        return {
            "code": self.code,
            "title": self.title,
            "state": self.state.value,
            "joinable": self.joinable,
            "player_count": len(self.players),
            "max_players": self.max_players,
            "players": [{"nick": p.nick, "connected": p.connected} for p in self.players.values()],
            "question_count": len(self.questions),
            "current_question": self.current_index + 1 if self.state in (PartyState.QUESTION, PartyState.REVEAL) else None,
            "host_connected": self.host_ws is not None,
        }

    async def _send(self, ws: Optional[WebSocket], msg: Dict[str, Any]) -> None:
        if ws is None:
            return
        try:
            await ws.send_json(msg)
        except Exception:  # client vanished mid-send; its own handler will clean up
            log.debug("send failed", exc_info=True)

    async def send_host(self, msg: Dict[str, Any]) -> None:
        await self._send(self.host_ws, msg)

    async def broadcast_players(self, msg: Dict[str, Any]) -> None:
        await asyncio.gather(*(self._send(p.ws, msg) for p in self.players.values()))

    async def broadcast(self, msg: Dict[str, Any]) -> None:
        await asyncio.gather(self.send_host(msg), self.broadcast_players(msg))

    async def broadcast_lobby(self) -> None:
        await self.broadcast(message("lobby_update", players=[p.public() for p in self.players.values()]))

    # ---------- connections ----------

    async def attach_host(self, ws: WebSocket) -> None:
        if self.host_ws is not None:
            await self._close(self.host_ws, CLOSE_REPLACED, "Host connected from another device")
        self.host_ws = ws
        self._update_idle()
        await self.send_host(message("host_joined", **self.summary()))
        await self.send_host(message("lobby_update", players=[p.public() for p in self.players.values()]))
        if self.state == PartyState.QUESTION:
            await self.send_host(self._question_message())
            await self.send_host(message("answer_count", answered=len(self.answers), total=self._active_player_count()))
        elif self.state == PartyState.REVEAL:
            await self.send_host(self._last_reveal_host)
        elif self.state == PartyState.GAME_OVER:
            await self.send_host(self._game_over_msg)

    async def detach_host(self, ws: WebSocket) -> None:
        # The party keeps running; the host can reconnect with the same token.
        if self.host_ws is ws:
            self.host_ws = None
            self._update_idle()

    def join(self, nick: str, reconnect_token: Optional[str], user_id: Optional[int] = None) -> Player:
        """Find the player for a reconnect token (or logged-in user), or register a new one."""
        if reconnect_token:
            for p in self.players.values():
                if secrets.compare_digest(p.reconnect_token, reconnect_token):
                    return p
            raise PartyError("Invalid reconnect token")
        if user_id is not None:
            # zalogowany gracz wraca na swoje miejsce także bez reconnect_token (np. z innego urządzenia)
            for p in self.players.values():
                if p.user_id == user_id:
                    return p

        nick = clean_nick(nick)
        if not nick:
            raise PartyError("Nick is required")
        if len(nick) > self.max_nick_length:
            raise PartyError(f"Nick can be at most {self.max_nick_length} characters")
        if self.state != PartyState.LOBBY:
            raise PartyError("Game already started")
        if len(self.players) >= self.max_players:
            raise PartyError("Party is full")
        if any(p.nick.casefold() == nick.casefold() for p in self.players.values()):
            raise PartyError("Nick already taken")

        player = Player(id=secrets.token_hex(4), nick=nick, reconnect_token=secrets.token_urlsafe(16), user_id=user_id)
        self.players[player.id] = player
        return player

    async def attach_player(self, player: Player, ws: WebSocket) -> None:
        if player.ws is not None:
            await self._close(player.ws, CLOSE_REPLACED, "Connected from another device")
        player.ws = ws
        self._update_idle()
        await self._send(ws, message(
            "joined",
            player_id=player.id,
            nick=player.nick,
            reconnect_token=player.reconnect_token,
            score=player.score,
            state=self.state.value,
        ))
        await self._send_current_screen(player, ws)
        await self.broadcast_lobby()

    async def _send_current_screen(self, player: Player, ws: WebSocket) -> None:
        """Po ponownym połączeniu gracz dostaje to, co widzą inni — nie pusty ekran."""
        if self.state == PartyState.QUESTION:
            if player.id in self.answers:
                await self._send(ws, message("answer_ack", question_id=self.current_question.id))
            else:
                await self._send(ws, self._question_message())
        elif self.state == PartyState.REVEAL and player.id in self._last_reveal_players:
            await self._send(ws, self._last_reveal_players[player.id])
        elif self.state == PartyState.GAME_OVER:
            await self._send(ws, self._game_over_msg)

    async def detach_player(self, player: Player, ws: WebSocket) -> None:
        if player.ws is not ws:  # already replaced by a newer connection
            return
        player.ws = None
        self._update_idle()
        # A dropped phone doesn't end the question: it may reconnect before the timer runs out.
        await self.broadcast_lobby()

    async def kick(self, player_id: str) -> None:
        player = self.players.pop(player_id, None)
        if player is None:
            return
        self.answers.pop(player_id, None)
        if player.ws is not None:
            ws, player.ws = player.ws, None
            await self._send(ws, message("kicked"))
            await self._close(ws, CLOSE_KICKED, "Kicked by host")
        self._update_idle()
        await self.broadcast_lobby()
        await self._maybe_reveal_early()

    async def _close(self, ws: WebSocket, code: int, reason: str) -> None:
        try:
            await ws.close(code=code, reason=reason)
        except Exception:
            pass

    # ---------- game flow ----------

    async def start(self) -> None:
        if self.state != PartyState.LOBBY:
            raise PartyError("Game already started")
        if not self.players:
            raise PartyError("Need at least one player")
        self.started_at = datetime.now(timezone.utc)
        await self._next_question()

    async def next(self) -> None:
        """Host's "next" button: skip to reveal during a question, or advance after reveal."""
        if self.state == PartyState.QUESTION:
            await self.reveal()
        elif self.state == PartyState.REVEAL:
            await self._next_question()
        else:
            raise PartyError(f"Cannot go to next question in state {self.state.value}")

    async def _next_question(self) -> None:
        self.current_index += 1
        if self.current_index >= len(self.questions):
            await self._game_over()
            return
        self.state = PartyState.QUESTION
        self.answers = {}
        self.question_started_at = time.monotonic()
        self._timer = asyncio.create_task(self._question_timer(self.current_index))
        await self.broadcast(self._question_message())

    def _question_message(self) -> Dict[str, Any]:
        q = self.current_question
        assert q is not None
        elapsed = time.monotonic() - self.question_started_at
        # Never include q.correct here — this goes to the players.
        return message(
            "question",
            question_id=q.id,
            index=self.current_index,
            total=len(self.questions),
            text=q.text,
            choices=q.choices,
            time_limit=q.time_limit,
            time_left=max(0.0, round(q.time_limit - elapsed, 1)),
        )

    async def _question_timer(self, index: int) -> None:
        q = self.questions[index]
        await asyncio.sleep(q.time_limit)
        if self.state == PartyState.QUESTION and self.current_index == index:
            await self.reveal()

    async def submit_answer(self, player: Player, question_id: Any, choice: Any) -> None:
        q = self.current_question
        if self.state != PartyState.QUESTION or q is None or question_id != q.id:
            raise PartyError("Question is not open")
        if player.id in self.answers:
            raise PartyError("Already answered")  # only the first answer counts
        if not isinstance(choice, int) or isinstance(choice, bool) or not 0 <= choice < len(q.choices):
            raise PartyError("Invalid choice")

        elapsed = time.monotonic() - self.question_started_at
        self.answers[player.id] = Answer(choice=choice, elapsed=elapsed)
        await self._send(player.ws, message("answer_ack", question_id=q.id))
        await self.send_host(message("answer_count", answered=len(self.answers), total=self._active_player_count()))
        await self._maybe_reveal_early()

    def _active_player_count(self) -> int:
        return sum(1 for p in self.players.values() if p.connected)

    async def _maybe_reveal_early(self) -> None:
        if self.state != PartyState.QUESTION:
            return
        connected = [p for p in self.players.values() if p.connected]
        if connected and all(p.id in self.answers for p in connected):
            await self.reveal()

    async def reveal(self) -> None:
        if self.state != PartyState.QUESTION:
            return
        self.state = PartyState.REVEAL
        if self._timer is not None and self._timer is not asyncio.current_task():
            self._timer.cancel()
        self._timer = None

        q = self.current_question
        assert q is not None
        for player in self.players.values():
            answer = self.answers.get(player.id)
            correct = answer is not None and answer.choice == q.correct
            if answer is not None:
                answer.points = points_for_answer(correct, answer.elapsed, q.time_limit, player.streak)
                player.score += answer.points
            player.streak = player.streak + 1 if correct else 0
        self.history.append(self.answers)

        stats = self._compute_question_stats(q)
        self.question_stats.append(stats)
        leaderboard = self.leaderboard()
        common = {
            "question_id": q.id,
            "correct": q.correct,
            "explanation": q.explanation,
            "hint": q.hint,
            "choice_counts": stats["choice_counts"],
            "stats": {k: stats[k] for k in ("answered", "players", "correct_count", "correct_ratio",
                                            "avg_time_ms", "fastest")},
            "is_last": self.current_index == len(self.questions) - 1,
        }

        self._last_reveal_host = message("reveal", **common, leaderboard=leaderboard)
        ranks = {row["id"]: row["rank"] for row in leaderboard}
        self._last_reveal_players = {
            p.id: message(
                "reveal",
                **common,
                your_answer=self.answers[p.id].choice if p.id in self.answers else None,
                your_points=self.answers[p.id].points if p.id in self.answers else 0,
                score=p.score,
                streak=p.streak,
                rank=ranks[p.id],
                leaderboard=leaderboard[:5],
            )
            for p in self.players.values()
        }
        await self.send_host(self._last_reveal_host)
        await asyncio.gather(*(self._send(p.ws, self._last_reveal_players[p.id]) for p in self.players.values()))

    async def _game_over(self) -> None:
        self.state = PartyState.GAME_OVER
        self.finished_at = time.monotonic()
        leaderboard = self.leaderboard()
        self._game_over_msg = message(
            "game_over",
            podium=leaderboard[:3],
            leaderboard=leaderboard,
            weakest_questions=self._weakest_questions(),
            question_stats=self.question_stats,
        )
        await self.broadcast(self._game_over_msg)
        if self.on_finish is not None:
            try:
                await self.on_finish(self)
            except Exception:  # błąd zapisu nie może zepsuć gry, która już się skończyła
                log.exception("Saving results of party %s failed", self.code)

    def _compute_question_stats(self, q: Question) -> Dict[str, Any]:
        """Statystyki jednego pytania liczone przy odsłonięciu (gracze obecni w tej rundzie)."""
        players = len(self.players)
        choice_counts = [0] * len(q.choices)
        correct_times = []
        times = []
        for answer in self.answers.values():
            choice_counts[answer.choice] += 1
            times.append(answer.elapsed)
            if answer.choice == q.correct:
                correct_times.append(answer.elapsed)
        fastest = None
        if correct_times:
            pid = min((pid for pid, a in self.answers.items() if a.choice == q.correct),
                      key=lambda pid: self.answers[pid].elapsed)
            fastest = {"nick": self.players[pid].nick, "time_ms": round(self.answers[pid].elapsed * 1000)}
        return {
            "question_id": q.id,
            "text": q.text,
            "correct_answer": q.choices[q.correct],
            "hint": q.hint,
            "players": players,
            "answered": len(self.answers),
            "correct_count": len(correct_times),
            "correct_ratio": round(len(correct_times) / players, 2) if players else 0.0,
            "avg_time_ms": round(sum(times) / len(times) * 1000) if times else None,
            "choice_counts": choice_counts,
            "fastest": fastest,
        }

    def _weakest_questions(self, limit: int = 3) -> List[Dict[str, Any]]:
        keys = ("question_id", "text", "correct_answer", "hint", "correct_ratio")
        ranked = sorted(self.question_stats, key=lambda s: s["correct_ratio"])
        return [{k: s[k] for k in keys} for s in ranked[:limit]]

    def cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
