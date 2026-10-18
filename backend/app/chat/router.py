from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.chat import service
from app.chat.models import Membership, Room
from app.chat.schemas import MessageOut, RoomCreate, RoomOut
from app.core.database import get_db

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _get_room(db: Session, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None:
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
    _get_room(db, room_id)
    if not service.is_member(db, room_id, user.id):
        db.add(Membership(room_id=room_id, user_id=user.id))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{room_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_room(db, room_id)
    membership = (
        db.query(Membership)
        .filter(Membership.room_id == room_id, Membership.user_id == user.id)
        .first()
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
