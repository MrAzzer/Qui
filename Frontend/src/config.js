const BACKEND_URL = (
  import.meta.env.VITE_API_URL || "https://qui-backend-y0cp.onrender.com"
).replace(/\/$/, "");

export const API_URL = "";
export const WS_URL = BACKEND_URL.replace(/^http/, "ws");