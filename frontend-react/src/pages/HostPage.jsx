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

  if (!party) {
    return (
      <main>
        <h1>qui?</h1>
        <button onClick={createParty}>Utwórz grę</button>
        {status && <p>{status}</p>}
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </main>
    );
  }

    //ekran koncowy
  if (gameOver) {
    const medals = ["🥇", "🥈", "🥉"];
    return (
      <main>
        <h1>Koniec gry!</h1>
        <div style={{ display: "flex", justifyContent: "center", gap: 16 }}>
          {gameOver.podium.map((p, i) => (
            <div key={p.id} style={{ padding: 16, borderRadius: 8, background: "#f2f2f2", minWidth: 120 }}>
              <div style={{ fontSize: 40 }}>{medals[i]}</div>
              <strong>{p.nick}</strong>
              <div>{p.score} pkt</div>
            </div>
          ))}
        </div>

        <h2>Pełny ranking</h2>
        <ol>
          {gameOver.leaderboard.map((p) => (
            <li key={p.id}>{p.nick}: {p.score} pkt</li>
          ))}
        </ol>

        <button onClick={() => { sessionStorage.removeItem("qui-host"); window.location.reload(); }}>
          Nowa gra
        </button>
        
      </main>
    );
  }

  // Ekran pytania (i odsłonięcia, gdy przyjdzie reveal)
  if (question) {
    return (
      <main>
        <p>Pytanie {question.index + 1} z {question.total}</p>
        {!reveal && timeLeft !== null && <p style={{ fontSize: 32 }}>⏱ {timeLeft} s</p>}
        <h1>{question.text}</h1>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {question.choices.map((choice, i) => {
            const isWrong = reveal && i !== reveal.correct;
            return (
              <div key={i} style={{ background: COLORS[i], color: "white", padding: 24, borderRadius: 8, fontSize: 22,
                                    opacity: isWrong ? 0.3 : 1 }}>
                {reveal && i === reveal.correct && "✓ "}
                {choice}
                {reveal && <span> ({reveal.choice_counts[i]})</span>}
              </div>
            );
          })}
        </div>

        {!reveal && answerCount && <p>Odpowiedzi: {answerCount.answered} / {answerCount.total}</p>}

        {reveal && (
          <>
            {reveal.explanation && <p>{reveal.explanation}</p>}
            <h2>Ranking</h2>
            <ol>
              {reveal.leaderboard.slice(0, 5).map((p) => (
                <li key={p.id}>{p.nick}: {p.score} pkt</li>
              ))}
            </ol>
          </>
        )}

        <button onClick={() => wsRef.current?.send(JSON.stringify({ type: "next_question", data: {} }))}>
          {reveal ? (reveal.is_last ? "Wyniki końcowe" : "Następne pytanie") : "Pokaż odpowiedź"}
        </button>
      </main>
    );
  }
//generowanie kodu qr z pinu
    const joinUrl = `${window.location.origin}/join/${party.code}`;

  return (
    <main>
      <h1>Kod gry: {party.code}</h1>
      <QRCodeSVG value={joinUrl} size={220} />
      <p>Zeskanuj kod albo wejdź na: {joinUrl}</p>
          <h2>Gracze ({players.length})</h2>
      <ul>
        {players.map((p) => (
          <li key={p.id}>{p.nick}</li>
        ))}
      </ul>
      <p>
        Czas na pytanie:
        {[10, 15, 20].map((s) => (
          <button key={s} onClick={() => setTimeLimit(s)}
                  style={{ marginLeft: 8, fontWeight: timeLimit === s ? "bold" : "normal" }}>
            {s} s {timeLimit === s && "✓"}
          </button>
        ))}
      </p>
      <button onClick={() => wsRef.current?.send(JSON.stringify({ type: "start_game", data: {} }))}
              disabled={players.length === 0}>
        Start gry
      </button>
      {status && <p>{status}</p>}
      {error && <p style={{ color: "crimson" }}>{error}</p>}
    </main>
  );
}