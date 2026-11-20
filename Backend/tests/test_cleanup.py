"""Sprzątanie party z pamięci: porzucone lobby, zakończone gry, twardy limit wieku."""

import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.config import get_settings
from app.party.manager import manager
from app.party.party import CLOSE_EXPIRED, Party
from app.quiz.sample import get_sample_questions

S = get_settings()
MIN = 60


def party(**kw) -> Party:
    return Party(code="000000", host_token="t", questions=get_sample_questions(), **kw)


def expired(p: Party, after: float) -> bool:
    return p.is_expired(p.created_at + after, S.party_idle_ttl, S.party_finished_ttl, S.party_max_age)


def test_party_nobody_ever_joined_expires_after_idle_ttl():
    p = party()
    assert not expired(p, S.party_idle_ttl - 1)
    assert expired(p, S.party_idle_ttl + 1)


def test_connected_party_is_kept_until_max_age():
    p = party()
    p.host_ws = object()  # ktoś jest połączony
    p._update_idle()
    assert not expired(p, S.party_idle_ttl * 10)
    assert expired(p, S.party_max_age + 1)


def test_finished_game_expires_even_with_open_tabs():
    p = party()
    p.host_ws = object()
    p._update_idle()
    p.finished_at = p.created_at + 5 * MIN
    assert not expired(p, 5 * MIN + S.party_finished_ttl - 1)
    assert expired(p, 5 * MIN + S.party_finished_ttl + 1)


def test_cleanup_removes_expired_and_closes_sockets(client):
    keep = client.post("/api/parties").json()["code"]
    old = client.post("/api/parties").json()
    with client.websocket_connect(f"/ws/party/{old['code']}/player?nick=Ala") as ws:
        assert ws.receive_json()["type"] == "joined"
        manager.get(old["code"]).created_at -= S.party_max_age + 1  # „stare” party

        removed = client.portal.call(manager.cleanup)
        assert removed == [old["code"]]
        assert client.get(f"/api/parties/{old['code']}").status_code == 404
        assert client.get(f"/api/parties/{keep}").status_code == 200
        with pytest.raises(WebSocketDisconnect) as exc:
            while True:
                ws.receive_json()
        assert exc.value.code == CLOSE_EXPIRED


def test_abandoned_lobby_removed_after_everyone_leaves(client):
    code = client.post("/api/parties").json()["code"]
    with client.websocket_connect(f"/ws/party/{code}/player?nick=Ala") as ws:
        ws.receive_json()
        assert manager.get(code).idle_since is None  # ktoś jest
    assert manager.get(code).idle_since is not None  # wszyscy wyszli
    assert client.portal.call(manager.cleanup, time.monotonic() + S.party_idle_ttl + 1) == [code]
