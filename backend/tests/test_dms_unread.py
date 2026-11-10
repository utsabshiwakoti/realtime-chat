import pytest
from sqlalchemy import create_engine, inspect, text

from app.auth.models import User
from app.chat import service
from app.core.database import SessionLocal, ensure_schema
from app.core.ratelimit import RateLimiter
from app.core.tickets import TicketStore
from tests.conftest import make_room, notify_url, recv, register, room_url


def post_messages(room_id, username, *contents):
    with SessionLocal() as db:
        user = db.query(User).filter_by(username=username).one()
        return [service.create_message(db, room_id, user, c).id for c in contents]


def open_dm(client, headers, username):
    return client.post("/dms", headers=headers, json={"username": username})


# ---------- direct messages ----------


def test_open_dm_is_idempotent_and_shared(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    first = open_dm(client, alice, "bob")
    assert first.status_code == 201
    assert first.json()["user"]["username"] == "bob"
    again = open_dm(client, alice, "bob")
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    # Bob sees the same conversation, labelled with Alice
    from_bob = open_dm(client, bob, "alice").json()
    assert from_bob["id"] == first.json()["id"]
    assert [d["user"]["username"] for d in client.get("/dms", headers=bob).json()] == ["alice"]


def test_dm_validation(client):
    alice, _ = register(client, "alice")
    assert open_dm(client, alice, "alice").status_code == 400
    assert open_dm(client, alice, "nobody").status_code == 404


def test_dms_are_private(client):
    alice, _ = register(client, "alice")
    register(client, "bob")
    eve, _ = register(client, "eve")
    dm_id = open_dm(client, alice, "bob").json()["id"]

    assert all(r["id"] != dm_id for r in client.get("/rooms", headers=eve).json())  # not listed
    assert client.post(f"/rooms/{dm_id}/join", headers=eve).status_code == 404  # can't join
    assert client.get(f"/rooms/{dm_id}/messages", headers=eve).status_code == 403
    assert client.get("/dms", headers=eve).json() == []
    assert client.post(f"/rooms/{dm_id}/leave", headers=alice).status_code == 404  # can't leave


def test_dm_messages_flow_over_websocket(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    dm_id = open_dm(client, alice, "bob").json()["id"]
    with client.websocket_connect(room_url(client, dm_id, alice)) as a_ws:
        recv(a_ws, "presence")
        with client.websocket_connect(room_url(client, dm_id, bob)) as b_ws:
            recv(b_ws, "presence", lambda e: len(e["users"]) == 2)
            a_ws.send_json({"type": "message", "content": "psst"})
            assert recv(b_ws, "message")["message"]["content"] == "psst"


def test_dms_sorted_by_latest_message(client):
    alice, _ = register(client, "alice")
    register(client, "bob")
    register(client, "carol")
    bob_dm = open_dm(client, alice, "bob").json()["id"]
    carol_dm = open_dm(client, alice, "carol").json()["id"]
    post_messages(bob_dm, "alice", "older")
    post_messages(carol_dm, "alice", "newer")
    assert [d["user"]["username"] for d in client.get("/dms", headers=alice).json()] == ["carol", "bob"]


def test_public_room_cannot_use_dm_prefix(client):
    alice, _ = register(client, "alice")
    assert client.post("/rooms", headers=alice, json={"name": "dm:1:2"}).status_code == 422


def test_user_search(client):
    alice, _ = register(client, "alice")
    register(client, "albert")
    register(client, "bob")
    names = [u["username"] for u in client.get("/users", headers=alice, params={"q": "al"}).json()]
    assert names == ["albert"]  # prefix match, never yourself


# ---------- unread counts ----------


def test_unread_counts_and_mark_read(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    room_id = make_room(client, alice)
    client.post(f"/rooms/{room_id}/join", headers=bob)
    ids = post_messages(room_id, "alice", "one", "two", "three")

    def bob_unread():
        return next(r for r in client.get("/rooms", headers=bob).json() if r["id"] == room_id)["unread_count"]

    assert bob_unread() == 3
    # Alice's own messages never count as unread for her
    assert client.get("/rooms", headers=alice).json()[0]["unread_count"] == 0

    client.post(f"/rooms/{room_id}/read", headers=bob, json={"message_id": ids[0]})
    assert bob_unread() == 2
    client.post(f"/rooms/{room_id}/read", headers=bob, json={"message_id": ids[0] - 1})
    assert bob_unread() == 2  # the marker never moves backwards
    client.post(f"/rooms/{room_id}/read", headers=bob)  # no body = read everything
    assert bob_unread() == 0


def test_joining_busy_room_starts_with_zero_unread(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    room_id = make_room(client, alice)
    post_messages(room_id, "alice", "a", "b", "c")
    client.post(f"/rooms/{room_id}/join", headers=bob)
    assert next(r for r in client.get("/rooms", headers=bob).json() if r["id"] == room_id)["unread_count"] == 0


def test_dm_unread_count(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    dm_id = open_dm(client, alice, "bob").json()["id"]
    post_messages(dm_id, "alice", "hey", "you there?")
    assert client.get("/dms", headers=bob).json()[0]["unread_count"] == 2


def test_mark_read_requires_membership(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    room_id = make_room(client, alice)
    assert client.post(f"/rooms/{room_id}/read", headers=bob).status_code == 403


def test_notification_socket_gets_activity_from_other_rooms(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    dm_id = open_dm(client, alice, "bob").json()["id"]
    with client.websocket_connect(notify_url(client, bob)) as bob_notes:
        with client.websocket_connect(room_url(client, dm_id, alice)) as a_ws:
            recv(a_ws, "presence")
            a_ws.send_json({"type": "message", "content": "ping"})
            recv(a_ws, "message")
            event = bob_notes.receive_json()
            assert event["type"] == "activity"
            assert event["room_id"] == dm_id
            assert event["message"]["content"] == "ping"


# ---------- building blocks ----------


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_ticket_store_expiry_and_single_use():
    clock = FakeClock()
    store = TicketStore(ttl_seconds=30, clock=clock)
    t = store.issue(7)
    assert store.redeem(t) == 7
    assert store.redeem(t) is None  # used up
    late = store.issue(7)
    clock.now = 31
    assert store.redeem(late) is None  # expired


def test_rate_limiter_refills_over_time():
    clock = FakeClock()
    limiter = RateLimiter(capacity=2, refill_per_second=1, clock=clock)
    assert limiter.allow("u") and limiter.allow("u")
    assert not limiter.allow("u")
    clock.now = 1.0
    assert limiter.allow("u")
    assert limiter.allow("someone-else")  # buckets are per user


def test_ensure_schema_upgrades_old_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:  # the tables as the first release created them
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(30), email VARCHAR, hashed_password VARCHAR, created_at DATETIME)"))
        conn.execute(text("CREATE TABLE rooms (id INTEGER PRIMARY KEY, name VARCHAR(50), created_by INTEGER, created_at DATETIME)"))
        conn.execute(text("CREATE TABLE memberships (id INTEGER PRIMARY KEY, room_id INTEGER, user_id INTEGER, joined_at DATETIME)"))
        conn.execute(text("INSERT INTO rooms (id, name, created_by) VALUES (1, 'general', 1)"))
    ensure_schema(engine)
    ensure_schema(engine)  # safe to run on every start
    insp = inspect(engine)
    assert "is_direct" in {c["name"] for c in insp.get_columns("rooms")}
    assert "last_read_message_id" in {c["name"] for c in insp.get_columns("memberships")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT is_direct FROM rooms")).scalar() in (0, False)
    engine.dispose()


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
        ("sqlite:///./chat.db", "sqlite:///./chat.db"),
    ],
)
def test_database_url_uses_psycopg3(given, expected):
    from app.core.database import _normalise_url

    assert _normalise_url(given) == expected
