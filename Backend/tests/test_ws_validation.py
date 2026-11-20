"""Walidacja WebSocket: rozmiar i liczba wiadomości, format, nick, uprawnienia."""

from urllib.parse import quote

import pytest

from app.party.party import clean_nick
from app.party.router import MAX_MESSAGE_BYTES, RATE_LIMIT_BURST


def receive_until(ws, type_):
    for _ in range(50):
        msg = ws.receive_json()
        if msg["type"] == type_:
            return msg["data"]
    raise AssertionError(f"no {type_} message")


@pytest.fixture
def player(client):
    party = client.post("/api/parties").json()
    with client.websocket_connect(f"/ws/party/{party['code']}/player?nick=Ala") as ws:
        receive_until(ws, "joined")
        yield ws


@pytest.mark.parametrize("raw,error", [
    ("to nie json", "Expected JSON"),
    ('{"data": {}}', "Expected JSON"),
    ('{"type": 5}', "Expected JSON"),
    ('{"type": "answer", "data": 5}', "Expected JSON"),
    ('{"type": "start_game"}', "Unknown message type"),  # gracz nie może startować gry
    ('{"type": "answer", "data": {"question_id": "q1", "choice": 0}}', "Question is not open"),
])
def test_bad_messages_get_error_and_connection_stays(player, raw, error):
    player.send_text(raw)
    assert error in receive_until(player, "error")["message"]
    player.send_text('{"type": "nic"}')  # połączenie nadal działa
    assert receive_until(player, "error")["message"] == "Unknown message type: nic"


def test_too_large_message_rejected(player):
    player.send_text('{"type": "answer", "data": {"x": "' + "a" * MAX_MESSAGE_BYTES + '"}}')
    assert "too large" in receive_until(player, "error")["message"]


def test_flood_is_rate_limited(player):
    for _ in range(RATE_LIMIT_BURST + 5):
        player.send_text('{"type": "nic"}')
    errors = [receive_until(player, "error")["message"] for _ in range(RATE_LIMIT_BURST + 5)]
    assert errors.count("Too many messages, slow down") >= 5


@pytest.mark.parametrize("raw,clean", [
    ("  Ala   Kowalska ", "Ala Kowalska"),
    ("A​la", "Ala"),  # zero-width space
    ("Ala\x00\x07", "Ala"),
    ("Zoë 🎉", "Zoë 🎉"),
])
def test_clean_nick(raw, clean):
    assert clean_nick(raw) == clean


def test_invisible_nick_rejected_and_lookalike_duplicates_blocked(client):
    code = client.post("/api/parties").json()["code"]
    with client.websocket_connect(f"/ws/party/{code}/player?nick={quote(chr(0x200b) * 3)}") as ws:
        assert receive_until(ws, "error")["message"] == "Nick is required"
    with client.websocket_connect(f"/ws/party/{code}/player?nick=Ala") as a:
        receive_until(a, "joined")
        with client.websocket_connect(f"/ws/party/{code}/player?nick={quote('A' + chr(0x200b) + 'LA')}") as b:
            assert receive_until(b, "error")["message"] == "Nick already taken"
