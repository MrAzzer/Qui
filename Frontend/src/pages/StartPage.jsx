import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { API_URL } from "../config.js";
 
export default function StartPage() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [count, setCount] = useState(5);
  const [difficulty, setDifficulty] = useState("medium");
  const [timeLimit, setTimeLimit] = useState(20);
  const [quiz, setQuiz] = useState(null); // { id, questions }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
 
  // wysyłamy materiał do modułu AI dostajemy pytania do podglądu
  async function generate() {
    setLoading(true); setError(""); setQuiz(null);
    try {
      const res = await fetch(`${API_URL}/api/quizzes/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, count, difficulty, time_limit: timeLimit }),
      });
      if (!res.ok) throw new Error(res.status === 422 ? "Tekst jest za krótki (min. 30 znaków)." : "Nie udało się wygenerować quizu, spróbuj jeszcze raz.");
      setQuiz(await res.json());
    } catch (e) { setError(e.message); }
    setLoading(false);
  }
 
  // tworzenie gry z wygenerowanym quizem i idziemy do lobby hosta
  async function createGame() {
    setLoading(true); setError("");
    try {
      const res = await fetch(`${API_URL}/api/parties`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quiz_id: quiz.id }),
      });
      if (!res.ok) throw new Error("Nie udało się utworzyć gry.");
      sessionStorage.setItem("qui-host", JSON.stringify(await res.json()));
      navigate("/");
    } catch (e) { setError(e.message); setLoading(false); }
  }
 
  return (
    <div className="lobby">
      <div className="lobby-card">
        <h1>Nowy quiz</h1>
        <textarea
          rows={8}
          placeholder="Wklej tu materiał (notatki, fragment wykładu)…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          style={{ width: "100%", borderRadius: 12, padding: 12, boxSizing: "border-box" }}
        />
        <p className="lobby-url">{text.length} znaków (min. 30)</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center", margin: "12px 0" }}>
          <label>Pytań <input type="number" min={1} max={20} value={count} onChange={(e) => setCount(+e.target.value)} style={{ width: 50 }} /></label>
          <label>Trudność <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            <option value="easy">łatwy</option><option value="medium">średni</option><option value="hard">trudny</option>
          </select></label>
          <label>Czas (s) <input type="number" min={5} max={120} value={timeLimit} onChange={(e) => setTimeLimit(+e.target.value)} style={{ width: 55 }} /></label>
        </div>
        <button onClick={generate} disabled={loading || text.trim().length < 30}>
          {loading && !quiz ? "Generuję…" : "Generuj pytania"}
        </button>
        {error && <p style={{ color: "#e21b3c" }}>{error}</p>}
      </div>
 
      {quiz && (
        <div className="lobby-card" style={{ textAlign: "left" }}>
          <h2>Podgląd ({quiz.questions.length} pytań)</h2>
          <ol>
            {quiz.questions.map((q) => (
              <li key={q.id} style={{ marginBottom: 12 }}>
                <b>{q.text}</b>
                <ul>{q.choices.map((c, i) => <li key={i} style={{ fontWeight: i === q.correct ? 700 : 400 }}>{i === q.correct ? "✅ " : ""}{c}</li>)}</ul>
              </li>
            ))}
          </ol>
          <button onClick={createGame} disabled={loading}>Utwórz grę z tym quizem</button>
          <button onClick={generate} disabled={loading} style={{ marginLeft: 8 }}>Wygeneruj ponownie</button>
        </div>
      )}
    </div>
  );
}
 