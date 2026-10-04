from datetime import datetime, timedelta, timezone

import jwt

from tests.conftest import auth_headers, register


def test_register_returns_token_and_hashes_password(client, db):
    data = register(client, email="Carol@Example.com")
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "carol@example.com"
    from app.models import User

    user = db.query(User).one()
    assert user.password_hash != "Passw0rd!"
    assert user.password_hash.startswith("$2b$")


def test_register_duplicate_email_case_insensitive(client):
    register(client, email="dup@example.com")
    resp = client.post("/auth/register", json={"email": "DUP@example.com", "password": "Passw0rd!"})
    assert resp.status_code == 409


def test_register_validation(client):
    assert client.post("/auth/register", json={"email": "not-an-email", "password": "Passw0rd!"}).status_code == 422
    resp = client.post("/auth/register", json={"email": "x@example.com", "password": "short1"})
    assert resp.status_code == 422
    resp = client.post("/auth/register", json={"email": "x@example.com", "password": "onlyletters"})
    assert resp.status_code == 422
    assert "letter and one number" in resp.json()["detail"]


def test_login_success_and_failure(client):
    register(client, email="dave@example.com")
    ok = client.post("/auth/login", json={"email": "dave@example.com", "password": "Passw0rd!"})
    assert ok.status_code == 200
    token = ok.json()["access_token"]
    assert client.get("/auth/me", headers=auth_headers(token)).json()["email"] == "dave@example.com"

    bad = client.post("/auth/login", json={"email": "dave@example.com", "password": "wrong-pass1"})
    assert bad.status_code == 401
    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": "Passw0rd!"})
    assert unknown.status_code == 401
    assert bad.json()["detail"] == unknown.json()["detail"]  # no account enumeration


def test_protected_routes_require_valid_token(client):
    assert client.get("/companies").status_code == 401
    assert client.get("/companies", headers=auth_headers("garbage")).status_code == 401

    data = register(client)
    expired = jwt.encode(
        {"sub": str(data["user"]["id"]), "type": "access", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        "test-secret-key-that-is-long-enough-for-hs256",
        algorithm="HS256",
    )
    assert client.get("/companies", headers=auth_headers(expired)).status_code == 401

    forged = jwt.encode(
        {"sub": str(data["user"]["id"]), "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "some-other-secret-key-of-sufficient-length",
        algorithm="HS256",
    )
    assert client.get("/companies", headers=auth_headers(forged)).status_code == 401


def test_login_rate_limited(client):
    register(client, email="eve@example.com")
    codes = [client.post("/auth/login", json={"email": "eve@example.com", "password": "wrong-pass1"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10
    assert codes[-1] == 429
