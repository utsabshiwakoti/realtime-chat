import axios from "axios";

const API_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.DEV ? "http://localhost:8000" : window.location.origin);
export const WS_URL = API_URL.replace(/^http/, "ws");

const api = axios.create({ baseURL: API_URL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && localStorage.getItem("token")) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// Open a WebSocket with a fresh one-time ticket (the JWT itself never goes in a URL).
export async function openSocket(path) {
  const res = await api.post("/ws/ticket");
  const sep = path.includes("?") ? "&" : "?";
  return new WebSocket(`${WS_URL}${path}${sep}ticket=${encodeURIComponent(res.data.ticket)}`);
}

export function errorMessage(err) {
  const detail = err.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "Please check your input.";
  return "Something went wrong. Is the server running?";
}

export default api;
