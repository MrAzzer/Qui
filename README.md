# Qui
Kahoot like app for studying

Użytkownicy wrzucają materiały z zajęć (PDF, notatki, slajdy), AI generuje z nich quiz,
a grupa gra razem w czasie rzeczywistym — każdy na swoim telefonie.

# Stack
Frontend: React — dwa widoki:
**Host** (duży ekran / rzutnik) 
**Gracz** (telefon)
AI: NVIDIA API (`integrate.api.nvidia.com`, API kompatybilne z OpenAI) — generowanie pytań i wskazówek
Backend: Python + FastAPI, WebSockets, Sqlite 

---

# Architektura

```
 ┌──────────────┐  REST (upload, tworzenie gry)   ┌─────────────────────────────┐
 │  Host (web)  │ ──────────────────────────────▶ │          FastAPI            │
 │ duży ekran   │ ◀════════ WebSocket ══════════▶ │                             │
 └──────────────┘                                 │  materials/  → parsowanie   │
        │ wyświetla kod QR                        │  quiz/       → NVIDIA API   │──▶ NVIDIA API
        ▼                                         │  party/      → pokoje, stan │
 ┌──────────────┐                                 │  scoring/    → punkty       │
 │ Gracz (tel.) │ ◀════════ WebSocket ══════════▶ │                             │
 │ skanuje QR   │                                 └──────────────┬──────────────┘
 └──────────────┘                                                │
                                                              SQLite 
```

## Przepływ gry

1. **Upload** — host wrzuca materiały (`PDF`, `DOCX`, `TXT`, `MD`). Backend wyciąga tekst i dzieli go na fragmenty.
2. **Generowanie** — backend wysyła fragmenty do NVIDIA API i dostaje pytania (JSON) z odpowiedziami i wskazówkami.
   Host może przejrzeć i usunąć/edytować pytania przed grą.
3. **Party** — host tworzy party, backend zwraca 6-cyfrowy kod. Frontend hosta pokazuje kod QR z linkiem
   `https://<frontend>/join/<KOD>`.
4. **Dołączanie** — gracz skanuje QR telefonem → otwiera się strona → wpisuje nick → łączy się przez WebSocket.
5. **Gra** — host startuje; backend rozsyła pytanie wszystkim, liczy czas, zbiera odpowiedzi.
6. **Odsłonięcie** — po upływie czasu (lub gdy wszyscy odpowiedzą): poprawna odpowiedź, punkty, ranking **i wskazówka jak zapamiętać**.
7. **Koniec** — podium + podsumowanie: na które pytania grupa odpowiadała najsłabiej (do powtórki).

---

# Backend — moduły

```
backend/
├── app/
│   ├── main.py            # FastAPI app, CORS, routery
│   ├── config.py          # zmienne środowiskowe (NVIDIA_API_KEY itd.)
│   ├── db.py              # SQLModel / SQLAlchemy
│   ├── materials/         # upload + ekstrakcja tekstu (pypdf, python-docx) + chunking
│   ├── quiz/              # klient NVIDIA API, prompty, walidacja JSON pytań
│   ├── party/             # menedżer pokoi w pamięci, obsługa WebSocket, maszyna stanów gry
│   └── scoring/           # liczenie punktów, ranking, statystyki
└── tests/
```

## REST API

| Metoda | Ścieżka | Opis |
|---|---|---|
| `POST` | `/api/materials` | Upload pliku (multipart). Zwraca `material_id`. |
| `POST` | `/api/quizzes` | `{ material_ids, question_count, difficulty, language }` → generuje quiz. Zwraca `quiz_id`. |
| `GET` | `/api/quizzes/{id}` | Pytania do podglądu przez hosta. |
| `PATCH` | `/api/quizzes/{id}/questions/{qid}` | Edycja / usunięcie pytania. |
| `POST` | `/api/parties` | `{ quiz_id }` → `{ code, host_token }`. |
| `GET` | `/api/parties/{code}` | Czy party istnieje i czy przyjmuje graczy (sprawdzane po zeskanowaniu QR). |

## WebSocket

- Host: `ws://<backend>/ws/party/{code}/host?token=<host_token>`
- Gracz: `ws://<backend>/ws/party/{code}/player?nick=<nick>`

Każda wiadomość to JSON `{ "type": "...", "data": { ... } }`.

## Stan party (maszyna stanów)

```
LOBBY ──start_game──▶ QUESTION ──czas minął / wszyscy odpowiedzieli──▶ REVEAL
                         ▲                                                │
                         └──────────────next_question─────────────────────┤
                                                                          ▼
                                                     (ostatnie pytanie) GAME_OVER
```

# Punktacja

- Zła odpowiedź / brak odpowiedzi: `0`
- Dobra odpowiedź: `round(1000 * (1 - 0.5 * czas_odpowiedzi / limit_czasu))` → od 500 do 1000 pkt (szybciej = więcej)
- Seria (streak): +100 za każdą kolejną dobrą odpowiedź z rzędu, maks. +500
- Czas mierzy **serwer** (od wysłania `question` do otrzymania `answer`), nie telefon — żeby nie dało się oszukać.
- Liczy się tylko pierwsza odpowiedź gracza na dane pytanie.

# Uruchomienie (dev)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # NVIDIA_API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`.env` jest w `.gitignore` — **nigdy nie commitujemy klucza NVIDIA**.

---

## Kolejność prac (MVP)

1. Party + WebSocket z pytaniami wpisanymi na sztywno → test na kilku telefonach. Równolegle Marvin dopracowuje prompty na przykładowych materiałach, a Natalia robi widoki na mockowanych danych.
2. Punktacja i ranking.
3. Upload PDF/TXT + generowanie pytań przez NVIDIA API.
4. Wskazówki do zapamiętywania i podsumowanie najsłabszych pytań.
5. Reconnect, edycja pytań przez hosta, kolejne formaty plików.
