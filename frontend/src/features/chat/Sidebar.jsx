import { useState } from "react";
import api, { errorMessage } from "../../api/client";
import { useAuth } from "../auth/AuthContext";

export default function Sidebar({ rooms, activeId, onSelect, onChanged }) {
  const { user, logout } = useAuth();
  const [name, setName] = useState("");
  const [error, setError] = useState("");

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
          className={`room ${r.id === activeId ? "active" : ""}`}
          onClick={() => r.is_member && onSelect(r.id)}
        >
          <span>#{r.name} <span className="muted">({r.member_count})</span></span>
          {!r.is_member && (
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
    </aside>
  );
}
