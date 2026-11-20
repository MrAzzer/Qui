"""Test obciążeniowy: N graczy przez WebSocket rozgrywa całą grę.

Uruchomienie (backend musi działać, MAX_PLAYERS >= liczba graczy):
    python scripts/load_test.py --url http://localhost:8000 --players 50
    python scripts/load_test.py --url https://qui-backend-y0cp.onrender.com --players 50

Mierzy (czasy w ms, p50 / p95 / max):
- join      — od otwarcia połączenia do komunikatu „joined”
- question  — od wysłania przez hosta start/next do otrzymania pytania przez gracza (rozgłoszenie)
- reveal    — od ostatniej odpowiedzi do otrzymania wyniku rundy przez gracza
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from typing import Dict, List

import httpx
import websockets


def pct(values: List[float], p: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def report(name: str, values: List[float]) -> str:
    ms = [v * 1000 for v in values]
    return (f"{name:<9} n={len(ms):<4} p50={statistics.median(ms):7.1f}  p95={pct(ms, 95):7.1f}  "
            f"max={max(ms):7.1f}")


TRAFFIC = {"messages": 0, "bytes": 0}  # wszystko, co serwer wysłał do graczy i hosta


async def recv_until(ws, type_: str, timeout: float = 30):
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout)
        TRAFFIC["messages"] += 1
        TRAFFIC["bytes"] += len(raw)
        msg = json.loads(raw)
        if msg["type"] == type_:
            return msg["data"]


async def main(url: str, players: int) -> None:
    ws_url = url.replace("http", "ws", 1)
    async with httpx.AsyncClient(timeout=120) as http:
        res = await http.post(f"{url}/api/parties", json={"max_players": players})
        res.raise_for_status()
        party = res.json()
    code = party["code"]
    print(f"party {code}, graczy: {players}")

    timings: Dict[str, List[float]] = {"join": [], "question": [], "reveal": []}
    host = await websockets.connect(f"{ws_url}/ws/party/{code}/host?token={party['host_token']}", max_queue=None)

    async def join(i: int):
        t = time.perf_counter()
        ws = await websockets.connect(f"{ws_url}/ws/party/{code}/player?nick=Gracz{i:03d}", max_queue=None)
        await recv_until(ws, "joined")
        timings["join"].append(time.perf_counter() - t)
        return ws

    t0 = time.perf_counter()
    sockets = await asyncio.gather(*(join(i) for i in range(players)))
    joined_in = time.perf_counter() - t0
    await asyncio.sleep(0.5)  # niech dotrą zaległe lobby_update
    for ws in [host, *sockets]:  # policz to, co czeka w kolejkach po dołączaniu
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), 0.05)
            except asyncio.TimeoutError:
                break
            TRAFFIC["messages"] += 1
            TRAFFIC["bytes"] += len(raw)
    lobby = dict(TRAFFIC)
    print(f"wszyscy dołączyli w {joined_in:.2f} s; "
          f"ruch w lobby: {lobby['messages']} wiadomości, {lobby['bytes'] / 1024:.0f} KB")

    async def play_round(ws, sent_at: float, answered_at: List[float]):
        q = await recv_until(ws, "question")
        timings["question"].append(time.perf_counter() - sent_at)
        await asyncio.sleep(random.uniform(0, 0.3))  # gracze odpowiadają w różnym tempie
        await ws.send(json.dumps({"type": "answer", "data": {"question_id": q["question_id"],
                                                             "choice": random.randrange(len(q["choices"]))}}))
        answered_at.append(time.perf_counter())
        await recv_until(ws, "reveal")
        return time.perf_counter()

    rounds = 0
    command = "start_game"
    while True:
        answered_at: List[float] = []
        sent_at = time.perf_counter()
        await host.send(json.dumps({"type": command}))
        revealed_at = await asyncio.gather(*(play_round(ws, sent_at, answered_at) for ws in sockets))
        last_answer = max(answered_at)
        timings["reveal"].extend(t - last_answer for t in revealed_at)
        rounds += 1
        reveal = await recv_until(host, "reveal")
        command = "next_question"
        if reveal["is_last"]:
            break

    await host.send(json.dumps({"type": "next_question"}))
    over = await recv_until(host, "game_over")
    print(f"rund: {rounds}, zwycięzca: {over['podium'][0]['nick']} ({over['podium'][0]['score']} pkt)\n")
    for name, values in timings.items():
        print(report(name, values))
    print(f"ruch z serwera: {TRAFFIC['messages']} wiadomości, {TRAFFIC['bytes'] / 1024:.0f} KB")

    await asyncio.gather(*(ws.close() for ws in sockets), host.close())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--players", type=int, default=50)
    args = parser.parse_args()
    asyncio.run(main(args.url.rstrip("/"), args.players))
