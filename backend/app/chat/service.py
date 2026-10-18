from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.chat.models import Membership, Message, Room


def is_member(db: Session, room_id: int, user_id: int) -> bool:
    return (
        db.scalar(
            select(Membership.id).where(
                Membership.room_id == room_id, Membership.user_id == user_id
            )
        )
        is not None
    )


def list_rooms(db: Session, user_id: int) -> list[dict]:
    counts = dict(
        db.execute(
            select(Membership.room_id, func.count(Membership.id)).group_by(
                Membership.room_id
            )
        ).all()
    )
    mine = set(db.scalars(select(Membership.room_id).where(Membership.user_id == user_id)))
    rooms = db.scalars(select(Room).order_by(Room.name)).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "member_count": counts.get(r.id, 0),
            "is_member": r.id in mine,
        }
        for r in rooms
    ]


def to_message_out(message: Message) -> dict:
    return {
        "id": message.id,
        "room_id": message.room_id,
        "user_id": message.user_id,
        "username": message.author.username,
        "content": message.content,
        "created_at": message.created_at,
    }


def create_message(db: Session, room_id: int, user: User, content: str) -> Message:
    message = Message(room_id=room_id, user_id=user.id, content=content.strip())
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_history(db: Session, room_id: int, before: int | None, limit: int) -> list[Message]:
    query = select(Message).where(Message.room_id == room_id)
    if before is not None:
        query = query.where(Message.id < before)
    rows = db.scalars(query.order_by(Message.id.desc()).limit(limit)).all()
    return list(reversed(rows))  # oldest first, ready to display
