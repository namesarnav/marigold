"""Integration tests for /api/auth/* endpoints."""


def test_register_success(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": "password123", "name": "New User"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "pass", "name": "Dup"}
    client.post("/api/auth/register", json=payload)
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 409


def test_register_invalid_email(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "pass", "name": "Bad"},
    )
    assert resp.status_code == 422


def test_login_success(client):
    client.post(
        "/api/auth/register",
        json={"email": "login@example.com", "password": "secret", "name": "Login"},
    )
    resp = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "secret"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client):
    client.post(
        "/api/auth/register",
        json={"email": "wp@example.com", "password": "correct", "name": "WP"},
    )
    resp = client.post(
        "/api/auth/login",
        json={"email": "wp@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "anything"},
    )
    assert resp.status_code == 401


def test_refresh_after_login(client):
    client.post(
        "/api/auth/register",
        json={"email": "rf@example.com", "password": "pass", "name": "RF"},
    )
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_without_cookie(client):
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401


def test_logout_success(client):
    client.post(
        "/api/auth/register",
        json={"email": "lo@example.com", "password": "pass", "name": "LO"},
    )
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out"


def test_me_authenticated(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "tester@example.com"
    assert data["name"] == "Tester"
    assert "id" in data


def test_me_unauthenticated(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_invalid_token(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer bad.token.here"})
    assert resp.status_code == 401
