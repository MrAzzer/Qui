from fastapi import APIRouter, Depends, HTTPException

from app.quiz.ai_schemas import GenerateQuizRequest, QuizResponse
from app.quiz.generator import QuizGenerationError, generate_questions
from app.quiz.store import quiz_store

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


def get_generator():
    """Zależność podmieniana w testach (app.dependency_overrides)."""
    return generate_questions


@router.post(
    "/generate",
    response_model=QuizResponse,
    status_code=201,
    responses={502: {"description": "Dostawca AI nie zwrócił poprawnego quizu"}},
)
def generate(body: GenerateQuizRequest, generator=Depends(get_generator)) -> QuizResponse:
    # Funkcja synchroniczna: FastAPI uruchamia ją w puli wątków,
    # więc wolne zapytanie do AI nie blokuje WebSocketów gry.
    try:
        questions = generator(body.text, body.count, body.difficulty, body.time_limit)
    except QuizGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return QuizResponse(id=quiz_store.add(questions), questions=questions)


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz(quiz_id: str) -> QuizResponse:
    questions = quiz_store.get(quiz_id)
    if questions is None:
        raise HTTPException(404, "Quiz not found")
    return QuizResponse(id=quiz_id, questions=questions)
