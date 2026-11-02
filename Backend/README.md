# Qui — Backend

## Start

```bash
cd Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pytest -q
```

Dokumentacja API (Swagger): http://localhost:8000/docs

**Telefony:** `localhost` nie działa z telefonu. Telefon musi być w tej samej sieci Wi-Fi, a frontend łączy się z backendem
przez IP laptopa (`ipconfig getifaddr en0` na macOS), np. `ws://192.168.1.20:8000`. W `.env` ustaw
`FRONTEND_URL=http://<IP>:5173`, żeby `join_url` (do kodu QR) prowadził pod adres osiągalny z telefonu.

## REST

| Metoda | Ścieżka | Odpowiedź |
|---|---|---|
| `POST` | `/api/parties` | `201 { code, host_token, join_url }` — na razie zawsze z przykładowym quizem |
| `GET` | `/api/parties/{code}` | `{ code, state, joinable, player_count, question_count }` lub `404` |

## WebSocket

- Host: `ws://<backend>/ws/party/{code}/host?token=<host_token>`
- Gracz: `ws://<backend>/ws/party/{code}/player?nick=<nick>`
- Gracz po zerwaniu połączenia: `ws://<backend>/ws/party/{code}/player?reconnect_token=<token>` — zachowuje punkty

Każda wiadomość: `{ "type": "...", "data": { ... } }`.

### Klient → serwer

| type | kto | data |
|---|---|---|
| `start_game` | host | — |
| `next_question` | host | — (w trakcie pytania: kończy je od razu; po odsłonięciu: następne pytanie / koniec) |
| `kick_player` | host | `{ player_id }` |
| `answer` | gracz | `{ question_id, choice }` (`choice` = indeks odpowiedzi) |

### Serwer → klient

| type | do kogo | data |
|---|---|---|
| `host_joined` | host | `{ code, state, joinable, player_count, question_count }` |
| `joined` | gracz | `{ player_id, nick, reconnect_token, score, state }` — zapisz `reconnect_token` w `localStorage` |
| `lobby_update` | wszyscy | `{ players: [{ id, nick, score, connected }] }` |
| `question` | wszyscy | `{ question_id, index, total, text, choices, time_limit, time_left }` |
| `answer_ack` | gracz | `{ question_id }` |
| `answer_count` | host | `{ answered, total }` |
| `reveal` | host | `{ question_id, correct, explanation, hint, choice_counts, is_last, leaderboard }` |
| `reveal` | gracz | jak wyżej + `{ your_answer, your_points, score, streak, rank }`, `leaderboard` = top 5 |
| `game_over` | wszyscy | `{ podium, leaderboard, weakest_questions: [{ question_id, text, correct_answer, hint, correct_ratio }] }` |
| `kicked` | gracz | — |
| `error` | jeden klient | `{ message, request? }` |

Kody zamknięcia: `4400` zły nick / gra już trwa / party pełne, `4401` zły token hosta, `4403` wyrzucony,
`4404` brak party, `4409` to samo konto połączyło się z innego urządzenia.

## Kontrakt z AI (Marvin)

Pytanie = `app/quiz/schemas.py::Question`:
`{ id, text, choices[2..4], correct, explanation, hint, time_limit }`. Do czasu podpięcia NVIDIA używamy `app/quiz/sample.py`.
