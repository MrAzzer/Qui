"""Powrót po rozłączeniu w każdym stanie gry: gracz i host widzą aktualny ekran."""

from contextlib import ExitStack

import pytest


@pytest.fixture
def stack():
    # zamyka wszystkie połączenia na koniec testu — inaczej klient testowy czeka na nie w nieskończoność
    with ExitStack() as s:
        yield s


def receive_until(ws, type_):
    for _ in range(30):
        msg = ws.receive_json()
        if msg["type"] == type_:
            return msg["data"]
    raise AssertionError(f"no {type_} message")


def start_game(client, stack):
    """Party z dwoma graczami (Ala, Ola) w trakcie pierwszego pytania."""
    party = client.post("/api/parties").json()
    code = party["code"]
    host = stack.enter_context(client.websocket_connect(f"/ws/party/{code}/host?token={party['host_token']}"))
    ala = stack.enter_context(client.websocket_connect(f"/ws/party/{code}/player?nick=Ala"))
    ola = stack.enter_context(client.websocket_connect(f"/ws/party/{code}/player?nick=Ola"))
    ala_token = receive_until(ala, "joined")["reconnect_token"]
    receive_until(ola, "joined")
    host.send_json({"type": "start_game"})
    q = receive_until(ala, "question")
    receive_until(ola, "question")
    return party, host, ala, ola, ala_token, q


def rejoin(client, stack, party, token):
    ws = stack.enter_context(client.websocket_connect(f"/ws/party/{party['code']}/player?reconnect_token={token}"))
    assert receive_until(ws, "joined")["nick"] == "Ala"
    return ws


def answer(ws, q, choice):
    ws.send_json({"type": "answer", "data": {"question_id": q["question_id"], "choice": choice}})
    receive_until(ws, "answer_ack")


def test_reconnect_after_answering_shows_waiting_not_question(client, stack):
    party, host, ala, ola, token, q = start_game(client, stack)
    answer(ala, q, 1)
    ala.close()
    ala2 = rejoin(client, stack, party, token)
    # nie dostaje ponownie pytania (już odpowiedziała), tylko potwierdzenie
    assert ala2.receive_json() == {"type": "answer_ack", "data": {"question_id": q["question_id"]}}


def test_reconnect_during_reveal_gets_own_result(client, stack):
    party, host, ala, ola, token, q = start_game(client, stack)
    answer(ala, q, 1)
    answer(ola, q, 0)
    receive_until(ala, "reveal")
    ala.close()
    reveal = receive_until(rejoin(client, stack, party, token), "reveal")
    assert reveal["your_answer"] == 1 and reveal["your_points"] >= 500 and reveal["rank"] == 1


def test_reconnect_after_game_over_gets_podium(client, stack):
    party, host, ala, ola, token, q = start_game(client, stack)
    for i in range(3):
        if i:
            q = receive_until(ala, "question")
            receive_until(ola, "question")
        answer(ala, q, 1)
        answer(ola, q, 1)
        receive_until(host, "reveal")
        host.send_json({"type": "next_question"})
    receive_until(ala, "game_over")
    ala.close()
    over = receive_until(rejoin(client, stack, party, token), "game_over")
    assert len(over["podium"]) == 2


def test_host_reconnect_during_reveal_gets_reveal(client, stack):
    party, host, ala, ola, token, q = start_game(client, stack)
    answer(ala, q, 1)
    answer(ola, q, 1)
    receive_until(host, "reveal")
    host.close()
    host2 = stack.enter_context(client.websocket_connect(f"/ws/party/{party['code']}/host?token={party['host_token']}"))
    reveal = receive_until(host2, "reveal")
    assert reveal["choice_counts"][1] == 2
