import secrets
from typing import Dict, List, Optional

from app.config import get_settings
from app.party.party import Party
from app.quiz.schemas import Question


class PartyManager:
    """Keeps active parties in memory (one backend instance → enough; move to Redis to scale out)."""

    def __init__(self) -> None:
        self._parties: Dict[str, Party] = {}

    def create(self, questions: List[Question]) -> Party:
        settings = get_settings()
        code = self._new_code()
        party = Party(
            code=code,
            host_token=secrets.token_urlsafe(24),
            questions=questions,
            max_players=settings.max_players,
            max_nick_length=settings.max_nick_length,
        )
        self._parties[code] = party
        return party

    def get(self, code: str) -> Optional[Party]:
        return self._parties.get(code)

    def remove(self, code: str) -> None:
        party = self._parties.pop(code, None)
        if party is not None:
            party.cancel_timer()

    def _new_code(self) -> str:
        while True:
            code = f"{secrets.randbelow(10**6):06d}"
            if code not in self._parties:
                return code


manager = PartyManager()
