import pytest

from app.auth.security import create_access_token
from app.db import _normalize_url
from tests.conftest import auth_header, register


def login(client, email, password):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def test_register_returns_token_and_user(client):
    data = register(client, email="Ala@Example.com")
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "ala@example.com"  # email zapisany małymi literami
    assert "password_hash" not in data["user"]

    me = client.get("/api/auth/me", headers=auth_header(data["access_token"]))
    assert me.status_code == 200
    assert me.json()["display_name"] == "Ala"


def test_duplicate_email_rejected(client):
    register(client)
    res = client.post("/api/auth/register",
                      json={"email": "ALA@example.com", "password": "innehaslo1", "display_name": "Ala2"})
    assert res.status_code == 409


@pytest.mark.parametrize("body", [
    {"email": "nie-email", "password": "tajnehaslo", "display_name": "Ala"},
    {"email": "a@example.com", "password": "krotkie", "display_name": "Ala"},
    {"email": "a@example.com", "password": "tajnehaslo", "display_name": "   "},
])
def test_register_validates_input(client, body):
    assert client.post("/api/auth/register", json=body).status_code == 422


def test_login(client):
    register(client)
    ok = login(client, "ALA@example.com", "tajnehaslo")
    assert ok.status_code == 200
    assert client.get("/api/auth/me", headers=auth_header(ok.json()["access_token"])).status_code == 200

    # zły email i złe hasło dają ten sam komunikat
    wrong_pass = login(client, "ala@example.com", "zlehaslo1")
    wrong_mail = login(client, "nikt@example.com", "tajnehaslo")
    assert wrong_pass.status_code == wrong_mail.status_code == 401
    assert wrong_pass.json() == wrong_mail.json()


def test_protected_endpoints_need_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=auth_header("zepsuty")).status_code == 401
    # token poprawny, ale użytkownika nie ma w bazie
    assert client.get("/api/auth/me", headers=auth_header(create_access_token(999))).status_code == 401
    assert client.post("/api/quizzes/generate", json={"text": "x" * 40}).status_code == 401


def test_party_works_for_guests_and_rejects_bad_token(client):
    assert client.post("/api/parties").status_code == 201
    assert client.post("/api/parties", headers=auth_header("zepsuty")).status_code == 401


@pytest.mark.parametrize("url,expected", [
    ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("postgresql://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
    ("sqlite:///./qui.db", "sqlite:///./qui.db"),
])
def test_database_url_normalized(url, expected):
    assert _normalize_url(url) == expected
