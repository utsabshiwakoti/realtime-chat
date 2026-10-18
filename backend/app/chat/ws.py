import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.auth.models import User
from app.chat import service
from app.chat.manager import manager
from app.chat.schemas import MessageOut
from app.core.database import SessionLocal
from app.core.security import decode_token

router = APIRouter()


def _authenticate(token: str, room_id: int) -> tuple[int, str] | None:
    """Return (user_id, username) if the token is valid and the user is in the room."""
    user_id = decode_token(token)
    if user_id is None:
        return None
    with SessionLocal() as db:
        user = db.get(User, int(user_id))
        if user is None or not service.is_member(db, room_id, user.id):
            return None
        return user.id, user.username


def _save_message(room_id: int, user_id: int, content: str) -> dict | None:
    with SessionLocal() as db:
        # Re-check on every message, in case the user left the room via REST
        if not service.is_member(db, room_id, user_id):
            return None
        user = db.get(User, user_id)
        message = service.create_message(db, room_id, user, content)
        return MessageOut(**service.to_message_out(message)).model_dump(mode="json")


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: int, token: str = Query("")):
    identity = await run_in_threadpool(_authenticate, token, room_id)
    if identity is None:
        await websocket.close(code=1008)  # policy violation
        return
    user_id, username = identity

    await websocket.accept()
    manager.connect(room_id, user_id, username, websocket)
    await manager.broadcast(
        room_id, {"type": "presence", "users": manager.online(room_id)}
    )

    try:
        while True:
            try:
                event = json.loads(await websocket.receive_text())
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                continue

            kind = event.get("type")
            if kind == "message":
                content = str(event.get("content", "")).strip()
                if not content or len(content) > 2000:
                    await websocket.send_json(
                        {"type": "error", "detail": "Message must be 1-2000 characters"}
                    )
                    continue
                saved = await run_in_threadpool(_save_message, room_id, user_id, content)
                if saved is None:
                    await websocket.send_json(
                        {"type": "error", "detail": "You are not a member of this room"}
                    )
                    continue
                await manager.broadcast(room_id, {"type": "message", "message": saved})
            elif kind == "typing":
                await manager.broadcast(
                    room_id,
                    {"type": "typing", "user_id": user_id, "username": username},
                    exclude_user=user_id,
                )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(room_id, user_id, websocket)
        await manager.broadcast(
            room_id, {"type": "presence", "users": manager.online(room_id)}
        )
