from app.auth.models import User
from app.chat import service
from app.core.database import SessionLocal
from tests.conftest import make_room, register


def test_create_room_auto_joins_creator(client):
    alice, _ = register(client, "alice")
    make_room(client, alice)
    rooms = client.get("/rooms", headers=alice).json()
    assert rooms[0]["is_member"] is True
    assert rooms[0]["member_count"] == 1


def test_duplicate_room_name_rejected(client):
    alice, _ = register(client, "alice")
    make_room(client, alice)
    res = client.post("/rooms", headers=alice, json={"name": "general"})
    assert res.status_code == 400


def test_non_member_cannot_read_history(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    room_id = make_room(client, alice)
    assert client.get(f"/rooms/{room_id}/messages", headers=bob).status_code == 403
    client.post(f"/rooms/{room_id}/join", headers=bob)
    assert client.get(f"/rooms/{room_id}/messages", headers=bob).json() == []


def test_join_missing_room_is_404(client):
    alice, _ = register(client, "alice")
    assert client.post("/rooms/999/join", headers=alice).status_code == 404


def test_leaving_removes_access(client):
    alice, _ = register(client, "alice")
    room_id = make_room(client, alice)
    client.post(f"/rooms/{room_id}/leave", headers=alice)
    assert client.get(f"/rooms/{room_id}/messages", headers=alice).status_code == 403


def test_history_cursor_pagination(client):
    alice, _ = register(client, "alice")
    room_id = make_room(client, alice)
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="alice").one()
        for i in range(5):
            service.create_message(db, room_id, user, f"m{i}")

    latest = client.get(f"/rooms/{room_id}/messages", headers=alice, params={"limit": 2}).json()
    assert [m["content"] for m in latest] == ["m3", "m4"]  # oldest first

    older = client.get(
        f"/rooms/{room_id}/messages",
        headers=alice,
        params={"limit": 2, "before": latest[0]["id"]},
    ).json()
    assert [m["content"] for m in older] == ["m1", "m2"]
