from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.auth.deps import get_current_user
from app.db import get_session
from app.models import Quiz, User
from app.quiz.ai_schemas import GenerateQuizRequest, QuizResponse
from app.quiz.generator import QuizGenerationError, generate_questions
from app.quiz.store import load_questions, make_title, save_quiz

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


def get_generator():
    """Zależność podmieniana w testach (app.dependency_overrides)."""
    return generate_questions


@router.post(
    "/generate",
    response_model=QuizResponse,
    status_code=201,
    responses={
        401: {"description": "Trzeba być zalogowanym (chroni limit klucza AI)"},
        502: {"description": "Dostawca AI nie zwrócił poprawnego quizu"},
    },
)
def generate(
    body: GenerateQuizRequest,
    generator=Depends(get_generator),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> QuizResponse:
    # Funkcja synchroniczna: FastAPI uruchamia ją w puli wątków,
    # więc wolne zapytanie do AI nie blokuje WebSocketów gry.
    try:
        questions = generator(body.text, body.count, body.difficulty, body.time_limit)
    except QuizGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    quiz = save_quiz(
        session,
        user.id,
        questions,
        title=(body.title or "").strip() or make_title(body.text),
        difficulty=body.difficulty.value,
        source_text=body.text,
    )
    return QuizResponse(id=quiz.id, title=quiz.title, questions=load_questions(session, quiz.id))


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz(quiz_id: str, session: Session = Depends(get_session)) -> QuizResponse:
    quiz = session.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(404, "Quiz not found")
    return QuizResponse(id=quiz.id, title=quiz.title, questions=load_questions(session, quiz.id))
