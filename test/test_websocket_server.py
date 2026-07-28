from starlette.testclient import TestClient

import websocket_server


def test_service_registers_expected_routes():
    # 现在有 /ws 和 /upload/pic 两个路由
    routes = [route.path for route in websocket_server.app.routes]
    assert "/ws" in routes
    assert "/upload/pic" in routes


def test_two_websocket_clients_exchange_json_messages():
    with TestClient(websocket_server.app) as client:
        with (
            client.websocket_connect("/ws?user_id=device_a") as device_a,
            client.websocket_connect("/ws?user_id=device_b") as device_b,
        ):
            # 消耗掉加入消息 (system)
            join_a = device_a.receive_json()
            join_b_on_a = device_a.receive_json()
            join_b = device_b.receive_json()
            
            assert join_a["type"] == "system"
            assert "device_a" in join_a["content"]
            assert join_b["type"] == "system"
            assert "device_b" in join_b["content"]

            # 测试普通文本消息
            text_msg = {"type": "text", "content": "message from web"}
            device_a.send_json(text_msg)
            
            resp = device_b.receive_json()
            assert resp["type"] == "text"
            assert resp["content"] == text_msg["content"]
            assert resp["sender"] == "device_a"
            assert "timestamp" in resp

            # 测试图片 URL 消息 (有效)
            image_url = "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png"
            image_msg = {"type": "image", "url": image_url}
            device_b.send_json(image_msg)
            
            resp = device_a.receive_json()
            assert resp["type"] == "image"
            assert resp["url"] == image_url
            assert resp["sender"] == "device_b"
            assert "metadata" in resp
            assert resp["metadata"]["mime_type"] == "image/png"

            # 测试普通非 JSON 文本消息
            raw_text = "hello world, this is not json"
            device_b.send_text(raw_text)
            resp = device_a.receive_json()
            assert resp["type"] == "text"
            assert resp["content"] == raw_text
            assert resp["sender"] == "device_b"

        # 离开 test_two_websocket_clients_exchange_json_messages 作用域后，连接关闭
        # 此时可以另外开启一个连接来接收“离开”通知 (这里逻辑稍微复杂，略过或增加专门测试)

def test_user_leave_notification():
    with TestClient(websocket_server.app) as client:
        with client.websocket_connect("/ws?user_id=Alice") as alice:
            # 消耗加入消息
            alice.receive_json()
            
            with client.websocket_connect("/ws?user_id=Bob") as bob:
                # Alice 收到 Bob 加入的消息
                alice.receive_json()
                # Bob 收到自己的加入消息
                bob.receive_json()
            
            # Bob 断开后，Alice 应该收到 Bob 离开的消息
            leave_msg = alice.receive_json()
            assert leave_msg["type"] == "system"
            assert "Bob 离开了聊天室" in leave_msg["content"]


def test_upload_image_to_minio(monkeypatch):
    from unittest.mock import MagicMock

    # Mock Minio client
    mock_minio = MagicMock()
    monkeypatch.setattr("websocket_server.minio_client", mock_minio)

    with TestClient(websocket_server.app) as client:
        file_content = b"fake image content"
        # 测试有效图片上传
        response = client.post(
            "/upload/pic",
            files={"file": ("test.png", file_content, "image/png")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # 不再有 local/ 前缀，且 image_id 就是 UUID + 扩展名
        assert "/" not in data["image_id"]
        assert "url" in data
        assert data["size"] == len(file_content)
        assert data["mime_type"] == "image/png"

        # 验证 Minio 的 put_object 是否被调用
        assert mock_minio.put_object.called

        # 测试非图片文件上传
        response = client.post(
            "/upload/pic",
            files={"file": ("test.txt", b"not an image", "text/plain")}
        )
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "Only images are allowed" in data["error"]

    assert websocket_server.manager.active_connections == {}
