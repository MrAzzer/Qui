import { createElement, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { WS_URL } from "../config.js";

export default function JoinPage() {
  const params = useParams();
  const [code, setCode] = useState(params.code ?? "");
  const [nick, setNick] = useState("");
  const [joining, setJoining] = useState(false); // sprawdza czy gracz kliknął „Dołącz”
  const [me, setMe] = useState(null);            // dane gracza od serwera
  const [players, setPlayers] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!joining) return;
    const url = `${WS_URL}/ws/party/${code}/player?nick=${encodeURIComponent(nick)}`;
    const ws = new WebSocket(url);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "joined") setMe(msg.data);
      if (msg.type === "lobby_update") setPlayers(msg.data.players);
      if (msg.type === "error") setError(msg.data.message);
    };

    //serwer zamknął połączenie (np. zły kod albo zajęty nick)=wracamy do formularza
    ws.onclose = () => {
      setJoining(false);
      setMe(null);
    };

    return () => ws.close();
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

  return (
    <main>
      <h1>Cześć, {me.nick}!</h1>
      <p>Czekamy, aż host wystartuje grę…</p>
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