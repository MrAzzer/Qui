import pytest

from app.materials.extract import MAX_FILE_BYTES
from app.quiz.router import get_generator
from app.quiz.sample import get_sample_questions
from tests.conftest import auth_header, register

NOTES = "Fotosynteza zachodzi w chloroplastach. Produktem jest glukoza i tlen.\nFaza jasna: tylakoidy."


def upload(client, headers, name="notatki.txt", data=NOTES.encode()):
    return client.post("/api/materials", headers=headers, files={"file": (name, data, "text/plain")})


def test_upload_txt_and_list(client, auth_headers):
    res = upload(client, auth_headers)
    assert res.status_code == 201
    m = res.json()
    assert m["filename"] == "notatki.txt"
    assert m["char_count"] == len(NOTES)
    assert m["preview"].startswith("Fotosynteza")

    assert client.get(f"/api/materials/{m['id']}", headers=auth_headers).json()["id"] == m["id"]
    assert [x["id"] for x in client.get("/api/materials", headers=auth_headers).json()] == [m["id"]]


def test_windows_1250_polish_file(client, auth_headers):
    res = upload(client, auth_headers, data="Zażółć gęślą jaźń — notatki z historii".encode("cp1250"))
    assert res.status_code == 201
    assert res.json()["preview"].startswith("Zażółć gęślą jaźń")


@pytest.mark.parametrize("name,data,status", [
    ("slajdy.pptx", b"PK...", 422),  # format jeszcze nieobsługiwany
    ("puste.txt", b"   \n  ", 422),
    ("duzy.txt", b"a" * (MAX_FILE_BYTES + 1), 413),
])
def test_bad_files_rejected(client, auth_headers, name, data, status):
    assert upload(client, auth_headers, name=name, data=data).status_code == status


def test_upload_requires_login(client):
    assert upload(client, {}).status_code == 401


def test_materials_are_private(client, auth_headers):
    material_id = upload(client, auth_headers).json()["id"]
    other = auth_header(register(client, email="ola@example.com", name="Ola")["access_token"])
    assert client.get(f"/api/materials/{material_id}", headers=other).status_code == 404
    assert client.post("/api/quizzes/generate", headers=other,
                       json={"material_id": material_id}).status_code == 404


def test_generate_quiz_from_material(client, auth_headers):
    seen = {}

    def fake_generator(text, count, difficulty, time_limit):
        seen["text"] = text
        return get_sample_questions()[:count]

    client.app.dependency_overrides[get_generator] = lambda: fake_generator
    material_id = upload(client, auth_headers, name="Biologia - fotosynteza.txt").json()["id"]
    res = client.post("/api/quizzes/generate", headers=auth_headers, json={"material_id": material_id, "count": 2})
    assert res.status_code == 201
    assert seen["text"] == NOTES
    assert res.json()["title"] == "Biologia - fotosynteza.txt"  # tytuł z nazwy pliku


@pytest.mark.parametrize("body", [{}, {"text": NOTES * 2, "material_id": "x"}])
def test_generate_needs_exactly_one_source(client, auth_headers, body):
    assert client.post("/api/quizzes/generate", headers=auth_headers, json=body).status_code == 422
