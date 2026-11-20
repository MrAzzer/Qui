import asyncio
import logging
import secrets
import time
from typing import Awaitable, Callable, Dict, List, Optional

from app.config import get_settings
from app.party.party import CLOSE_EXPIRED, Party

log = logging.getLogger(__name__)
from app.quiz.schemas import Question


class PartyManager:
    """Keeps active parties in memory (one backend instance → enough; move to Redis to scale out)."""

    def __init__(self) -> None:
        self._parties: Dict[str, Party] = {}

    def create(
        self,
        questions: List[Question],
        *,
        quiz_id: Optional[str] = None,
        host_user_id: Optional[int] = None,
        on_finish: Optional[Callable[[Party], Awaitable[None]]] = None,
    ) -> Party:
        settings = get_settings()
        code = self._new_code()
        party = Party(
            code=code,
            host_token=secrets.token_urlsafe(24),
            questions=questions,
            max_players=settings.max_players,
            max_nick_length=settings.max_nick_length,
            quiz_id=quiz_id,
            host_user_id=host_user_id,
            on_finish=on_finish,
        )
        self._parties[code] = party
        return party

    def get(self, code: str) -> Optional[Party]:
        return self._parties.get(code)

    def remove(self, code: str) -> None:
        party = self._parties.pop(code, None)
        if party is not None:
            party.cancel_timer()

    def __len__(self) -> int:
        return len(self._parties)

    def clear(self) -> None:
        for code in list(self._parties):
            self.remove(code)

    async def cleanup(self, now: Optional[float] = None) -> List[str]:
        """Usuwa porzucone i dawno zakończone party. Zwraca ich kody."""
        s = get_settings()
        now = time.monotonic() if now is None else now
        expired = [
            code for code, party in self._parties.items()
            if party.is_expired(now, s.party_idle_ttl, s.party_finished_ttl, s.party_max_age)
        ]
        for code in expired:
            party = self._parties.get(code)
            if party is None:
                continue
            self.remove(code)
            await party.close_all(CLOSE_EXPIRED, "Party expired")
        if expired:
            log.info("Removed %d expired parties, %d left", len(expired), len(self._parties))
        return expired

    async def run_cleanup_loop(self) -> None:
        """Zadanie w tle uruchamiane przy starcie serwera."""
        interval = get_settings().party_cleanup_interval
        while True:
            await asyncio.sleep(interval)
            try:
                await self.cleanup()
            except Exception:
                log.exception("Party cleanup failed")

    def _new_code(self) -> str:
        while True:
            code = f"{secrets.randbelow(10**6):06d}"
            if code not in self._parties:
                return code


manager = PartyManager()
