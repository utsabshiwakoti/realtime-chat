import { useCallback, useEffect, useState } from "react";
import api from "../../api/client";
import { useAuth } from "../auth/AuthContext";
import ChatWindow from "./ChatWindow";
import Sidebar from "./Sidebar";
import useNotifications from "./useNotifications";

const clearUnread = (id) => (list) =>
  list.map((item) => (item.id === id ? { ...item, unread_count: 0 } : item));

export default function ChatPage() {
  const { token } = useAuth();
  const [rooms, setRooms] = useState([]);
  const [dms, setDms] = useState([]);
  const [activeId, setActiveId] = useState(null);

  const loadRooms = useCallback(async () => setRooms((await api.get("/rooms")).data), []);
  const loadDms = useCallback(async () => setDms((await api.get("/dms")).data), []);

  useEffect(() => {
    loadRooms();
    loadDms();
  }, [loadRooms, loadDms]);

  // A message arrived somewhere. The open chat handles its own messages; anything else
  // gets an unread badge. An unknown room id means someone just started a DM with us.
  const onActivity = useCallback(
    ({ room_id, message }) => {
      if (room_id === activeId) return;
      if (!rooms.some((r) => r.id === room_id) && !dms.some((d) => d.id === room_id)) {
        loadDms(); // new conversation: fetch it, unread count included
        return;
      }
      const bump = (item) =>
        item.id === room_id
          ? { ...item, unread_count: item.unread_count + 1, last_message_at: message.created_at }
          : item;
      setRooms((list) => list.map(bump));
      setDms((list) => list.map(bump));
    },
    [activeId, rooms, dms, loadDms],
  );
  useNotifications(token, onActivity);

  const room = rooms.find((r) => r.id === activeId && r.is_member);
  const dm = dms.find((d) => d.id === activeId);
  const active = room
    ? { id: room.id, title: `#${room.name}`, isDirect: false }
    : dm
    ? { id: dm.id, title: `@${dm.user.username}`, isDirect: true }
    : null;

  // Show the total in the tab title, e.g. "(3) Realtime Chat"
  const totalUnread = [...rooms, ...dms].reduce((sum, r) => sum + (r.unread_count || 0), 0);
  useEffect(() => {
    document.title = totalUnread ? `(${totalUnread}) Realtime Chat` : "Realtime Chat";
  }, [totalUnread]);

  const markedRead = useCallback((id) => {
    setRooms(clearUnread(id));
    setDms(clearUnread(id));
  }, []);

  async function leave() {
    await api.post(`/rooms/${activeId}/leave`);
    setActiveId(null);
    loadRooms();
  }

  async function startDm(username) {
    const res = await api.post("/dms", { username });
    await loadDms();
    setActiveId(res.data.id);
  }

  return (
    <div className="chat-layout">
      <Sidebar
        rooms={rooms}
        dms={dms}
        activeId={activeId}
        onSelect={setActiveId}
        onChanged={loadRooms}
        onStartDm={startDm}
      />
      {active ? (
        <ChatWindow
          key={active.id}
          room={active}
          onLeave={active.isDirect ? null : leave}
          onRead={markedRead}
        />
      ) : (
        <div className="empty">Pick a room or a person to start chatting.</div>
      )}
    </div>
  );
}
