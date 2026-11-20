from app import health
from app.materials.storage import MemoryStorage


def test_health_is_fast_and_does_not_need_db(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["version"] == health.VERSION
    assert set(body) == {"status", "version", "commit", "uptime_s", "active_parties"}


def test_full_health_checks_services(client, monkeypatch):
    monkeypatch.setattr(health, "get_storage", lambda: MemoryStorage())
    monkeypatch.setattr(health.get_settings(), "llm_api_key", "x")
    res = client.get("/health/full")
    assert res.status_code == 200, res.json()
    checks = res.json()["checks"]
    assert checks["database"]["ok"] and checks["database"]["engine"] == "sqlite"
    assert checks["storage"] == {"ok": True, "ms": checks["storage"]["ms"], "configured": True}


def test_full_health_reports_broken_service_as_503(client, monkeypatch):
    class Broken(MemoryStorage):
        def check(self):
            raise ConnectionError("bucket down")

    monkeypatch.setattr(health, "get_storage", lambda: Broken())
    res = client.get("/health/full")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert body["checks"]["storage"] == {"ok": False, "ms": body["checks"]["storage"]["ms"], "error": "ConnectionError"}
