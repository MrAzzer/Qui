import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { API_URL, WS_URL } from "../config.js";

const COLORS = ["#e21b3c", "#1368ce", "#d89e00", "#26890c"];

export default function HostPage() {
  //po odświeżeniu strony bierzemy zapisaną grę jeśli jest
  const [party, setParty] = useState(() => {
    const saved = sessionStorage.getItem("qui-host");
    return saved ? JSON.parse(saved) : null;
  });
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [players, setPlayers] = useState([]);
  const wsRef = useRef(null);
  const [question, setQuestion] = useState(null);       // aktualne pytanie od serwera
  const [answerCount, setAnswerCount] = useState(null); // ilu graczy już odpowiedziało
  const [reveal, setReveal] = useState(null); // wynik pytania od serwera
  const [timeLimit, setTimeLimit] = useState(20); // czas na pytanie wybrany przez hosta
  const [timeLeft, setTimeLeft] = useState(null); // ile sekund zostało
  const [gameOver, setGameOver] = useState(null); // wyniki końcowe

  //gdy jest gra to polaczenie z serwerem na zywo
  useEffect(() => {
    if (!party) return;
    const url = `${WS_URL}/ws/party/${party.code}/host?token=${encodeURIComponent(party.host_token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "lobby_update") setPlayers(msg.data.players);
      if (msg.type === "error") setError(msg.data.message);
      if (msg.type === "question") {
        setQuestion(msg.data);
        setAnswerCount(null);
        setReveal(null);
      }
      if (msg.type === "reveal") setReveal(msg.data);
      if (msg.type === "game_over") setGameOver(msg.data);
      if (msg.type === "answer_count") setAnswerCount(msg.data);
    };

    // gra wygasła albo zły token: czyścimy zapis i wracamy do „Utwórz grę”
    ws.onclose = (event) => {
      if (event.code === 4404 || event.code === 4401) {
        sessionStorage.removeItem("qui-host");
        setParty(null);
        setError("Ta gra już nie istnieje. Utwórz nową.");
      }
    };

    //zamykamy polaczenie gdy strona sie skonczyla
    return () => ws.close();
  }, [party]);

  // odliczanie czasu na pytanie
  useEffect(() => {
    if (!question || reveal) return;
    let left = Math.min(timeLimit, Math.floor(question.time_left));
    setTimeLeft(left);
    const timer = setInterval(() => {
      left -= 1;
      setTimeLeft(left);
      if (left <= 0) {
        clearInterval(timer);
        // serwer sam kończy pytanie po swoim czasie (20 s) wysyłamy tylko przy krótszym limicie
        if (timeLimit < question.time_limit) {
          wsRef.current?.send(JSON.stringify({ type: "next_question", data: {} }));
        }
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [question, reveal]);

  async function createParty() {
    setError("");
    setStatus("Tworzę grę… (pierwsze uruchomienie serwera może potrwać do minuty)");
    try {
      const res = await fetch(`${API_URL}/api/parties`, { method: "POST" });
      if (!res.ok) throw new Error(`Błąd serwera: ${res.status}`);
      const data = await res.json();
      sessionStorage.setItem("qui-host", JSON.stringify(data)); // zapamiętujemy grę
      setParty(data);
      setStatus("");
    } catch (e) {
      setError(e.message);
      setStatus("");
    }
  }

  // ekran startowy
  if (!party) {
    return (
      <div className="lobby" style={{ justifyContent: "center" }}>
        <h1 style={{ fontSize: 72, margin: 0 }}>qui?</h1>
        <button className="start-btn" onClick={() => (window.location.href = "/start")}>Utwórz QUIZ</button>
        {status && <p>{status}</p>}
        {error && <p style={{ color: "#ffd23f" }}>{error}</p>}
      </div>
    );
  }

  // ekran końcowy: podium i pełny ranking
  if (gameOver) {
    const medals = ["🥇", "🥈", "🥉"];
    return (
      <div className="lobby">
        <h1 style={{ margin: 0 }}>Koniec gry! 🏆</h1>
        <div className="podium">
          {gameOver.podium.map((p, i) => (
            <div key={p.id} className={`podium-place place-${i + 1}`}>
              <div style={{ fontSize: 40 }}>{medals[i]}</div>
              <strong>{p.nick}</strong>
              <div>{p.score} pkt</div>
            </div>
          ))}
        </div>
        <div className="lobby-card">
          <h2 style={{ marginTop: 0 }}>Pełny ranking</h2>
          <ol className="rank-list">
            {gameOver.leaderboard.map((p, i) => (
              <li key={p.id}><span>{i + 1}. {p.nick}</span><strong>{p.score} pkt</strong></li>
            ))}
          </ol>
        </div>
        <button className="start-btn" onClick={() => { sessionStorage.removeItem("qui-host"); window.location.reload(); }}>
          Nowa gra
        </button>
      </div>
    );
  }

  // ekran pytania (i odsłonięcia, gdy przyjdzie reveal)
  if (question) {
    return (
      <div className="lobby">
        <div className="q-top">
          <span>Pytanie {question.index + 1} / {question.total}</span>
          {!reveal && timeLeft !== null && <span className="timer">{timeLeft}</span>}
          <span>{!reveal && answerCount ? `Odpowiedzi: ${answerCount.answered}/${answerCount.total}` : ""}</span>
        </div>

        <div className="lobby-card" style={{ maxWidth: 900 }}>
          <h1 style={{ margin: 0 }}>{question.text}</h1>
        </div>

        <div className="q-tiles">
          {question.choices.map((choice, i) => {
            const isWrong = reveal && i !== reveal.correct;
            return (
              <div key={i} className={`tile ${isWrong ? "dim" : ""}`} style={{ background: COLORS[i] }}>
                <span>{reveal && i === reveal.correct && "✓ "}{choice}</span>
                {reveal && <span className="tile-count">{reveal.choice_counts[i]}</span>}
              </div>
            );
          })}
        </div>

        {reveal && reveal.explanation && (
          <div className="lobby-card" style={{ maxWidth: 900 }}>{reveal.explanation}</div>
        )}

        {reveal && (
          <div className="lobby-card">
            <h2 style={{ marginTop: 0 }}>Top 5</h2>
            <ol className="rank-list">
              {reveal.leaderboard.slice(0, 5).map((p, i) => (
                <li key={p.id}><span>{i + 1}. {p.nick}</span><strong>{p.score} pkt</strong></li>
              ))}
            </ol>
          </div>
        )}

        <button className="start-btn" onClick={() => wsRef.current?.send(JSON.stringify({ type: "next_question", data: {} }))}>
          {reveal ? (reveal.is_last ? "Wyniki końcowe" : "Następne pytanie") : "Pokaż odpowiedź"}
        </button>
      </div>
    );
  }

  //generowanie kodu qr z pinu
  const joinUrl = `${window.location.origin}/join/${party.code}`;

  return (
    <div className="lobby">
      <div className="lobby-card">
        <p style={{ margin: 0, fontWeight: 600 }}>Kod gry</p>
        <div className="lobby-code">{party.code}</div>
        <QRCodeSVG value={joinUrl} size={200} />
        <p className="lobby-url">Zeskanuj albo wejdź na: {joinUrl}</p>
      </div>

      <h2 style={{ margin: 0 }}>
        {players.length === 0 ? "Czekamy na graczy" : `Dołączyło: ${players.length}`}
      </h2>
      {players.length === 0 && (
        <div className="waiting"><span></span><span></span><span></span></div>
      )}

      <div className="lobby-chips">
        {players.map((p, i) => (
          <div className="chip" key={p.id}>
            <span className="chip-avatar" style={{ background: COLORS[i % COLORS.length] }}>
              {p.nick[0]?.toUpperCase()}
            </span>
            {p.nick}
          </div>
        ))}
      </div>

      <div className="time-pick">
        <span>Czas na pytanie: </span>
        {[10, 15, 20].map((s) => (
          <button key={s} className={timeLimit === s ? "active" : ""} onClick={() => setTimeLimit(s)}>
            {s} s
          </button>
        ))}
      </div>

      <button className="start-btn" disabled={players.length === 0}
              onClick={() => wsRef.current?.send(JSON.stringify({ type: "start_game", data: {} }))}>
        Start gry
      </button>
      {error && <p style={{ color: "#ffd23f" }}>{error}</p>}
    </div>
  );
}