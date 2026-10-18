import { useCallback, useEffect, useState } from "react";
import api from "../../api/client";
import ChatWindow from "./ChatWindow";
import Sidebar from "./Sidebar";

export default function ChatPage() {
  const [rooms, setRooms] = useState([]);
  const [activeId, setActiveId] = useState(null);

  const loadRooms = useCallback(async () => {
    const res = await api.get("/rooms");
    setRooms(res.data);
  }, []);

  useEffect(() => {
    loadRooms();
  }, [loadRooms]);

  const active = rooms.find((r) => r.id === activeId && r.is_member);

  async function leave() {
    await api.post(`/rooms/${activeId}/leave`);
    setActiveId(null);
    loadRooms();
  }

  return (
    <div className="chat-layout">
      <Sidebar rooms={rooms} activeId={activeId} onSelect={setActiveId} onChanged={loadRooms} />
      {active ? (
        <ChatWindow key={active.id} room={active} onLeave={leave} />
      ) : (
        <div className="empty">Pick a room or create one to start chatting.</div>
      )}
    </div>
  );
}
