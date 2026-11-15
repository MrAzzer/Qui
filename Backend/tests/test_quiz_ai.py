"""Testy modułu AI. Nie odpytują prawdziwego API (fałszywy klient)."""

import json
import random
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.quiz.ai_schemas import AIQuestion, AIQuiz
from app.quiz.generator import (
    QuizGenerationError,
    generate_questions,
    parse_ai_quiz,
    shuffle_options,
)
from app.quiz.router import get_generator
from app.quiz.schemas import Question

MATERIAL = "Fotosynteza to proces, w którym rośliny wytwarzają glukozę z CO2 i wody."
SETTINGS = Settings(_env_file=None, llm_api_key="test", llm_max_attempts=3)


def ai_question(n: int = 1, correct: int = 0) -> dict:
    return {
        "question": f"Pytanie {n}?",
        "options": [f"A{n}", f"B{n}", f"C{n}", f"D{n}"],
        "correct_index": correct,
        "explanation": "Bo tak jest w materiale.",
        "hint": "Skojarzenie.",
    }


def ai_json(count: int) -> str:
    return json.dumps({"questions": [ai_question(i) for i in range(1, count + 1)]})


class FakeClient:
    """Zwraca kolejne odpowiedzi z listy, jak chat.completions.create."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        content = self.responses.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


# --- walidacja Pydantic -----------------------------------------------------

def test_valid_ai_quiz_parses():
    assert len(parse_ai_quiz(ai_json(3), 3).questions) == 3


@pytest.mark.parametrize(
    "mutate",
    [
        lambda q: q.update(options=["a", "b", "c"]),
        lambda q: q.update(options=["a", "b", "c", "d", "e"]),
        lambda q: q.update(options=["a", "A", "c", "d"]),
        lambda q: q.update(options=["a", " ", "c", "d"]),
        lambda q: q.update(correct_index=4),
        lambda q: q.update(correct_index=-1),
        lambda q: q.update(correct_index="1"),
        lambda q: q.update(correct_index=True),
        lambda q: q.update(question="   "),
        lambda q: q.update(hint=""),
        lambda q: q.pop("explanation"),
        lambda q: q.update(extra="pole spoza schematu"),
    ],
)
def test_invalid_ai_question_rejected(mutate):
    q = ai_question()
    mutate(q)
    with pytest.raises(ValueError):
        parse_ai_quiz(json.dumps({"questions": [q]}), 1)


@pytest.mark.parametrize("content", ["", '{"questions": [', "to nie json"])
def test_broken_output_rejected(content):
    with pytest.raises(ValueError):
        parse_ai_quiz(content, 1)


def test_duplicate_questions_rejected():
    q = ai_question()
    with pytest.raises(ValueError):
        parse_ai_quiz(json.dumps({"questions": [q, dict(q)]}), 2)


def test_wrong_count_rejected():
    with pytest.raises(ValueError, match="oczekiwano 5"):
        parse_ai_quiz(ai_json(3), 5)


def test_shuffle_keeps_correct_answer():
    quiz = AIQuiz(questions=[AIQuestion(**ai_question(i, correct=i % 4)) for i in range(1, 9)])
    shuffled = shuffle_options(quiz, random.Random(42))
    for before, after in zip(quiz.questions, shuffled.questions):
        assert sorted(before.options) == sorted(after.options)
        assert after.options[after.correct_index] == before.options[before.correct_index]


# --- generator: format gry, ponawianie, błędy --------------------------------

def test_generate_returns_game_questions():
    questions = generate_questions(MATERIAL, 2, time_limit=30, client=FakeClient([ai_json(2)]), settings=SETTINGS)
    assert [q.id for q in questions] == ["q1", "q2"]
    assert all(isinstance(q, Question) and q.time_limit == 30 for q in questions)
    assert questions[0].explanation and questions[0].hint


def test_generate_retries_on_bad_output():
    client = FakeClient(["zły", ai_json(1), ai_json(2)])
    assert len(generate_questions(MATERIAL, 2, client=client, settings=SETTINGS)) == 2
    assert client.calls == 3


def test_generate_gives_up_after_max_attempts():
    with pytest.raises(QuizGenerationError, match="3 próbach"):
        generate_questions(MATERIAL, 2, client=FakeClient(["zły"] * 3), settings=SETTINGS)


def test_generate_without_api_key_fails_clearly():
    with pytest.raises(QuizGenerationError, match="LLM_API_KEY"):
        generate_questions(MATERIAL, 2, settings=Settings(_env_file=None, llm_api_key=""))


@pytest.mark.parametrize("text,count", [("krótko", 2), (MATERIAL, 0), (MATERIAL, 21)])
def test_generate_rejects_bad_input(text, count):
    with pytest.raises(ValueError):
        generate_questions(text, count, client=FakeClient([]), settings=SETTINGS)


# --- REST: /api/quizzes i podpięcie do /api/parties ---------------------------

@pytest.fixture
def api():
    yield TestClient(app)
    app.dependency_overrides.clear()


def fake_generator(text, count, difficulty, time_limit):
    return generate_questions(text, count, difficulty, time_limit,
                              client=FakeClient([ai_json(count)]), settings=SETTINGS)


def test_generate_endpoint_and_party_from_quiz(api):
    app.dependency_overrides[get_generator] = lambda: fake_generator
    r = api.post("/api/quizzes/generate", json={"text": MATERIAL, "count": 3, "difficulty": "easy"})
    assert r.status_code == 201
    quiz = r.json()
    assert len(quiz["questions"]) == 3
    assert set(quiz["questions"][0]) == {"id", "text", "choices", "correct", "explanation", "hint", "time_limit"}

    assert api.get(f"/api/quizzes/{quiz['id']}").json() == quiz

    party = api.post("/api/parties", json={"quiz_id": quiz["id"]})
    assert party.status_code == 201
    summary = api.get(f"/api/parties/{party.json()['code']}").json()
    assert summary["question_count"] == 3


def test_party_with_unknown_quiz_is_404(api):
    assert api.post("/api/parties", json={"quiz_id": "nie-ma"}).status_code == 404


def test_party_without_quiz_uses_sample(api):
    assert api.post("/api/parties").status_code == 201


def test_generate_endpoint_validates_input(api):
    r = api.post("/api/quizzes/generate", json={"text": "krótko", "count": 50})
    assert r.status_code == 422


def test_generate_endpoint_maps_ai_failure_to_502(api):
    def failing(*args):
        raise QuizGenerationError("limit wyczerpany")

    app.dependency_overrides[get_generator] = lambda: failing
    r = api.post("/api/quizzes/generate", json={"text": MATERIAL})
    assert r.status_code == 502
    assert "limit" in r.json()["detail"]
