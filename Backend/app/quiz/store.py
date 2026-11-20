"""Zapis i odczyt quizów z bazy (tabele quizzes + quiz_questions)."""

import secrets
from typing import List, Optional

from sqlmodel import Session, col, select

from app.models import Quiz, QuizQuestion
from app.quiz.schemas import Question


def make_title(text: str, limit: int = 80) -> str:
    first_line = text.strip().splitlines()[0].strip() if text.strip() else "Quiz"
    return first_line if len(first_line) <= limit else first_line[: limit - 1].rstrip() + "…"


def save_quiz(
    session: Session,
    owner_id: int,
    questions: List[Question],
    *,
    title: str,
    difficulty: str,
    source_text: str,
) -> Quiz:
    quiz = Quiz(
        id=secrets.token_urlsafe(8),
        owner_id=owner_id,
        title=title,
        difficulty=difficulty,
        source_text=source_text,
    )
    session.add(quiz)
    for position, q in enumerate(questions, start=1):
        session.add(QuizQuestion(
            quiz_id=quiz.id,
            position=position,
            text=q.text,
            choices=list(q.choices),
            correct=q.correct,
            explanation=q.explanation,
            hint=q.hint,
            time_limit=q.time_limit,
        ))
    session.commit()
    session.refresh(quiz)
    return quiz


def load_questions(session: Session, quiz_id: str) -> Optional[List[Question]]:
    """Pytania quizu w formacie gry albo None, gdy quizu nie ma."""
    if session.get(Quiz, quiz_id) is None:
        return None
    rows = session.exec(
        select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id).order_by(col(QuizQuestion.position))
    ).all()
    return [
        Question(
            id=f"q{r.position}",
            text=r.text,
            choices=r.choices,
            correct=r.correct,
            explanation=r.explanation,
            hint=r.hint,
            time_limit=r.time_limit,
        )
        for r in rows
    ]
