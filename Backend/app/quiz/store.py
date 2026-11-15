"""Magazyn wygenerowanych quizów w pamięci. W T5 do podmiany na SQLite (SQLModel)."""

import secrets
from typing import Dict, List, Optional

from app.quiz.schemas import Question


class QuizStore:
    def __init__(self) -> None:
        self._quizzes: Dict[str, List[Question]] = {}

    def add(self, questions: List[Question]) -> str:
        quiz_id = secrets.token_urlsafe(8)
        self._quizzes[quiz_id] = [q.model_copy() for q in questions]
        return quiz_id

    def get(self, quiz_id: str) -> Optional[List[Question]]:
        questions = self._quizzes.get(quiz_id)
        return None if questions is None else [q.model_copy() for q in questions]


quiz_store = QuizStore()
