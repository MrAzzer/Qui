import { Routes, Route } from "react-router-dom";
import HostPage from "./pages/HostPage.jsx";
import JoinPage from "./pages/JoinPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HostPage />} />
      <Route path="/join" element={<JoinPage />} />
      <Route path="/join/:code" element={<JoinPage />} />
    </Routes>
  );
}