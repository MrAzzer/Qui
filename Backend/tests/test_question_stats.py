"""Statystyki pytań: po każdym odsłonięciu i w podsumowaniu gry."""

from contextlib import ExitStack


def receive_until(ws, type_):
    for _ in range(30):
        msg = ws.receive_json()
        if msg["type"] == type_:
            return msg["data"]
    raise AssertionError(f"no {type_} message")


def test_stats_in_reveal_and_game_over(client):
    party = client.post("/api/parties").json()
    code = party["code"]
    with ExitStack() as stack:
        host = stack.enter_context(client.websocket_connect(f"/ws/party/{code}/host?token={party['host_token']}"))
        players = {}
        for nick in ("Ala", "Ola", "Ela"):
            players[nick] = stack.enter_context(client.websocket_connect(f"/ws/party/{code}/player?nick={nick}"))
            receive_until(players[nick], "joined")
        host.send_json({"type": "start_game"})

        # Pytanie 1: Ala i Ola dobrze (poprawna = 1), Ela źle. Pytania 2–3: tylko Ala odpowiada, host kończy.
        script = [{"Ala": 1, "Ola": 1, "Ela": 0}, {"Ala": 1}, {"Ala": 0}]
        reveals = []
        for answers in script:
            q = receive_until(host, "question")
            for nick, ws in players.items():
                receive_until(ws, "question")
                if nick in answers:
                    ws.send_json({"type": "answer", "data": {"question_id": q["question_id"], "choice": answers[nick]}})
                    receive_until(ws, "answer_ack")
            if len(answers) < len(players):
                host.send_json({"type": "next_question"})
            reveals.append(receive_until(host, "reveal"))
            host.send_json({"type": "next_question"})
        over = receive_until(host, "game_over")

    first = reveals[0]["stats"]
    assert (first["players"], first["answered"], first["correct_count"], first["correct_ratio"]) == (3, 3, 2, 0.67)
    assert first["fastest"]["nick"] == "Ala"  # odpowiedziała pierwsza
    assert first["avg_time_ms"] >= 0
    assert reveals[0]["choice_counts"][:2] == [1, 2]

    second = reveals[1]["stats"]
    assert (second["answered"], second["correct_count"], second["correct_ratio"]) == (1, 1, 0.33)

    stats = over["question_stats"]
    assert [s["question_id"] for s in stats] == ["q1", "q2", "q3"]
    assert stats[2]["correct_ratio"] == 0.0 and stats[2]["fastest"] is None
    # najsłabsze pytania: od najgorszego odsetka poprawnych
    assert [w["question_id"] for w in over["weakest_questions"]] == ["q3", "q2", "q1"]
