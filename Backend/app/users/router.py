from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.auth.deps import get_current_user
from app.db import get_session
from app.models import GameAnswer, GameResult, GameSession, Quiz, QuizQuestion, User

router = APIRouter(prefix="/api/users/me", tags=["users"])


class MyQuiz(BaseModel):
    id: str
    title: str
    difficulty: str
    question_count: int
    created_at: datetime


class MyGame(BaseModel):
    session_id: int
    quiz_id: Optional[str]
    quiz_title: str
    played_at: datetime
    nick: str
    score: int
    rank: int
    player_count: int
    correct_count: int
    question_count: int


class ReviewItem(BaseModel):
    quiz_id: str
    quiz_title: str
    question: str
    correct_answer: str
    your_answer: Optional[str]
    explanation: str
    hint: str
    times_wrong: int


@router.get("/quizzes", response_model=List[MyQuiz])
def my_quizzes(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    counts = (
        select(QuizQuestion.quiz_id, func.count().label("n"))
        .group_by(QuizQuestion.quiz_id)
        .subquery()
    )
    rows = session.exec(
        select(Quiz, counts.c.n)
        .join(counts, counts.c.quiz_id == Quiz.id)
        .where(Quiz.owner_id == user.id)
        .order_by(col(Quiz.created_at).desc())
    ).all()
    return [
        MyQuiz(id=q.id, title=q.title, difficulty=q.difficulty, question_count=n, created_at=q.created_at)
        for q, n in rows
    ]


@router.get("/games", response_model=List[MyGame])
def my_games(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Gry, w których użytkownik grał jako zalogowany gracz (od najnowszej)."""
    rows = session.exec(
        select(GameResult, GameSession, Quiz.title)
        .join(GameSession, GameSession.id == GameResult.session_id)
        .join(Quiz, Quiz.id == GameSession.quiz_id, isouter=True)
        .where(GameResult.user_id == user.id)
        .order_by(col(GameSession.finished_at).desc())
        .limit(limit)
    ).all()
    return [
        MyGame(
            session_id=g.id,
            quiz_id=g.quiz_id,
            quiz_title=title or "Przykładowy quiz",
            played_at=g.finished_at,
            nick=r.nick,
            score=r.score,
            rank=r.rank,
            player_count=g.player_count,
            correct_count=r.correct_count,
            question_count=g.question_count,
        )
        for r, g, title in rows
    ]


@router.get("/review", response_model=List[ReviewItem])
def my_review(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Pytania do powtórki: te, na które użytkownik odpowiedział źle, najczęściej mylone na górze."""
    rows = session.exec(
        select(GameAnswer, QuizQuestion, Quiz.title, GameSession.finished_at)
        .join(GameResult, GameResult.id == GameAnswer.result_id)
        .join(GameSession, GameSession.id == GameResult.session_id)
        .join(QuizQuestion, (QuizQuestion.quiz_id == GameSession.quiz_id)
              & (QuizQuestion.position == GameAnswer.question_position))
        .join(Quiz, Quiz.id == QuizQuestion.quiz_id)
        .where(GameResult.user_id == user.id, GameAnswer.is_correct == False)  # noqa: E712
        .order_by(col(GameSession.finished_at).desc())
    ).all()

    # Jedno pytanie może być pomylone w kilku grach — grupujemy, ostatnia zła odpowiedź wygrywa
    items = {}
    for answer, question, title, _ in rows:
        item = items.get(question.id)
        if item is None:
            your = question.choices[answer.choice] if answer.choice is not None else None
            items[question.id] = ReviewItem(
                quiz_id=question.quiz_id,
                quiz_title=title,
                question=question.text,
                correct_answer=question.choices[question.correct],
                your_answer=your,
                explanation=question.explanation,
                hint=question.hint,
                times_wrong=1,
            )
        else:
            item.times_wrong += 1
    return sorted(items.values(), key=lambda i: -i.times_wrong)[:limit]
