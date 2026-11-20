import os
import tempfile

# Ustawiane PRZED importem aplikacji: testy zawsze na tymczasowej bazie, nigdy na prawdziwej
_db_dir = tempfile.mkdtemp(prefix="qui-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_dir}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-only-for-tests-0123456789"
os.environ["S3_BUCKET"] = ""  # nigdy prawdziwy bucket z Backend/.env

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.db import create_db_and_tables, get_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.materials.storage import MemoryStorage, get_storage  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Każdy test zaczyna od pustej bazy."""
    SQLModel.metadata.drop_all(get_engine())
    create_db_and_tables()
    yield


@pytest.fixture
def storage():
    return MemoryStorage()


@pytest.fixture
def client(storage):
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, email="ala@example.com", password="tajnehaslo", name="Ala"):
    res = client.post("/api/auth/register", json={"email": email, "password": password, "display_name": name})
    assert res.status_code == 201, res.text
    return res.json()


def auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(client):
    return auth_header(register(client)["access_token"])
