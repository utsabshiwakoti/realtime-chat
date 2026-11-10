from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.chat import service
from app.chat.models import Membership, Room
from app.chat.schemas import (
    DMCreate,
    DMOut,
    MessageOut,
    ReadMarker,
    ReadState,
    RoomCreate,
    RoomOut,
    UserBrief,
)
from app.core.database import get_db

router = APIRouter(prefix="/rooms", tags=["rooms"])
dm_router = APIRouter(tags=["direct messages"])


def _get_room(db: Session, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


def _get_public_room(db: Session, room_id: int) -> Room:
    room = _get_room(db, room_id)
    if room.is_direct:
        # Same answer as a missing room, so DM ids can't be discovered by probing.
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.get("", response_model=list[RoomOut])
def list_rooms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.list_rooms(db, user.id)


@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
    data: RoomCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = Room(name=data.name.strip(), created_by=user.id)
    db.add(room)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Room name already taken")
    db.add(Membership(room_id=room.id, user_id=user.id))  # creator auto-joins
    db.commit()
    return {"id": room.id, "name": room.name, "member_count": 1, "is_member": True}


@router.post("/{room_id}/join", status_code=status.HTTP_204_NO_CONTENT)
def join_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_public_room(db, room_id)  # nobody can join someone else's DM by id
    service.join(db, room_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{room_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_public_room(db, room_id)
    membership = db.scalar(
        select(Membership).where(Membership.room_id == room_id, Membership.user_id == user.id)
    )
    if membership:
        db.delete(membership)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{room_id}/messages", response_model=list[MessageOut])
def history(
    room_id: int,
    before: int | None = None,
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_room(db, room_id)
    if not service.is_member(db, room_id, user.id):
        raise HTTPException(status_code=403, detail="Join the room to read messages")
    return [service.to_message_out(m) for m in service.get_history(db, room_id, before, limit)]


@router.post("/{room_id}/read", response_model=ReadState)
def mark_read(
    room_id: int,
    data: ReadMarker | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark messages up to `message_id` (default: all) as read. Works for rooms and DMs."""
    _get_room(db, room_id)
    if not service.is_member(db, room_id, user.id):
        raise HTTPException(status_code=403, detail="Not a member of this room")
    marker = service.mark_read(db, room_id, user.id, data.message_id if data else None)
    return ReadState(last_read_message_id=marker)


# ---------- direct messages ----------


@dm_router.get("/dms", response_model=list[DMOut])
def list_dms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return service.list_dms(db, user.id)


@dm_router.post("/dms", response_model=DMOut)
def open_dm(
    data: DMCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start (or reopen) a private conversation with another user."""
    other = db.scalar(select(User).where(User.username == data.username))
    if other is None:
        raise HTTPException(status_code=404, detail="No user with that username")
    if other.id == user.id:
        raise HTTPException(status_code=400, detail="You can't message yourself")
    existed = db.scalar(select(Room.id).where(Room.name == service.dm_name(user.id, other.id)))
    room = service.get_or_create_dm(db, user, other)
    if existed is None:
        response.status_code = status.HTTP_201_CREATED
    unread = service.unread_counts(db, user.id).get(room.id, 0)
    return {"id": room.id, "user": other, "unread_count": unread}


@dm_router.get("/users", response_model=list[UserBrief])
def search_users(
    q: str = Query(min_length=1, max_length=30),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Username prefix search, for picking who to message."""
    return service.search_users(db, q, exclude_id=user.id)
