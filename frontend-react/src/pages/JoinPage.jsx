import { createElement, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { WS_URL } from "../config.js";

const COLORS = ["#e21b3c", "#1368ce", "#d89e00", "#26890c"];

export default function JoinPage() {
  const params = useParams();
  const [code, setCode] = useState(params.code ?? "");
  const [nick, setNick] = useState("");
  // Łączymy się, gdy gracz kliknie „Dołącz” albo gdy po odświeżeniu mamy zapisany bilet powrotu
  const [joining, setJoining] = useState(
    () => Boolean(params.code && localStorage.getItem(`qui-player-${params.code}`))
  );
  const [me, setMe] = useState(null);            // dane gracza od serwera
  const [players, setPlayers] = useState([]);
  const [error, setError] = useState("");
  const [question, setQuestion] = useState(null); // aktualne pytanie
  const [answered, setAnswered] = useState(false); // czy gracz już odpowiedział
  const [reveal, setReveal] = useState(null); // wynik po pytaniu
  const [gameOver, setGameOver] = useState(null); // wyniki końcowe

  const wsRef = useRef(null);

  useEffect(() => {
    if (!joining) return;
    const key = `qui-player-${code}`;
    let token = localStorage.getItem(key); // bilet powrotu jeśli już graliśmy
    let ws;
    let closedByUs = false;
    let retryTimer;

    function connect() {
      const query = token
        ? `reconnect_token=${encodeURIComponent(token)}`
        : `nick=${encodeURIComponent(nick)}`;
      ws = new WebSocket(`${WS_URL}/ws/party/${code}/player?${query}`);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "joined") {
          setMe(msg.data);
          setError("");
          token = msg.data.reconnect_token;
          localStorage.setItem(key, token); // zapisujemy bilet na wypadek zerwania
        }
        if (msg.type === "lobby_update") setPlayers(msg.data.players);
        if (msg.type === "error") setError(msg.data.message);
        if (msg.type === "question") {
          setQuestion(msg.data);
          setAnswered(false);
          setReveal(null);
        }
        if (msg.type === "answer_ack") setAnswered(true);
        if (msg.type === "reveal") setReveal(msg.data);
        if (msg.type === "game_over") {
          setGameOver(msg.data);
          localStorage.removeItem(key); // gra skończona, bilet niepotrzebny
          token = null;
        }
      };

      ws.onclose = (event) => {
        if (closedByUs) return;
        // 4400: zły nick albo gra już trwa, 4403: usunięty przez hosta, 4404: nie ma takiej gry
        if ([4400, 4403, 4404].includes(event.code)) {
          localStorage.removeItem(key);
          setJoining(false);
          setMe(null);
          if (event.code === 4403) setError("Host usunął Cię z gry.");
          if (event.code === 4404) setError("Nie ma gry o takim kodzie.");
          return;
        }
        if (event.code === 4409) {
          setError("Grasz już w innej karcie.");
          return;
        }
        // Inny powód (zgasł ekran, słaby internet) próbujemy wrócić za 1,5 s
        if (token) {
          retryTimer = setTimeout(connect, 1500);
        } else {
          setJoining(false);
          setMe(null);
        }
      };
    }

    connect();
    return () => {
      closedByUs = true;
      clearTimeout(retryTimer);
      ws?.close();
    };
  }, [joining]);

  function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setJoining(true);
  }

  if (!me) {
    return (
      <main>
        <h1>qui? – dołącz do gry</h1>
        <form onSubmit={handleSubmit}>
          <TextField placeholder="Kod gry" value={code} onChange={setCode} maxLength={6} />
          <TextField placeholder="Twój nick" value={nick} onChange={setNick} maxLength={20} />
          <button type="submit" disabled={joining}>Dołącz</button>
        </form>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </main>
    );
  }

  // Ekran końcowy u gracza: jego miejsce, wynik i podium
  if (gameOver) {
    const myResult = gameOver.leaderboard.find((p) => p.id === me.player_id);
    const medals = ["🥇", "🥈", "🥉"];
    return (
      <main>
        <h1>Koniec gry!</h1>
        {myResult && (
          <>
            <p style={{ fontSize: 48, margin: 0 }}>{medals[myResult.rank - 1] ?? `#${myResult.rank}`}</p>
            <h2>Zajmujesz {myResult.rank}. miejsce</h2>
            <p>Twój wynik: {myResult.score} pkt</p>
          </>
        )}
        <h3>Podium</h3>
        <ol>
          {gameOver.podium.map((p) => (
            <li key={p.id}>{p.nick}: {p.score} pkt</li>
          ))}
        </ol>
      </main>
    );
  }

  // Ekran pytania u gracza
  if (question) {
    function answer(i) {
      wsRef.current?.send(JSON.stringify({
        type: "answer",
        data: { question_id: question.question_id, choice: i },
      }));
    }

    // po odsłonięciu zielony ekran gdy dobrze, czerwony gdy źle
    if (reveal) {
      const isCorrect = reveal.your_answer === reveal.correct;
      return (
        <main style={{ background: isCorrect ? "#26890c" : "#e21b3c", color: "white", padding: 24, borderRadius: 8 }}>
          <h1>{reveal.your_answer === null ? "Brak odpowiedzi" : isCorrect ? "Dobrze! ✓" : "Źle ✗"}</h1>
          <p>Poprawna odpowiedź: {question.choices[reveal.correct]}</p>
          <p>+{reveal.your_points} pkt</p>
        </main>
      );
    }

    return (
      <main>
        <h2>{question.text}</h2>
        {answered ? (
          <p>Odpowiedź wysłana! Czekamy na resztę…</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {question.choices.map((choice, i) => (
              <button key={i} onClick={() => answer(i)}
                style={{ background: COLORS[i], color: "white", padding: 24, fontSize: 20, border: "none", borderRadius: 8 }}>
                {choice}
              </button>
            ))}
          </div>
        )}
      </main>
    );
  }

  return (
    <main>
      <h1>Cześć, {me.nick}!</h1>
      <p>{me.state === "lobby" ? "Czekamy, aż host wystartuje grę…" : "Wróciłeś do gry! Poczekaj na następne pytanie…"}</p>
      <h2>W lobby ({players.length})</h2>
      <ul>
        {players.map((p) => (
          <li key={p.id}>{p.nick}</li>
        ))}
      </ul>
    </main>
  );
}

//pole tekstowe (to samo co zwykły tag input w JSX)
function TextField({ value, onChange, ...rest }) {
  return createElement("input", {
    ...rest,
    value,
    required: true,
    onChange: (e) => onChange(e.target.value),
  });
}