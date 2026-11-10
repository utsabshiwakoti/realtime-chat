import pytest
from starlette.websockets import WebSocketDisconnect

from app.chat.manager import ConnectionManager
from tests.conftest import make_room, recv, register, room_url, ticket


def test_bad_ticket_refused(client):
    alice, _ = register(client, "alice")
    room_id = make_room(client, alice)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/rooms/{room_id}?ticket=garbage"):
            pass


def test_jwt_in_url_is_no_longer_accepted(client):
    alice, alice_token = register(client, "alice")
    room_id = make_room(client, alice)
    for query in (f"token={alice_token}", f"ticket={alice_token}"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/rooms/{room_id}?{query}"):
                pass


def test_ticket_works_only_once(client):
    alice, _ = register(client, "alice")
    room_id = make_room(client, alice)
    t = ticket(client, alice)
    with client.websocket_connect(f"/ws/rooms/{room_id}?ticket={t}") as ws:
        recv(ws, "presence")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/rooms/{room_id}?ticket={t}"):
            pass


def test_ticket_requires_login(client):
    assert client.post("/ws/ticket").status_code == 401


def test_non_member_refused(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    room_id = make_room(client, alice)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(room_url(client, room_id, bob)):
            pass


def test_message_reaches_other_member_and_is_saved(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    room_id = make_room(client, alice)
    client.post(f"/rooms/{room_id}/join", headers=bob)

    with client.websocket_connect(room_url(client, room_id, alice)) as a_ws:
        recv(a_ws, "presence")
        with client.websocket_connect(room_url(client, room_id, bob)) as b_ws:
            recv(b_ws, "presence", lambda e: len(e["users"]) == 2)

            a_ws.send_json({"type": "message", "content": "hi bob"})
            got = recv(b_ws, "message")["message"]
            assert got["content"] == "hi bob"
            assert got["username"] == "alice"

    saved = client.get(f"/rooms/{room_id}/messages", headers=bob).json()
    assert [m["content"] for m in saved] == ["hi bob"]


def test_typing_goes_to_others_only(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    room_id = make_room(client, alice)
    client.post(f"/rooms/{room_id}/join", headers=bob)

    with client.websocket_connect(room_url(client, room_id, alice)) as a_ws:
        recv(a_ws, "presence")
        with client.websocket_connect(room_url(client, room_id, bob)) as b_ws:
            recv(b_ws, "presence", lambda e: len(e["users"]) == 2)
            a_ws.send_json({"type": "typing"})
            event = recv(b_ws, "typing")
            assert event["username"] == "alice"


def test_presence_updates_when_user_leaves(client):
    alice, _ = register(client, "alice")
    bob, _ = register(client, "bob")
    room_id = make_room(client, alice)
    client.post(f"/rooms/{room_id}/join", headers=bob)

    with client.websocket_connect(room_url(client, room_id, alice)) as a_ws:
        recv(a_ws, "presence")
        with client.websocket_connect(room_url(client, room_id, bob)):
            recv(a_ws, "presence", lambda e: len(e["users"]) == 2)
        event = recv(a_ws, "presence", lambda e: len(e["users"]) == 1)
        assert event["users"][0]["username"] == "alice"


def test_invalid_message_gets_error_event(client):
    alice, _ = register(client, "alice")
    room_id = make_room(client, alice)
    with client.websocket_connect(room_url(client, room_id, alice)) as ws:
        recv(ws, "presence")
        ws.send_json({"type": "message", "content": "x" * 2001})
        assert "1-2000" in recv(ws, "error")["detail"]


def test_flooding_is_rate_limited(client):
    alice, _ = register(client, "alice")
    room_id = make_room(client, alice)
    with client.websocket_connect(room_url(client, room_id, alice)) as ws:
        recv(ws, "presence")
        for i in range(5):  # the burst allowance
            ws.send_json({"type": "message", "content": f"m{i}"})
            recv(ws, "message")
        ws.send_json({"type": "message", "content": "one too many"})
        assert "too fast" in recv(ws, "error")["detail"]
    saved = client.get(f"/rooms/{room_id}/messages", headers=alice).json()
    assert len(saved) == 5  # the rejected message was not stored


def test_leaving_room_blocks_further_messages(client):
    alice, _ = register(client, "alice")
    room_id = make_room(client, alice)
    with client.websocket_connect(room_url(client, room_id, alice)) as ws:
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
