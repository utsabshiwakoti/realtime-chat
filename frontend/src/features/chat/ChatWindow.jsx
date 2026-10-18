import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import useRoomSocket from "./useRoomSocket";

export default function ChatWindow({ room, onLeave }) {
  const { user, token } = useAuth();
  const { messages, online, typing, status, error, hasMore, send, sendTyping, loadOlder } =
    useRoomSocket(room.id, token);
  const [text, setText] = useState("");
  const bottomRef = useRef(null);
  const lastId = messages[messages.length - 1]?.id;

  // Scroll down when a new message arrives (not when older ones load at the top)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lastId]);

  function handleSubmit(e) {
    e.preventDefault();
    const content = text.trim();
    if (!content) return;
    if (send(content)) setText("");
  }

  const typers = Object.values(typing);
  const typingText =
    typers.length === 0
      ? ""
      : typers.length === 1
      ? `${typers[0]} is typing...`
      : `${typers.join(", ")} are typing...`;

  return (
    <div className="window">
      <div className="window-head">
        <div>
          <h2>#{room.name}</h2>
          <span className="muted">{status === "online" ? "Connected" : status}</span>
        </div>
        <button className="ghost" onClick={onLeave}>Leave room</button>
      </div>

      <div className="body">
        <div className="messages">
          {hasMore && (
            <button className="ghost" onClick={loadOlder}>Load older messages</button>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`msg ${m.user_id === user.id ? "mine" : ""}`}>
              <div className="meta">
                {m.username} · {new Date(m.created_at).toLocaleTimeString()}
              </div>
              <div className="text">{m.content}</div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <div className="online">
          <h3>Online ({online.length})</h3>
          {online.map((u) => (
            <div key={u.id}><span className="dot" />{u.username}</div>
          ))}
        </div>
      </div>

      <div className="typing">{error ? <span className="error">{error}</span> : typingText}</div>

      <form className="composer" onSubmit={handleSubmit}>
        <input
          placeholder="Write a message..."
          value={text}
          maxLength={2000}
          onChange={(e) => { setText(e.target.value); sendTyping(); }}
        />
        <button disabled={status !== "online"}>Send</button>
      </form>
    </div>
  );
}
