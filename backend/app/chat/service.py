from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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


def member_ids(db: Session, room_id: int) -> list[int]:
    return list(db.scalars(select(Membership.user_id).where(Membership.room_id == room_id)))


def latest_message_id(db: Session, room_id: int) -> int | None:
    return db.scalar(select(func.max(Message.id)).where(Message.room_id == room_id))


def unread_counts(db: Session, user_id: int) -> dict[int, int]:
    """Messages from other people newer than what the user last read, per room they're in."""
    rows = db.execute(
        select(Message.room_id, func.count(Message.id))
        .join(
            Membership,
            (Membership.room_id == Message.room_id) & (Membership.user_id == user_id),
        )
        .where(
            Message.id > func.coalesce(Membership.last_read_message_id, 0),
            Message.user_id != user_id,
        )
        .group_by(Message.room_id)
    ).all()
    return dict(rows)


def list_rooms(db: Session, user_id: int) -> list[dict]:
    counts = dict(
        db.execute(
            select(Membership.room_id, func.count(Membership.id)).group_by(
                Membership.room_id
            )
        ).all()
    )
    mine = set(db.scalars(select(Membership.room_id).where(Membership.user_id == user_id)))
    unread = unread_counts(db, user_id)
    rooms = db.scalars(select(Room).where(Room.is_direct.is_(False)).order_by(Room.name)).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "member_count": counts.get(r.id, 0),
            "is_member": r.id in mine,
            "unread_count": unread.get(r.id, 0),
        }
        for r in rooms
    ]


def join(db: Session, room_id: int, user_id: int) -> None:
    if is_member(db, room_id, user_id):
        return
    # Start "read" at the newest message, so joining a busy room doesn't show 500 unread.
    db.add(
        Membership(
            room_id=room_id,
            user_id=user_id,
            last_read_message_id=latest_message_id(db, room_id),
        )
    )
    db.commit()


def mark_read(db: Session, room_id: int, user_id: int, message_id: int | None) -> int | None:
    """Move the user's read marker forward (never back). Defaults to the newest message."""
    membership = db.scalar(
        select(Membership).where(Membership.room_id == room_id, Membership.user_id == user_id)
    )
    if membership is None:
        return None
    newest = latest_message_id(db, room_id) or 0
    target = newest if message_id is None else min(message_id, newest)
    if target > (membership.last_read_message_id or 0):
        membership.last_read_message_id = target
        db.commit()
    return membership.last_read_message_id


# ---------- direct messages ----------


def dm_name(a: int, b: int) -> str:
    low, high = sorted((a, b))
    return f"dm:{low}:{high}"


def get_or_create_dm(db: Session, me: User, other: User) -> Room:
    """One conversation per pair of users, however many times either side opens it."""
    name = dm_name(me.id, other.id)
    room = db.scalar(select(Room).where(Room.name == name))
    if room is not None:
        return room
    room = Room(name=name, is_direct=True, created_by=me.id)
    db.add(room)
    try:
        db.flush()
    except IntegrityError:
        # The other person opened the same DM at the same moment; use theirs.
        db.rollback()
        return db.scalar(select(Room).where(Room.name == name))
    db.add_all([Membership(room_id=room.id, user_id=uid) for uid in {me.id, other.id}])
    db.commit()
    return room


def list_dms(db: Session, user_id: int) -> list[dict]:
    my_dms = (
        select(Room.id)
        .join(Membership, Membership.room_id == Room.id)
        .where(Room.is_direct.is_(True), Membership.user_id == user_id)
    )
    # The other participant of each DM (a DM with yourself has no other member).
    others = dict(
        db.execute(
            select(Membership.room_id, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.room_id.in_(my_dms), Membership.user_id != user_id)
        ).all()
    )
    last_at = dict(
        db.execute(
            select(Message.room_id, func.max(Message.created_at))
            .where(Message.room_id.in_(my_dms))
            .group_by(Message.room_id)
        ).all()
    )
    unread = unread_counts(db, user_id)
    rows = [
        {
            "id": room_id,
            "user": {"id": other.id, "username": other.username},
            "unread_count": unread.get(room_id, 0),
            "last_message_at": last_at.get(room_id),
        }
        for room_id, other in others.items()
    ]
    # Most recent conversation first; ones with no messages yet go last.
    rows.sort(key=lambda r: (r["last_message_at"] is not None, r["last_message_at"] or 0), reverse=True)
    return rows


def search_users(db: Session, query: str, exclude_id: int, limit: int = 10) -> list[User]:
    pattern = f"{query.strip()}%"
    return list(
        db.scalars(
            select(User)
            .where(User.username.ilike(pattern), User.id != exclude_id)
            .order_by(User.username)
            .limit(limit)
        )
    )


# ---------- messages ----------


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
