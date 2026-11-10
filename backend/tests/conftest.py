import os
import tempfile

# Must be set before the app is imported
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SECRET_KEY"] = "test-secret"

import pytest
from fastapi.testclient import TestClient

from app.chat.manager import channels, manager
from app.core.database import Base, engine
from app.core.ratelimit import message_limiter
from app.core.tickets import tickets
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    # In-memory state survives between tests otherwise (user ids repeat after the DB reset)
    manager.rooms.clear()
    channels.users.clear()
    tickets._tickets.clear()
    message_limiter._buckets.clear()
    with TestClient(app) as c:
        yield c


def register(client, username):
    """Create a user and return (auth headers, raw token)."""
    client.post(
        "/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "password123",
        },
    )
    res = client.post(
        "/auth/login", data={"username": username, "password": "password123"}
    )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, token


def make_room(client, headers, name="general") -> int:
    return client.post("/rooms", headers=headers, json={"name": name}).json()["id"]


def ticket(client, headers) -> str:
    return client.post("/ws/ticket", headers=headers).json()["ticket"]


def room_url(client, room_id, headers) -> str:
    return f"/ws/rooms/{room_id}?ticket={ticket(client, headers)}"


def notify_url(client, headers) -> str:
    return f"/ws/notifications?ticket={ticket(client, headers)}"


def recv(ws, kind, check=lambda e: True):
    """Read events until one of the given type (and condition) arrives."""
    for _ in range(15):
        event = ws.receive_json()
        if event["type"] == kind and check(event):
            return event
    raise AssertionError(f"never received a {kind} event")
