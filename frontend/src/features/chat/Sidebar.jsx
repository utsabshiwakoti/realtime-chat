import { useEffect, useState } from "react";
import api, { errorMessage } from "../../api/client";
import { useAuth } from "../auth/AuthContext";

function Badge({ count }) {
  if (!count) return null;
  return <span className="badge" aria-label={`${count} unread`}>{count > 99 ? "99+" : count}</span>;
}

export default function Sidebar({ rooms, dms, activeId, onSelect, onChanged, onStartDm }) {
  const { user, logout } = useAuth();
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [who, setWho] = useState("");
  const [matches, setMatches] = useState([]);
  const [dmError, setDmError] = useState("");

  // Suggest usernames as you type (debounced).
  useEffect(() => {
    const q = who.trim();
    if (!q) return undefined;
    const t = setTimeout(async () => {
      try {
        setMatches((await api.get("/users", { params: { q } })).data);
      } catch {
        setMatches([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [who]);

  async function createRoom(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setError("");
    try {
      const res = await api.post("/rooms", { name });
      setName("");
      await onChanged();
      onSelect(res.data.id);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function join(id) {
    await api.post(`/rooms/${id}/join`);
    await onChanged();
    onSelect(id);
  }

  async function startDm(e) {
    e.preventDefault();
    const username = who.trim();
    if (!username) return;
    setDmError("");
    try {
      await onStartDm(username);
      setWho("");
    } catch (err) {
      setDmError(errorMessage(err));
    }
  }

  return (
    <aside className="sidebar">
      <div className="me">
        <strong>{user?.username}</strong>
        <button className="ghost" onClick={logout}>Log out</button>
      </div>

      <h2>Rooms</h2>
      {rooms.length === 0 && <p className="muted">No rooms yet. Create one below.</p>}
      {rooms.map((r) => (
        <div
          key={r.id}
          className={`room ${r.id === activeId ? "active" : ""} ${r.unread_count ? "unread" : ""}`}
          onClick={() => r.is_member && onSelect(r.id)}
        >
          <span>#{r.name} <span className="muted">({r.member_count})</span></span>
          {r.is_member ? (
            <Badge count={r.unread_count} />
          ) : (
            <button className="ghost" onClick={() => join(r.id)}>Join</button>
          )}
        </div>
      ))}

      <form className="new-room" onSubmit={createRoom}>
        <input placeholder="New room name" value={name} maxLength={50}
          onChange={(e) => setName(e.target.value)} />
        <button>Add</button>
      </form>
      {error && <p className="error">{error}</p>}

      <h2>Direct messages</h2>
      {dms.length === 0 && <p className="muted">No conversations yet.</p>}
      {dms.map((d) => (
        <div
          key={d.id}
          className={`room ${d.id === activeId ? "active" : ""} ${d.unread_count ? "unread" : ""}`}
          onClick={() => onSelect(d.id)}
        >
          <span>@{d.user.username}</span>
          <Badge count={d.unread_count} />
        </div>
      ))}

      <form className="new-room" onSubmit={startDm}>
        <input
          placeholder="Message someone…"
          value={who}
          maxLength={30}
          list="user-matches"
          aria-label="Username to message"
          onChange={(e) => setWho(e.target.value)}
        />
        <datalist id="user-matches">
          {(who.trim() ? matches : []).map((u) => <option key={u.id} value={u.username} />)}
        </datalist>
        <button>Chat</button>
      </form>
      {dmError && <p className="error">{dmError}</p>}
    </aside>
  );
}
