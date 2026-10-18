import pytest
from starlette.websockets import WebSocketDisconnect

from app.chat.manager import ConnectionManager
from tests.conftest import make_room, register


def recv(ws, kind, check=lambda e: True):
    """Read events until one of the given type (and condition) arrives."""
    for _ in range(15):
        event = ws.receive_json()
        if event["type"] == kind and check(event):
            return event
    raise AssertionError(f"never received a {kind} event")


def url(room_id, token):
    return f"/ws/rooms/{room_id}?token={token}"


def test_bad_token_refused(client):
    alice, _ = register(client, "alice")
    room_id = make_room(client, alice)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url(room_id, "garbage")):
            pass


def test_non_member_refused(client):
    alice, _ = register(client, "alice")
    _, bob_token = register(client, "bob")
    room_id = make_room(client, alice)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url(room_id, bob_token)):
            pass


def test_message_reaches_other_member_and_is_saved(client):
    alice, alice_token = register(client, "alice")
    bob, bob_token = register(client, "bob")
    room_id = make_room(client, alice)
    client.post(f"/rooms/{room_id}/join", headers=bob)

    with client.websocket_connect(url(room_id, alice_token)) as a_ws:
        recv(a_ws, "presence")
        with client.websocket_connect(url(room_id, bob_token)) as b_ws:
            recv(b_ws, "presence", lambda e: len(e["users"]) == 2)

            a_ws.send_json({"type": "message", "content": "hi bob"})
            got = recv(b_ws, "message")["message"]
            assert got["content"] == "hi bob"
            assert got["username"] == "alice"

    saved = client.get(f"/rooms/{room_id}/messages", headers=bob).json()
    assert [m["content"] for m in saved] == ["hi bob"]


def test_typing_goes_to_others_only(client):
    alice, alice_token = register(client, "alice")
    bob, bob_token = register(client, "bob")
    room_id = make_room(client, alice)
    client.post(f"/rooms/{room_id}/join", headers=bob)

    with client.websocket_connect(url(room_id, alice_token)) as a_ws:
        recv(a_ws, "presence")
        with client.websocket_connect(url(room_id, bob_token)) as b_ws:
            recv(b_ws, "presence", lambda e: len(e["users"]) == 2)
            a_ws.send_json({"type": "typing"})
            event = recv(b_ws, "typing")
            assert event["username"] == "alice"


def test_presence_updates_when_user_leaves(client):
    alice, alice_token = register(client, "alice")
    bob, bob_token = register(client, "bob")
    room_id = make_room(client, alice)
    client.post(f"/rooms/{room_id}/join", headers=bob)

    with client.websocket_connect(url(room_id, alice_token)) as a_ws:
        recv(a_ws, "presence")
        with client.websocket_connect(url(room_id, bob_token)):
            recv(a_ws, "presence", lambda e: len(e["users"]) == 2)
        event = recv(a_ws, "presence", lambda e: len(e["users"]) == 1)
        assert event["users"][0]["username"] == "alice"


def test_invalid_message_gets_error_event(client):
    alice, alice_token = register(client, "alice")
    room_id = make_room(client, alice)
    with client.websocket_connect(url(room_id, alice_token)) as ws:
        recv(ws, "presence")
        ws.send_json({"type": "message", "content": "x" * 2001})
        assert "1-2000" in recv(ws, "error")["detail"]


def test_leaving_room_blocks_further_messages(client):
    alice, alice_token = register(client, "alice")
    room_id = make_room(client, alice)
    with client.websocket_connect(url(room_id, alice_token)) as ws:
        recv(ws, "presence")
        client.post(f"/rooms/{room_id}/leave", headers=alice)
        ws.send_json({"type": "message", "content": "still here?"})
        assert "not a member" in recv(ws, "error")["detail"]


def test_multiple_tabs_count_as_one_user():
    m = ConnectionManager()
    tab1, tab2 = object(), object()
    m.connect(1, 10, "alice", tab1)
    m.connect(1, 10, "alice", tab2)
    assert m.online(1) == [{"id": 10, "username": "alice"}]
    m.disconnect(1, 10, tab1)
    assert len(m.online(1)) == 1  # one tab still open
    m.disconnect(1, 10, tab2)
    assert m.online(1) == []
    assert 1 not in m.rooms
