import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.chat import service
from app.chat.manager import channels, manager
from app.chat.schemas import MessageOut, Ticket
from app.core.database import SessionLocal
from app.core.ratelimit import message_limiter
from app.core.tickets import tickets

router = APIRouter()


@router.post("/ws/ticket", response_model=Ticket, tags=["websocket"])
def issue_ticket(user: User = Depends(get_current_user)):
    """Trade the JWT (sent in a header) for a one-time ticket to put in the WebSocket URL."""
    return Ticket(ticket=tickets.issue(user.id), expires_in=int(tickets.ttl))


def _load_user(user_id: int, room_id: int | None = None) -> tuple[int, str] | None:
    """(user_id, username) if the user exists and, when a room is given, is a member."""
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            return None
        if room_id is not None and not service.is_member(db, room_id, user.id):
            return None
        return user.id, user.username


def _save_message(room_id: int, user_id: int, content: str) -> tuple[dict, list[int]] | None:
    """Store the message; return it plus the room's member ids, or None if no longer a member."""
    with SessionLocal() as db:
        # Re-check on every message, in case the user left the room via REST
        if not service.is_member(db, room_id, user_id):
            return None
        user = db.get(User, user_id)
        message = service.create_message(db, room_id, user, content)
        payload = MessageOut(**service.to_message_out(message)).model_dump(mode="json")
        return payload, service.member_ids(db, room_id)


async def _accept(websocket: WebSocket, ticket: str, room_id: int | None = None):
    """Validate the ticket *before* accepting, so unauthenticated clients never connect."""
    user_id = tickets.redeem(ticket)
    identity = None if user_id is None else await run_in_threadpool(_load_user, user_id, room_id)
    if identity is None:
        await websocket.close(code=1008)  # policy violation
        return None
    await websocket.accept()
    return identity


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: int, ticket: str = Query("")):
    identity = await _accept(websocket, ticket, room_id)
    if identity is None:
        return
    user_id, username = identity

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
                if not message_limiter.allow(user_id):
                    await websocket.send_json(
                        {"type": "error", "detail": "You're sending messages too fast. Slow down a little."}
                    )
                    continue
                result = await run_in_threadpool(_save_message, room_id, user_id, content)
                if result is None:
                    await websocket.send_json(
                        {"type": "error", "detail": "You are not a member of this room"}
                    )
                    continue
                saved, members = result
                await manager.broadcast(room_id, {"type": "message", "message": saved})
                # Tell members' other tabs/rooms, so sidebars can show an unread badge.
                await channels.send(
                    [m for m in members if m != user_id],
                    {"type": "activity", "room_id": room_id, "message": saved},
                )
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


@router.websocket("/ws/notifications")
async def notification_socket(websocket: WebSocket, ticket: str = Query("")):
    """Server-to-client only: new-message activity in any room or DM the user belongs to."""
    identity = await _accept(websocket, ticket)
    if identity is None:
        return
    user_id, _ = identity
    channels.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # ignore input; just wait for the client to leave
    except WebSocketDisconnect:
        pass
    finally:
        channels.disconnect(user_id, websocket)
