import pytest
from starlette.testclient import TestClient
from unittest.mock import MagicMock
import basic_server

@pytest.fixture
def client():
    with TestClient(basic_server.app) as test_client:
        yield test_client

@pytest.fixture
def token():
    """Generate a valid JWT token for testing."""
    return basic_server.auth.create_access_token(uid="TestUser")

def test_websocket_auth_failure(client):
    """Test that WebSocket connection fails without a valid token."""
    with pytest.raises(Exception): # TestClient raises an exception if the connection is rejected
        with client.websocket_connect("/ws") as websocket:
             pass

def test_websocket_chat_exchange_messages(client, token):
    """Test authenticated WebSocket message exchange."""
    # We use two users to test broadcasting
    token_a = basic_server.auth.create_access_token(uid="UserA")
    token_b = basic_server.auth.create_access_token(uid="UserB")

    with (
        client.websocket_connect(f"/ws?token={token_a}") as ws_a,
        client.websocket_connect(f"/ws?token={token_b}") as ws_b,
    ):
        # Consume join messages
        join_a = ws_a.receive_json()
        join_b_on_a = ws_a.receive_json()
        join_b = ws_b.receive_json()

        assert join_a["type"] == "system"
        assert "UserA 加入了聊天室" in join_a["content"]
        assert join_b["type"] == "system"
        assert "UserB 加入了聊天室" in join_b["content"]

        # Test text message
        text_msg = {"type": "text", "content": "Hello from A"}
        ws_a.send_json(text_msg)
        
        resp = ws_b.receive_json()
        assert resp["type"] == "text"
        assert resp["content"] == "Hello from A"
        assert resp["sender"] == "UserA"

def test_upload_image_to_minio(client, monkeypatch):
    """Test image upload logic."""
    # Mock minio_client in the business router where it is used
    mock_minio = MagicMock()
    monkeypatch.setattr("business.chat_router.minio_client", mock_minio)

    file_content = b"fake image content"
    response = client.post(
        "/upload/pic",
        files={"file": ("test.png", file_content, "image/png")}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["mime_type"] == "image/png"
    assert mock_minio.put_object.called

def test_websocket_image_message(client, token, monkeypatch):
    """Test sending an image message through WebSocket."""
    # Mock process_image_url in business.chat_business (it's called via handle_chat_session)
    # Actually, business.chat_business imports process_image_url from utils.chat_utils
    
    mock_info = {
        "success": True,
        "size": 1234,
        "mime_type": "image/jpeg"
    }
    
    # We need to mock it where it's used or where it's imported.
    # handle_chat_session is in business.chat_business
    async def fake_process_image_url(*args, **kwargs):
        return mock_info

    monkeypatch.setattr("business.chat_business.process_image_url", fake_process_image_url)

    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json() # join message
        
        image_url = "http://example.com/test.jpg"
        ws.send_json({"type": "image", "url": image_url})
        
        # In handle_chat_session, if it's the sender, it doesn't broadcast to itself.
        # Wait, ConnectionManager.broadcast: if connection is sender: continue
        # So I need another user to receive the message.
        
        token_b = basic_server.auth.create_access_token(uid="UserB")
        with client.websocket_connect(f"/ws?token={token_b}") as ws_b:
             ws.receive_json() # UserB joined
             ws_b.receive_json() # UserB joined (own)
             
             ws.send_json({"type": "image", "url": image_url})
             resp = ws_b.receive_json()
             
             assert resp["type"] == "image"
             assert resp["url"] == image_url
             assert "metadata" in resp
             assert resp["metadata"]["mime_type"] == "image/jpeg"
