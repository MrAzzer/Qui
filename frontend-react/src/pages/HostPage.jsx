import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { API_URL, WS_URL } from "../config.js";

export default function HostPage() {
  const [party, setParty] = useState(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [players, setPlayers] = useState([]);

  //gdy jest gra to polaczenie z serwerem na zywo
  useEffect(() => {
    if (!party) return;
    const url = `${WS_URL}/ws/party/${party.code}/host?token=${encodeURIComponent(party.host_token)}`;
    const ws = new WebSocket(url);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "lobby_update") setPlayers(msg.data.players);
      if (msg.type === "error") setError(msg.data.message);
    };

    //zamykamy polaczenie gdy strona sie skonczyla
    return () => ws.close();
  }, [party]);

  async function createParty() {
    setError("");
    setStatus("Tworzę grę… (pierwsze uruchomienie serwera może potrwać do minuty)");
    try {
      const res = await fetch(`${API_URL}/api/parties`, { method: "POST" });
      if (!res.ok) throw new Error(`Błąd serwera: ${res.status}`);
      const data = await res.json();
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
    </main>
  );
}