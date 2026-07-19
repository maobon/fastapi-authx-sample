from datetime import datetime

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient

import advanced_server
from model import LoginRequest, RefreshRequest, RegisterRequest


def unique_username(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


@pytest.fixture
def username():
    value = unique_username("AdvanceTest")
    advanced_server.delete_user(value)
    yield value
    advanced_server.delete_user(value)


@pytest.fixture
def client():
    with TestClient(advanced_server.app) as test_client:
        yield test_client


def register_user(username: str) -> dict:
    return advanced_server.create_user(username, "Passw0rd!")


def issue_tokens_for(username: str) -> tuple[str, str]:
    user = advanced_server.get_user_by_username(username, include_password_hash=True)
    token_pair = advanced_server.issue_token_pair(user)
    return token_pair.access_token, token_pair.refresh_token


def test_init_database_and_lifespan_create_tables(client):
    advanced_server.init_database()
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["database"]["tables"] == ["user_info", "user_sessions"]


def test_create_get_update_delete_user_helpers(username):
    created_user = advanced_server.create_user(username, "Passw0rd!")

    assert created_user["username"] == username
    assert "password_hash" not in created_user

    public_user = advanced_server.get_user_by_username(username)
    private_user = advanced_server.get_user_by_username(username, include_password_hash=True)

    assert public_user["username"] == username
    assert "password_hash" not in public_user
    assert private_user["password_hash"].startswith("pbkdf2_sha256$")

    updated_user = advanced_server.update_user_password(username, "Newpass1!")
    updated_private_user = advanced_server.get_user_by_username(username, include_password_hash=True)

    assert updated_user["username"] == username
    assert advanced_server.verify_password("Newpass1!", updated_private_user["password_hash"])
    assert advanced_server.delete_user(username) is True
    assert advanced_server.delete_user(username) is False
    assert advanced_server.get_user_by_username(username) is None


def test_create_user_duplicate_raises_conflict(username):
    advanced_server.create_user(username, "Passw0rd!")

    with pytest.raises(HTTPException) as exc_info:
        advanced_server.create_user(username, "Passw0rd!")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Username already exists"


def test_session_helpers_and_decode_refresh_token(username):
    user = register_user(username)
    refresh_token = advanced_server.auth.create_refresh_token(uid=username)
    refresh_payload = advanced_server.decode_refresh_token(refresh_token)
    session = advanced_server.create_session(user["id"], refresh_token)
    active_session = advanced_server.get_active_session(refresh_token)
    sessions = advanced_server.list_user_sessions(username)

    assert refresh_payload.sub == username
    assert refresh_payload.type == "refresh"
    assert session["refresh_jti"] == refresh_payload.jti
    assert active_session["username"] == username
    assert any(item["refresh_jti"] == refresh_payload.jti for item in sessions)
    assert advanced_server.revoke_session(refresh_token) is True
    assert advanced_server.revoke_session(refresh_token) is False
    assert advanced_server.get_active_session(refresh_token) is None


def test_decode_refresh_token_rejects_access_token(username):
    register_user(username)
    access_token, _ = issue_tokens_for(username)

    with pytest.raises(ValueError):
        advanced_server.decode_refresh_token(access_token)


def test_issue_token_pair_and_revoke_all_sessions(username):
    register_user(username)
    access_token, refresh_token = issue_tokens_for(username)
    active_session = advanced_server.get_active_session(refresh_token)
    revoked_count = advanced_server.revoke_all_user_sessions(username)

    assert access_token
    assert refresh_token
    assert active_session["username"] == username
    assert revoked_count >= 1
    assert advanced_server.get_active_session(refresh_token) is None


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
    assert login_response.json()["access_token"]
    assert login_response.json()["refresh_token"]
    assert root_response.status_code == 200
    assert "refresh" in root_response.json()["endpoints"]


def test_login_function_returns_token_pair(username):
    advanced_server.register(RegisterRequest(username=username, password="Passw0rd!"))
    token_pair = advanced_server.login(LoginRequest(username=username, password="Passw0rd!"))

    assert token_pair.token_type == "bearer"
    assert token_pair.access_token
    assert token_pair.refresh_token


def test_login_function_rejects_invalid_credentials(username):
    with pytest.raises(HTTPException) as missing_user_exc:
        advanced_server.login(LoginRequest(username=username, password="Passw0rd!"))

    advanced_server.register(RegisterRequest(username=username, password="Passw0rd!"))

    with pytest.raises(HTTPException) as bad_password_exc:
        advanced_server.login(LoginRequest(username=username, password="wrongPass1!"))

    assert missing_user_exc.value.status_code == 401
    assert bad_password_exc.value.status_code == 401


def test_refresh_rotate_logout_and_logout_all_routes(client, username):
    client.post("/register", json={"username": username, "password": "Passw0rd!"})
    login_response = client.post(
        "/login",
        json={"username": username, "password": "Passw0rd!"},
    )
    access_token = login_response.json()["access_token"]
    refresh_token = login_response.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    sessions_response = client.get("/me/sessions", headers=headers)
    refresh_response = client.post("/refresh", json={"refresh_token": refresh_token})
    rotate_response = client.post("/refresh/rotate", json={"refresh_token": refresh_token})
    rotated_refresh_token = rotate_response.json()["refresh_token"]
    old_refresh_response = client.post("/refresh", json={"refresh_token": refresh_token})
    rotated_refresh_response = client.post(
        "/refresh",
        json={"refresh_token": rotated_refresh_token},
    )
    logout_response = client.post("/logout", json={"refresh_token": rotated_refresh_token})
    logged_out_refresh_response = client.post(
        "/refresh",
        json={"refresh_token": rotated_refresh_token},
    )
    relogin_response = client.post(
        "/login",
        json={"username": username, "password": "Passw0rd!"},
    )
    logout_all_headers = {"Authorization": f"Bearer {relogin_response.json()['access_token']}"}
    logout_all_refresh_token = relogin_response.json()["refresh_token"]
    logout_all_response = client.post("/logout-all", headers=logout_all_headers)
    logout_all_refresh_response = client.post(
        "/refresh",
        json={"refresh_token": logout_all_refresh_token},
    )

    assert sessions_response.status_code == 200
    assert len(sessions_response.json()) >= 1
    assert refresh_response.status_code == 200
    assert rotate_response.status_code == 200
    assert old_refresh_response.status_code == 401
    assert rotated_refresh_response.status_code == 200
    assert logout_response.status_code == 200
    assert logged_out_refresh_response.status_code == 401
    assert logout_all_response.status_code == 200
    assert logout_all_response.json()["revoked_count"] >= 1
    assert logout_all_refresh_response.status_code == 401


def test_refresh_and_logout_functions_reject_invalid_tokens():
    with pytest.raises(HTTPException) as refresh_exc:
        advanced_server.refresh_token(RefreshRequest(refresh_token="not-a-jwt"))

    with pytest.raises(HTTPException) as rotate_exc:
        advanced_server.rotate_refresh_token(RefreshRequest(refresh_token="not-a-jwt"))

    with pytest.raises(HTTPException) as logout_exc:
        advanced_server.logout(RefreshRequest(refresh_token="not-a-jwt"))

    assert refresh_exc.value.status_code == 401
    assert rotate_exc.value.status_code == 401
    assert logout_exc.value.status_code == 404


def test_protected_me_update_password_and_delete_routes(client, username):
    client.post("/register", json={"username": username, "password": "Passw0rd!"})
    login_response = client.post(
        "/login",
        json={"username": username, "password": "Passw0rd!"},
    )
    access_token = login_response.json()["access_token"]
    refresh_token = login_response.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    me_response = client.get("/me", headers=headers)
    protected_response = client.get("/protected", headers=headers)
    update_response = client.put(
        "/me/password",
        headers=headers,
        json={"password": "Newpass1!"},
    )
    refresh_after_password_change_response = client.post(
        "/refresh",
        json={"refresh_token": refresh_token},
    )
    old_password_response = client.post(
        "/login",
        json={"username": username, "password": "Passw0rd!"},
    )
    new_password_response = client.post(
        "/login",
        json={"username": username, "password": "Newpass1!"},
    )
    delete_token = new_password_response.json()["access_token"]
    delete_response = client.delete("/me", headers={"Authorization": f"Bearer {delete_token}"})
    deleted_me_response = client.get("/me", headers={"Authorization": f"Bearer {delete_token}"})

    assert me_response.status_code == 200
    assert me_response.json()["username"] == username
    assert protected_response.status_code == 200
    assert protected_response.json()["username"] == username
    assert update_response.status_code == 200
    assert refresh_after_password_change_response.status_code == 401
    assert old_password_response.status_code == 401
    assert new_password_response.status_code == 200
    assert delete_response.status_code == 204
    assert deleted_me_response.status_code == 404


def test_protected_routes_reject_missing_token(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me/sessions").status_code == 401
    assert client.put("/me/password", json={"password": "Newpass1!"}).status_code == 401
    assert client.delete("/me").status_code == 401
    assert client.get("/protected").status_code == 401
    assert client.post("/logout-all").status_code == 401
