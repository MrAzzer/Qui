import { API_URL } from "../config.js";

export default function HostPage() {
  return (
    <main>
      <h1>qui? – host</h1>
      <p>Backend: {API_URL}</p>
    </main>
  );
}