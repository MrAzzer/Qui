const BACKEND_URL = import.meta.env.VITE_API_URL;

//na ten moment lokalnie zapytania idą przez Vite
export const API_URL = import.meta.env.DEV ? "" : BACKEND_URL;
export const WS_URL = BACKEND_URL.replace(/^http/, "ws");