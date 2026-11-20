"""GET /api/parties/{code} i limit graczy."""

from contextlib import ExitStack

from app.config import get_settings
from app.quiz.router import get_generator
from app.quiz.sample import get_sample_questions


def test_party_preview(client):
    party = client.post("/api/parties").json()
    info = client.get(f"/api/parties/{party['code']}").json()
    assert info == {
        "code": party["code"],
        "title": "Przykładowy quiz",
        "state": "lobby",
        "joinable": True,
        "player_count": 0,
        "max_players": get_settings().max_players,
        "players": [],
        "question_count": 3,
        "current_question": None,
        "host_connected": False,
    }
    assert "host_token" not in str(info)


def test_preview_shows_players_host_and_current_question(client):
    party = client.post("/api/parties").json()
    code = party["code"]
    with client.websocket_connect(f"/ws/party/{code}/host?token={party['host_token']}") as host, \
         client.websocket_connect(f"/ws/party/{code}/player?nick=Ala") as ala:
        ala.receive_json()
        info = client.get(f"/api/parties/{code}").json()
        assert info["players"] == [{"nick": "Ala", "connected": True}] and info["host_connected"]
        host.send_json({"type": "start_game"})
        while ala.receive_json()["type"] != "question":
            pass
        info = client.get(f"/api/parties/{code}").json()
        assert (info["state"], info["current_question"], info["joinable"]) == ("question", 1, False)


def test_party_title_comes_from_quiz(client, auth_headers):
    client.app.dependency_overrides[get_generator] = lambda: (lambda *a: get_sample_questions()[:2])
    quiz = client.post("/api/quizzes/generate", headers=auth_headers,
                       json={"text": "Notatki z historii Polski. " * 3, "count": 2, "title": "Historia"}).json()
    party = client.post("/api/parties", json={"quiz_id": quiz["id"]}).json()
    assert client.get(f"/api/parties/{party['code']}").json()["title"] == "Historia"


def test_host_sets_player_limit(client):
    party = client.post("/api/parties", json={"max_players": 2}).json()
    code = party["code"]
    with ExitStack() as stack:
        for nick in ("Ala", "Ola"):
            ws = stack.enter_context(client.websocket_connect(f"/ws/party/{code}/player?nick={nick}"))
            assert ws.receive_json()["type"] == "joined"
        info = client.get(f"/api/parties/{code}").json()
        assert (info["max_players"], info["joinable"]) == (2, False)
        third = stack.enter_context(client.websocket_connect(f"/ws/party/{code}/player?nick=Ela"))
        assert third.receive_json()["data"]["message"] == "Party is full"


def test_player_limit_cannot_exceed_server_limit(client):
    too_many = get_settings().max_players + 1
    assert client.post("/api/parties", json={"max_players": too_many}).status_code == 422
    assert client.post("/api/parties", json={"max_players": 0}).status_code == 422


def test_lobby_updates_are_batched_when_many_players_join(client):
    """Optymalizacja T7: 20 szybkich dołączeń ≠ 20 rozesłanych list graczy."""
    party = client.post("/api/parties").json()
    code = party["code"]
    with ExitStack() as stack:
        host = stack.enter_context(client.websocket_connect(f"/ws/party/{code}/host?token={party['host_token']}"))
        for i in range(20):
            ws = stack.enter_context(client.websocket_connect(f"/ws/party/{code}/player?nick=Gracz{i}"))
            assert ws.receive_json()["type"] == "joined"
        updates = 0
        while True:
            msg = host.receive_json()
            if msg["type"] == "lobby_update":
                updates += 1
                if len(msg["data"]["players"]) == 20:  # ostatnia aktualizacja ma wszystkich
                    break
        assert updates <= 5
