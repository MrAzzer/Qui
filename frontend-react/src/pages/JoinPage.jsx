import { useParams } from "react-router-dom";

export default function JoinPage() {
  const { code } = useParams();
  return (
    <main>
      <h1>qui? – dołącz do gry</h1>
      <p>Kod gry: {code ?? "brak"}</p>
    </main>
  );
}