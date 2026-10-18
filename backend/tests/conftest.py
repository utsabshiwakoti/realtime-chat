import os
import tempfile

# Must be set before the app is imported
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SECRET_KEY"] = "test-secret"

import pytest
from fastapi.testclient import TestClient

from app.chat.manager import manager
from app.core.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    manager.rooms.clear()
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
