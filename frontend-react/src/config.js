const BACKEND_URL = (
  import.meta.env.VITE_API_URL || "https://qui-backend-y0cp.onrender.com"
).replace(/\/$/, "");

// lokalnie (npm run dev) zapytania idą przez proxy Vite, na Vercelu prosto do backendu
export const API_URL = import.meta.env.DEV ? "" : BACKEND_URL;
export const WS_URL = BACKEND_URL.replace(/^http/, "ws");