const API_URL = (window.QUI_API_URL || `${location.protocol}//${location.hostname}:8000`).replace(/\/$/, "");
const WS_URL = API_URL.replace(/^http/, "ws");

const $ = (sel) => document.querySelector(sel);

function showScreen(id) {
  document.querySelectorAll("[data-screen]").forEach((el) => {
    el.hidden = el.id !== id;
  });
}

function connect(path, onMessage, onClose) {
  const ws = new WebSocket(WS_URL + path);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    onMessage(msg.type, msg.data || {});
  };
  ws.onclose = onClose;
  ws.sendMsg = (type, data = {}) => ws.send(JSON.stringify({ type, data }));
  return ws;
}

let countdownTimer = null;
function startCountdown(el, seconds) {
  clearInterval(countdownTimer);
  const end = Date.now() + seconds * 1000;
  const tick = () => {
    const left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
    el.textContent = left;
    if (left === 0) clearInterval(countdownTimer);
  };
  tick();
  countdownTimer = setInterval(tick, 250);
}
function stopCountdown() {
  clearInterval(countdownTimer);
}

function renderLeaderboard(ol, rows, highlightId) {
  ol.replaceChildren(
    ...rows.map((row) => {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = row.nick;
      const score = document.createElement("strong");
      score.textContent = row.score;
      li.append(name, score);
      if (row.id === highlightId) li.classList.add("me");
      return li;
    })
  );
}

const CHOICE_CLASSES = ["c0", "c1", "c2", "c3"];
