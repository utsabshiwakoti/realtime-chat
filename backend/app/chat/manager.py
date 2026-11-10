from fastapi import WebSocket


class ConnectionManager:
    """Tracks open sockets per room. A user can have several (multiple tabs)."""

    def __init__(self):
        # room_id -> user_id -> {"username": str, "sockets": set[WebSocket]}
        self.rooms: dict[int, dict[int, dict]] = {}

    def connect(self, room_id: int, user_id: int, username: str, ws: WebSocket) -> None:
        users = self.rooms.setdefault(room_id, {})
        entry = users.setdefault(user_id, {"username": username, "sockets": set()})
        entry["sockets"].add(ws)

    def disconnect(self, room_id: int, user_id: int, ws: WebSocket) -> None:
        users = self.rooms.get(room_id, {})
        entry = users.get(user_id)
        if not entry:
            return
        entry["sockets"].discard(ws)
        if not entry["sockets"]:
            del users[user_id]  # last tab closed: user is offline
        if not users:
            self.rooms.pop(room_id, None)

    def online(self, room_id: int) -> list[dict]:
        users = self.rooms.get(room_id, {})
        return sorted(
            ({"id": uid, "username": e["username"]} for uid, e in users.items()),
            key=lambda u: u["username"],
        )

    async def broadcast(self, room_id: int, payload: dict, exclude_user: int | None = None):
        dead = []
        for uid, entry in list(self.rooms.get(room_id, {}).items()):
            if uid == exclude_user:
                continue
            for ws in list(entry["sockets"]):
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append((uid, ws))
        for uid, ws in dead:
            self.disconnect(room_id, uid, ws)


class UserChannels:
    """One socket per open tab, per user, for events outside the room you're viewing.

    Room sockets only exist for the room on screen, so this is how the sidebar learns that
    another room (or a brand-new DM) has a new message and should show an unread badge.
    """

    def __init__(self):
        self.users: dict[int, set[WebSocket]] = {}

    def connect(self, user_id: int, ws: WebSocket) -> None:
        self.users.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        sockets = self.users.get(user_id)
        if sockets is None:
            return
        sockets.discard(ws)
        if not sockets:
            del self.users[user_id]

    async def send(self, user_ids, payload: dict) -> None:
        for uid in user_ids:
            for ws in list(self.users.get(uid, ())):
                try:
                    await ws.send_json(payload)
                except Exception:
                    self.disconnect(uid, ws)


manager = ConnectionManager()
channels = UserChannels()
