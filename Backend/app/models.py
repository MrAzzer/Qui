"""Tabele bazy danych.

users ──< quizzes ──< quiz_questions
  │          │
  │          └──< game_sessions ──< game_results ──< game_answers
  └──────────────────(host)   (gracz, opcjonalnie)

Gracze mogą grać bez konta (sam nick) — wtedy game_results.user_id jest pusty.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import JSON, Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=254)  # zawsze małymi literami
    display_name: str = Field(max_length=40)
    password_hash: str
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class Quiz(SQLModel, table=True):
    __tablename__ = "quizzes"

    # Losowy tekstowy id (jak dotąd w /api/quizzes/{id}), trudny do odgadnięcia
    id: str = Field(primary_key=True, max_length=32)
    owner_id: int = Field(foreign_key="users.id", index=True)
    title: str = Field(max_length=120)
    difficulty: str = Field(max_length=10)
    source_text: str = Field(sa_column=Column(Text, nullable=False))  # materiał, z którego powstał quiz
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class QuizQuestion(SQLModel, table=True):
    __tablename__ = "quiz_questions"
    __table_args__ = (UniqueConstraint("quiz_id", "position"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    quiz_id: str = Field(foreign_key="quizzes.id", index=True)
    position: int  # 1, 2, 3… — kolejność w quizie; w grze pytanie ma id "q{position}"
    text: str = Field(sa_column=Column(Text, nullable=False))
    choices: List[str] = Field(sa_column=Column(JSON, nullable=False))
    correct: int
    explanation: str = Field(default="", sa_column=Column(Text, nullable=False))
    hint: str = Field(default="", sa_column=Column(Text, nullable=False))
    time_limit: int = 20


class GameSession(SQLModel, table=True):
    """Jedna rozegrana gra (party), zapisywana po jej zakończeniu."""

    __tablename__ = "game_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=6)
    quiz_id: Optional[str] = Field(default=None, foreign_key="quizzes.id", index=True)  # None = przykładowy quiz
    host_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    question_count: int
    player_count: int
    started_at: datetime = Field(sa_type=DateTime(timezone=True))
    finished_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class GameResult(SQLModel, table=True):
    """Wynik jednego gracza w jednej grze."""

    __tablename__ = "game_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="game_sessions.id", index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)  # None = gość
    nick: str = Field(max_length=20)
    score: int
    rank: int
    correct_count: int


class GameAnswer(SQLModel, table=True):
    """Odpowiedź gracza na jedno pytanie — z tego budujemy listę „do powtórki”."""

    __tablename__ = "game_answers"

    id: Optional[int] = Field(default=None, primary_key=True)
    result_id: int = Field(foreign_key="game_results.id", index=True)
    question_position: int
    choice: Optional[int] = None  # None = brak odpowiedzi
    is_correct: bool
    points: int
    elapsed_ms: Optional[int] = None
