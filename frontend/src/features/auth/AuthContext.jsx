import { createContext, useContext, useEffect, useState } from "react";
import api from "../../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!localStorage.getItem("token"));

  useEffect(() => {
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .get("/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => {
        localStorage.removeItem("token");
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, [token]);

  async function login(identifier, password) {
    const form = new URLSearchParams({ username: identifier, password });
    const res = await api.post("/auth/login", form);
    localStorage.setItem("token", res.data.access_token);
    setToken(res.data.access_token);
  }

  async function register(username, email, password) {
    await api.post("/auth/register", { username, email, password });
    await login(username, password);
  }

  function logout() {
    localStorage.removeItem("token");
    setToken(null);
  }

  return (
    <AuthContext.Provider value={{ token, user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
