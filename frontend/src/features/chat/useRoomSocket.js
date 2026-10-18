import { useCallback, useEffect, useRef, useState } from "react";
import api, { WS_URL } from "../../api/client";

const PAGE = 30;

function merge(current, incoming) {
  const byId = new Map(current.map((m) => [m.id, m]));
  incoming.forEach((m) => byId.set(m.id, m));
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

export default function useRoomSocket(roomId, token) {
  const [messages, setMessages] = useState([]);
  const [online, setOnline] = useState([]);
  const [typing, setTyping] = useState({});
  const [status, setStatus] = useState("connecting");
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const wsRef = useRef(null);
  const lastTypingSent = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let retries = 0;
    let reconnectTimer;
    const typingTimers = {};

    api.get(`/rooms/${roomId}/messages`, { params: { limit: PAGE } }).then((res) => {
      if (cancelled) return;
      setMessages((prev) => merge(res.data, prev));
      setHasMore(res.data.length === PAGE);
    });

    function clearTyping(userId) {
      clearTimeout(typingTimers[userId]);
      setTyping((prev) => {
        const next = { ...prev };
        delete next[userId];
        return next;
      });
    }

    function connect() {
      const ws = new WebSocket(`${WS_URL}/ws/rooms/${roomId}?token=${token}`);
      wsRef.current = ws;

      ws.onopen = () => {
        retries = 0;
        setStatus("online");
        setError("");
      };

      ws.onmessage = (e) => {
        const event = JSON.parse(e.data);
        if (event.type === "message") {
          setMessages((prev) => merge(prev, [event.message]));
          clearTyping(event.message.user_id);
        } else if (event.type === "presence") {
          setOnline(event.users);
        } else if (event.type === "typing") {
          setTyping((prev) => ({ ...prev, [event.user_id]: event.username }));
          clearTimeout(typingTimers[event.user_id]);
          typingTimers[event.user_id] = setTimeout(() => clearTyping(event.user_id), 3000);
        } else if (event.type === "error") {
          setError(event.detail);
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        // A refused handshake also lands here, so stop after a few tries
        if (retries >= 5) {
          setStatus("offline");
          return;
        }
        setStatus("reconnecting");
        reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** retries, 10000));
        retries += 1;
      };
    }

    connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      Object.values(typingTimers).forEach(clearTimeout);
      wsRef.current?.close();
    };
  }, [roomId, token]);

  const send = useCallback((content) => {
    const ws = wsRef.current;
    if (ws?.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: "message", content }));
    return true;
  }, []);

  const sendTyping = useCallback(() => {
    const ws = wsRef.current;
    const now = Date.now();
    if (ws?.readyState !== WebSocket.OPEN || now - lastTypingSent.current < 2000) return;
    lastTypingSent.current = now;
    ws.send(JSON.stringify({ type: "typing" }));
  }, []);

  const loadOlder = useCallback(async () => {
    if (messages.length === 0) return;
    const res = await api.get(`/rooms/${roomId}/messages`, {
      params: { before: messages[0].id, limit: PAGE },
    });
    setMessages((prev) => merge(prev, res.data));
    setHasMore(res.data.length === PAGE);
  }, [messages, roomId]);

  return { messages, online, typing, status, error, hasMore, send, sendTyping, loadOlder };
}
