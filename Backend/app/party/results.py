"""Zapis zakończonej gry do bazy: game_sessions + game_results + game_answers."""

import asyncio
from datetime import datetime, timezone

from app.db import session_scope
from app.models import GameAnswer, GameResult, GameSession
from app.party.party import Party


def save_party_results(party: Party) -> int:
    """Zapisuje grę i zwraca id sesji. Synchroniczne — wołaj przez save_party_results_async."""
    ranks = {row["id"]: row["rank"] for row in party.leaderboard()}
    with session_scope() as session:
        game = GameSession(
            code=party.code,
            quiz_id=party.quiz_id,
            host_id=party.host_user_id,
            question_count=len(party.questions),
            player_count=len(party.players),
            started_at=party.started_at or datetime.now(timezone.utc),
        )
        session.add(game)
        session.flush()  # nadaje game.id

        for player in party.players.values():
            result = GameResult(
                session_id=game.id,
                user_id=player.user_id,
                nick=player.nick,
                score=player.score,
                rank=ranks[player.id],
                correct_count=0,
            )
            session.add(result)
            session.flush()

            for position, (question, answers) in enumerate(zip(party.questions, party.history), start=1):
                answer = answers.get(player.id)
                is_correct = answer is not None and answer.choice == question.correct
                result.correct_count += is_correct
                session.add(GameAnswer(
                    result_id=result.id,
                    question_position=position,
                    choice=answer.choice if answer else None,
                    is_correct=is_correct,
                    points=answer.points if answer else 0,
                    elapsed_ms=round(answer.elapsed * 1000) if answer else None,
                ))
        session.commit()
        return game.id


async def save_party_results_async(party: Party) -> None:
    # Zapis w osobnym wątku, żeby baza nie blokowała WebSocketów innych gier
    await asyncio.to_thread(save_party_results, party)
