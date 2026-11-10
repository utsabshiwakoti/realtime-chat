from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def not_reserved(cls, v: str) -> str:
        # "dm:" names belong to direct-message rooms; don't let a public room squat on one.
        if v.strip().lower().startswith("dm:"):
            raise ValueError('Room names can\'t start with "dm:"')
        return v


class RoomOut(BaseModel):
    id: int
    name: str
    member_count: int
    is_member: bool
    unread_count: int = 0


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class DMCreate(BaseModel):
    username: str = Field(min_length=1, max_length=30)


class DMOut(BaseModel):
    id: int
    user: UserBrief
    unread_count: int = 0
    last_message_at: datetime | None = None


class ReadMarker(BaseModel):
    message_id: int | None = None  # omit to mark everything as read


class ReadState(BaseModel):
    last_read_message_id: int | None


class Ticket(BaseModel):
    ticket: str
    expires_in: int


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    user_id: int
    username: str
    content: str
    created_at: datetime
