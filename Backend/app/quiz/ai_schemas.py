"""Format odpowiedzi modelu AI i jego konwersja na pytania gry (app.quiz.schemas.Question).

Model zwraca JSON w formacie AIQuiz. Odpowiedź, która nie jest w 100% zgodna
z tymi modelami, jest odrzucana (i ponawiana w generatorze).
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.quiz.schemas import Question

OPTIONS_PER_QUESTION = 4
MIN_COUNT = 1
MAX_COUNT = 20
MIN_TEXT_LENGTH = 30
MAX_TEXT_LENGTH = 60_000


class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class AIQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    question: str = Field(min_length=1)
    options: List[str] = Field(min_length=OPTIONS_PER_QUESTION, max_length=OPTIONS_PER_QUESTION)
    correct_index: int = Field(ge=0, le=OPTIONS_PER_QUESTION - 1)
    explanation: str = Field(min_length=1)
    hint: str = Field(min_length=1)

    @field_validator("options")
    @classmethod
    def options_must_be_distinct(cls, options: List[str]) -> List[str]:
        cleaned = [o.strip() for o in options]
        if any(not o for o in cleaned):
            raise ValueError("odpowiedź nie może być pusta")
        if len({o.casefold() for o in cleaned}) != len(cleaned):
            raise ValueError("odpowiedzi muszą być różne")
        return cleaned


class AIQuiz(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    questions: List[AIQuestion] = Field(min_length=1)

    @field_validator("questions")
    @classmethod
    def questions_must_be_unique(cls, questions: List[AIQuestion]) -> List[AIQuestion]:
        seen = set()
        for n, q in enumerate(questions, start=1):
            key = q.question.casefold()
            if key in seen:
                raise ValueError(f"pytanie {n} jest duplikatem")
            seen.add(key)
        return questions


def to_game_questions(quiz: AIQuiz, time_limit: int = 20) -> List[Question]:
    return [
        Question(
            id=f"q{n}",
            text=q.question,
            choices=list(q.options),
            correct=q.correct_index,
            explanation=q.explanation,
            hint=q.hint,
            time_limit=time_limit,
        )
        for n, q in enumerate(quiz.questions, start=1)
    ]


class GenerateQuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Albo wklejony tekst, albo id wgranego materiału (POST /api/materials)
    text: Optional[str] = Field(default=None, min_length=MIN_TEXT_LENGTH, max_length=MAX_TEXT_LENGTH)
    material_id: Optional[str] = None
    count: int = Field(default=5, ge=MIN_COUNT, le=MAX_COUNT)
    difficulty: Difficulty = Difficulty.medium
    time_limit: int = Field(default=20, ge=5, le=120)
    title: Optional[str] = Field(default=None, max_length=120)  # brak = pierwsza linia materiału

    @model_validator(mode="after")
    def _text_or_material(self) -> "GenerateQuizRequest":
        if (self.text is None) == (self.material_id is None):
            raise ValueError("Podaj dokładnie jedno: text albo material_id")
        return self


class QuizResponse(BaseModel):
    id: str
    title: str = ""
    questions: List[Question]
