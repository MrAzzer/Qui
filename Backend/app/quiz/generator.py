"""Zamknięta funkcja: tekst -> AI -> walidacja Pydantic -> pytania gotowe do gry."""

import logging
import random
from typing import List, Optional, Union

import openai

from app.config import Settings, get_settings
from app.quiz.ai_schemas import (
    MAX_COUNT,
    MIN_COUNT,
    MIN_TEXT_LENGTH,
    OPTIONS_PER_QUESTION,
    AIQuestion,
    AIQuiz,
    Difficulty,
    to_game_questions,
)
from app.quiz.prompts import SYSTEM_PROMPT, build_user_prompt
from app.quiz.schemas import Question

log = logging.getLogger(__name__)

# Schemat dla trybu structured outputs dostawcy. Ostateczna walidacja: AIQuiz (Pydantic).
AI_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "correct_index": {"type": "integer"},
                    "explanation": {"type": "string"},
                    "hint": {"type": "string"},
                },
                "required": ["question", "options", "correct_index", "explanation", "hint"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


class QuizGenerationError(Exception):
    """Nie udało się wygenerować poprawnego quizu (błąd API albo zły format)."""


def make_client(settings: Settings) -> openai.OpenAI:
    if not settings.llm_api_key:
        raise QuizGenerationError("Brak klucza API: ustaw LLM_API_KEY w Backend/.env")
    # max_retries=2: SDK sam ponawia błędy sieci, 429 i 5xx.
    return openai.OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
        max_retries=2,
    )


def _response_format(kind: str) -> dict:
    if kind == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {"name": "quiz", "strict": True, "schema": AI_JSON_SCHEMA},
    }


def parse_ai_quiz(content: Optional[str], count: int) -> AIQuiz:
    """Waliduje surową odpowiedź modelu. ValueError przy każdej niezgodności."""
    if not content or not content.strip():
        raise ValueError("model zwrócił pustą odpowiedź")
    quiz = AIQuiz.model_validate_json(content)  # ValidationError dziedziczy po ValueError
    if len(quiz.questions) != count:
        raise ValueError(f"oczekiwano {count} pytań, otrzymano {len(quiz.questions)}")
    return quiz


def shuffle_options(quiz: AIQuiz, rng: Optional[random.Random] = None) -> AIQuiz:
    """Losuje kolejność odpowiedzi, żeby poprawna nie była ciągle na tej samej pozycji."""
    rng = rng or random.Random()
    out = []
    for q in quiz.questions:
        order = list(range(OPTIONS_PER_QUESTION))
        rng.shuffle(order)
        out.append(
            AIQuestion(
                question=q.question,
                options=[q.options[i] for i in order],
                correct_index=order.index(q.correct_index),
                explanation=q.explanation,
                hint=q.hint,
            )
        )
    return AIQuiz(questions=out)


def generate_questions(
    text: str,
    count: int = 5,
    difficulty: Union[Difficulty, str] = Difficulty.medium,
    time_limit: int = 20,
    *,
    client=None,
    settings: Optional[Settings] = None,
    shuffle: bool = True,
) -> List[Question]:
    """Przyjmuje tekst materiału, pyta AI, waliduje przez Pydantic, zwraca pytania gry.

    Zepsuty JSON / zła struktura -> ponowienie (maks. settings.llm_max_attempts razy).
    Błąd API albo wyczerpane próby -> QuizGenerationError.
    """
    text = (text or "").strip()
    if len(text) < MIN_TEXT_LENGTH:
        raise ValueError(f"Materiał jest za krótki (min. {MIN_TEXT_LENGTH} znaków)")
    if not MIN_COUNT <= count <= MAX_COUNT:
        raise ValueError(f"Liczba pytań musi być z zakresu {MIN_COUNT}-{MAX_COUNT}")
    difficulty = Difficulty(difficulty)
    settings = settings or get_settings()
    client = client or make_client(settings)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(text, count, difficulty)},
    ]

    last_error: Optional[Exception] = None
    attempts = max(1, settings.llm_max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                response_format=_response_format(settings.llm_response_format),
            )
        except openai.APIError as exc:
            raise QuizGenerationError(f"Błąd API dostawcy LLM: {exc}") from exc

        content = response.choices[0].message.content if response.choices else None
        try:
            quiz = parse_ai_quiz(content, count)
        except ValueError as exc:
            last_error = exc
            log.warning("Próba %d/%d: odrzucono odpowiedź modelu: %s", attempt, attempts, exc)
            continue
        if shuffle:
            quiz = shuffle_options(quiz)
        return to_game_questions(quiz, time_limit)

    raise QuizGenerationError(
        f"Model nie zwrócił poprawnego quizu po {attempts} próbach. Ostatni błąd: {last_error}"
    )
