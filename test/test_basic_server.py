from datetime import datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

import basic_server
from model import LoginRequest, RegisterRequest


def unique_username(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def username():
    value = unique_username("BasicTest")
    basic_server.delete_user(value)
    yield value
    basic_server.delete_user(value)


@pytest.fixture
def client():
    with TestClient(basic_server.app) as test_client:
        yield test_client


def test_init_database_and_lifespan_create_table(client):
    basic_server.init_database()
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["database"]["table"] == "user_info"


def test_create_get_update_delete_user_helpers(username):
    created_user = basic_server.create_user(username, "Passw0rd!")

    assert created_user["username"] == username
    assert "password_hash" not in created_user

    public_user = basic_server.get_user_by_username(username)
    private_user = basic_server.get_user_by_username(username, include_password_hash=True)

    assert public_user["username"] == username
    assert "password_hash" not in public_user
    assert private_user["password_hash"].startswith("pbkdf2_sha256$")

    updated_user = basic_server.update_user_password(username, "Newpass1!")
    updated_private_user = basic_server.get_user_by_username(username, include_password_hash=True)

    assert updated_user["username"] == username
    assert basic_server.verify_password("Newpass1!", updated_private_user["password_hash"])
    assert basic_server.delete_user(username) is True
    assert basic_server.delete_user(username) is False
    assert basic_server.get_user_by_username(username) is None


def test_create_user_duplicate_raises_conflict(username):
    basic_server.create_user(username, "Passw0rd!")

    with pytest.raises(HTTPException) as exc_info:
        basic_server.create_user(username, "Passw0rd!")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Username already exists"


def test_register_login_read_root_routes(client, username):
    register_response = client.post(
        "/register",
        json={"username": username, "password": "Passw0rd!"},
    )
    duplicate_response = client.post(
        "/register",
        json={"username": username, "password": "Passw0rd!"},
    )
    bad_login_response = client.post(
        "/login",
        json={"username": username, "password": "wrongPass1!"},
    )
    login_response = client.post(
        "/login",
        json={"username": username, "password": "Passw0rd!"},
    )
    root_response = client.get("/")

    assert register_response.status_code == 201
    assert register_response.json()["username"] == username
    assert duplicate_response.status_code == 409
    assert bad_login_response.status_code == 401
    assert login_response.status_code == 200
    assert login_response.json()["token_type"] == "bearer"
    assert root_response.status_code == 200
    assert "register" in root_response.json()["endpoints"]


def test_login_function_returns_token_response(username):
    basic_server.register(RegisterRequest(username=username, password="Passw0rd!"))
    token_response = basic_server.login(LoginRequest(username=username, password="Passw0rd!"))

    assert token_response.token_type == "bearer"
    assert token_response.access_token


def test_login_function_rejects_invalid_credentials(username):
    with pytest.raises(HTTPException) as missing_user_exc:
        basic_server.login(LoginRequest(username=username, password="Passw0rd!"))

    basic_server.register(RegisterRequest(username=username, password="Passw0rd!"))

    with pytest.raises(HTTPException) as bad_password_exc:
        basic_server.login(LoginRequest(username=username, password="wrongPass1!"))

    assert missing_user_exc.value.status_code == 401
    assert bad_password_exc.value.status_code == 401


def test_protected_me_update_password_and_delete_routes(client, username):
    client.post("/register", json={"username": username, "password": "Passw0rd!"})
    login_response = client.post(
        "/login",
        json={"username": username, "password": "Passw0rd!"},
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_response = client.get("/me", headers=headers)
    protected_response = client.get("/protected", headers=headers)
    router_protected_response = client.get("/api/protected", headers=headers)
    update_response = client.put(
        "/me/password",
        headers=headers,
        json={"password": "Newpass1!"},
    )
    old_password_response = client.post(
        "/login",
        json={"username": username, "password": "Passw0rd!"},
    )
    new_password_response = client.post(
        "/login",
        json={"username": username, "password": "Newpass1!"},
    )
    delete_response = client.delete("/me", headers=headers)
    deleted_me_response = client.get("/me", headers=headers)

    assert me_response.status_code == 200
    assert me_response.json()["username"] == username
    assert protected_response.status_code == 200
    assert protected_response.json()["username"] == username
    assert router_protected_response.status_code == 200
    assert router_protected_response.json()["username"] == username
    assert update_response.status_code == 200
    assert old_password_response.status_code == 401
    assert new_password_response.status_code == 200
    assert delete_response.status_code == 204
    assert deleted_me_response.status_code == 404


def test_router_news_requires_token_and_returns_news(client, monkeypatch):
    rows = [
        {
            "id": 1,
            "title": "JWT Protected News",
            "url": "https://example.com/news/1",
            "image": "https://example.com/image.jpg",
            "summary": "A protected news summary",
            "date": datetime(2026, 7, 18).date(),
            "img": None,
        }
    ]
    cursor = FakeCursor(rows)

    def fake_connect(database_url, row_factory):
        assert database_url == basic_server.DATABASE_URL
        assert row_factory is dict_row
        return FakeConnection(cursor)

    monkeypatch.setattr(basic_server.psycopg, "connect", fake_connect)
    token = basic_server.auth.create_access_token(uid="NewsUser")

    missing_token_response = client.get("/api/news")
    response = client.get("/api/news?page=2&page_size=10", headers={"Authorization": f"Bearer {token}"})

    assert missing_token_response.status_code == 401
    assert response.status_code == 200
    assert response.json() == {
        "news": [
            {
                "id": 1,
                "title": "JWT Protected News",
                "url": "https://example.com/news/1",
                "image": "https://example.com/image.jpg",
                "summary": "A protected news summary",
                "date": "2026-07-18",
                "img": None,
            }
        ],
    }
    assert "LIMIT %s OFFSET %s" in cursor.query
    assert cursor.params == (10, 10)


def test_protected_routes_reject_missing_token(client):
    assert client.get("/me").status_code == 401
    assert client.put("/me/password", json={"password": "Newpass1!"}).status_code == 401
    assert client.delete("/me").status_code == 401
    assert client.get("/protected").status_code == 401
    assert client.get("/api/protected").status_code == 401
    assert client.get("/api/news").status_code == 401
