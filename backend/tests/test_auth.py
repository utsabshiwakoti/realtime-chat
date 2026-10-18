def test_register_returns_user_without_password(client):
    res = client.post(
        "/auth/register",
        json={"username": "alice", "email": "a@example.com", "password": "password123"},
    )
    assert res.status_code == 201
    assert "hashed_password" not in res.json()


def test_duplicate_username_rejected(client):
    body = {"username": "alice", "email": "a@example.com", "password": "password123"}
    client.post("/auth/register", json=body)
    other = {**body, "email": "other@example.com"}
    assert client.post("/auth/register", json=other).status_code == 400


def test_invalid_username_rejected(client):
    res = client.post(
        "/auth/register",
        json={"username": "bad name!", "email": "a@example.com", "password": "password123"},
    )
    assert res.status_code == 422


def test_login_with_username_or_email(client):
    client.post(
        "/auth/register",
        json={"username": "alice", "email": "a@example.com", "password": "password123"},
    )
    for identifier in ("alice", "a@example.com"):
        res = client.post(
            "/auth/login", data={"username": identifier, "password": "password123"}
        )
        assert res.status_code == 200


def test_wrong_password(client):
    client.post(
        "/auth/register",
        json={"username": "alice", "email": "a@example.com", "password": "password123"},
    )
    res = client.post("/auth/login", data={"username": "alice", "password": "nope-nope"})
    assert res.status_code == 401


def test_rooms_require_token(client):
    assert client.get("/rooms").status_code == 401
