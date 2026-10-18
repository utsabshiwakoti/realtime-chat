import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { errorMessage } from "../../api/client";
import { useAuth } from "./AuthContext";

export default function AuthPage({ mode }) {
  const isRegister = mode === "register";
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (isRegister) await register(username, email, password);
      else await login(username, password);
      navigate("/");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-card">
      <h1>{isRegister ? "Create account" : "Sign in"}</h1>
      <form onSubmit={handleSubmit}>
        <label>
          {isRegister ? "Username" : "Username or email"}
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            minLength={isRegister ? 3 : undefined}
            maxLength={isRegister ? 30 : undefined}
            pattern={isRegister ? "[A-Za-z0-9_]+" : undefined}
            title={isRegister ? "Letters, numbers, and underscores only" : undefined}
            required
          />
        </label>
        {isRegister && (
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
        )}
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            maxLength={72}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button disabled={busy}>
          {busy ? "Please wait..." : isRegister ? "Register" : "Sign in"}
        </button>
      </form>
      <p>
        {isRegister ? (
          <>Already have an account? <Link to="/login">Sign in</Link></>
        ) : (
          <>No account? <Link to="/register">Register</Link></>
        )}
      </p>
    </div>
  );
}
