"""Pełna gra przez WebSocket: zalogowany host i gracz + gość → wyniki w bazie i w historii."""

import time

from sqlmodel import select

from app.db import session_scope
from app.models import GameAnswer, GameResult, GameSession
from app.quiz.router import get_generator
from app.quiz.sample import get_sample_questions
from tests.conftest import auth_header, register


def fake_generator(text, count, difficulty, time_limit):
    return get_sample_questions()[:count]  # w przykładowych pytaniach poprawna odpowiedź to zawsze 1


def receive_until(ws, type_):
    for _ in range(30):
        msg = ws.receive_json()
        if msg["type"] == type_:
            return msg["data"]
    raise AssertionError(f"no {type_} message")


def wait_for(fn, timeout=3.0):
    """Wyniki zapisują się w tle tuż po końcu gry."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timeout")


def play_game(client, code, host_token, players, choices_per_question):
    """players: lista (nick, access_token|None). choices_per_question: [{nick: choice}] na każde pytanie."""
    with client.websocket_connect(f"/ws/party/{code}/host?token={host_token}") as host:
        sockets = {}
        for nick, token in players:
            url = f"/ws/party/{code}/player?nick={nick}" + (f"&access_token={token}" if token else "")
            ws = client.websocket_connect(url).__enter__()
            receive_until(ws, "joined")
            sockets[nick] = ws
        try:
            host.send_json({"type": "start_game"})
            for choices in choices_per_question:
                q = receive_until(host, "question")
                for nick, ws in sockets.items():
                    receive_until(ws, "question")
                    if nick in choices:
                        ws.send_json({"type": "answer",
                                      "data": {"question_id": q["question_id"], "choice": choices[nick]}})
                        receive_until(ws, "answer_ack")
                if len(choices) < len(sockets):
                    host.send_json({"type": "next_question"})  # ktoś nie odpowiada → host kończy pytanie
                reveal = receive_until(host, "reveal")
                host.send_json({"type": "next_question"})
            assert reveal["is_last"]
            return receive_until(host, "game_over")
        finally:
            for ws in sockets.values():
                ws.__exit__(None, None, None)


def test_logged_in_game_is_saved_and_shows_in_history(client):
    host = register(client, email="host@example.com", name="Pani Ania")
    ala = register(client, email="ala@example.com", name="Ala")
    host_h, ala_h = auth_header(host["access_token"]), auth_header(ala["access_token"])

    client.app.dependency_overrides[get_generator] = lambda: fake_generator
    quiz = client.post("/api/quizzes/generate", headers=host_h,
                       json={"text": "Biologia komórki: mitochondria i rybosomy. " * 3, "count": 3,
                             "title": "Biologia — test"}).json()
    assert quiz["title"] == "Biologia — test"

    party = client.post("/api/parties", json={"quiz_id": quiz["id"]}, headers=host_h).json()
    # Ala (konto): dobrze, dobrze, źle. Gość Ola: źle, brak odpowiedzi, dobrze.
    over = play_game(client, party["code"], party["host_token"],
                     players=[("Ala", ala["access_token"]), ("Ola", None)],
                     choices_per_question=[{"Ala": 1, "Ola": 0}, {"Ala": 1}, {"Ala": 0, "Ola": 1}])
    assert over["podium"][0]["nick"] == "Ala"

    games = wait_for(lambda: client.get("/api/users/me/games", headers=ala_h).json())
    assert len(games) == 1
    g = games[0]
    assert (g["quiz_title"], g["rank"], g["correct_count"], g["question_count"], g["player_count"]) == \
           ("Biologia — test", 1, 2, 3, 2)
    assert g["score"] == over["podium"][0]["score"]

    # do powtórki: tylko pytanie 3, z twoją złą odpowiedzią i wskazówką
    review = client.get("/api/users/me/review", headers=ala_h).json()
    assert len(review) == 1
    assert review[0]["question"].startswith("W którym roku")
    assert review[0]["your_answer"] == "1914"
    assert review[0]["correct_answer"] == "1939"
    assert review[0]["hint"]

    # quiz widnieje u hosta, a host nie grał, więc nie ma go w historii gier
    assert [q["id"] for q in client.get("/api/users/me/quizzes", headers=host_h).json()] == [quiz["id"]]
    assert client.get("/api/users/me/games", headers=host_h).json() == []

    with session_scope() as s:
        session = s.exec(select(GameSession)).one()
        assert (session.quiz_id, session.host_id) == (quiz["id"], host["user"]["id"])
        guest = s.exec(select(GameResult).where(GameResult.nick == "Ola")).one()
        assert guest.user_id is None and guest.correct_count == 1
        unanswered = s.exec(select(GameAnswer).where(GameAnswer.result_id == guest.id,
                                                     GameAnswer.question_position == 2)).one()
        assert unanswered.choice is None and not unanswered.is_correct


def test_guest_game_on_sample_quiz_is_saved_without_users(client):
    party = client.post("/api/parties").json()
    play_game(client, party["code"], party["host_token"], players=[("Gość", None)],
              choices_per_question=[{"Gość": 1}] * 3)

    def saved():
        with session_scope() as s:
            return s.exec(select(GameSession)).first()

    game = wait_for(saved)
    assert game.quiz_id is None and game.host_id is None and game.player_count == 1


def test_logged_in_player_rejoins_by_token(client):
    ala = register(client)
    party = client.post("/api/parties").json()
    url = f"/ws/party/{party['code']}/player?nick=Ala&access_token={ala['access_token']}"
    with client.websocket_connect(url) as first:
        player_id = receive_until(first, "joined")["player_id"]
    # nowe urządzenie, bez reconnect_token — wraca na to samo miejsce
    with client.websocket_connect(url) as second:
        assert receive_until(second, "joined")["player_id"] == player_id


def test_player_with_bad_token_is_rejected(client):
    party = client.post("/api/parties").json()
    with client.websocket_connect(f"/ws/party/{party['code']}/player?nick=X&access_token=zly") as ws:
        assert receive_until(ws, "error")["message"] == "Invalid or expired access token"
