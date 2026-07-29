import pytest
from starlette.testclient import TestClient
from unittest.mock import MagicMock
import basic_server
from business.deps import database

@pytest.fixture
def client():
    # 确保数据库工具是 Mock 的，避免连接真实 DB
    with TestClient(basic_server.app) as test_client:
        yield test_client

@pytest.fixture
def token():
    return basic_server.auth.create_access_token(uid="CycleUser")

def test_avatar_to_me_cycle(client, token, monkeypatch):
    """
    集成测试：
    1. 上传头像请求 -> 模拟 MinIO 上传 -> 触发数据库更新
    2. 请求 /me 接口 -> 获取数据库中的用户信息 -> 验证包含 avatar_url
    """
    # 1. 模拟数据存储状态
    # 我们用一个字典来模拟数据库中的用户信息
    stored_user = {
        "id": 999,
        "username": "CycleUser",
        "extra": {},
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01"
    }

    def mock_get_user(username, include_password_hash=False):
        if username == "CycleUser":
            return stored_user
        return None

    def mock_update_extra(username, extra_data):
        if username == "CycleUser":
            stored_user["extra"].update(extra_data)
            return stored_user
        return None

    # 2. 应用 Mock
    monkeypatch.setattr("business.chat_router.minio_client", MagicMock())
    monkeypatch.setattr("business.auth_business.database.get_user_by_username", mock_get_user)
    monkeypatch.setattr("business.chat_business.database.update_user_extra", mock_update_extra)
    # basic_server 也直接用了这些函数
    monkeypatch.setattr("basic_server.get_user_by_username", mock_get_user)

    # 3. 执行上传头像
    file_content = b"cycle test image"
    upload_response = client.post(
        "/upload/pic",
        headers={"Authorization": f"Bearer {token}", "head_pic": "true"},
        files={"file": ("test.jpg", file_content, "image/jpeg")}
    )
    assert upload_response.status_code == 200
    uploaded_url = upload_response.json()["url"]
    
    # 验证此时 mock 的 stored_user 是否已更新
    assert "avatar_url" in stored_user["extra"]
    assert stored_user["extra"]["avatar_url"] == uploaded_url

    # 4. 执行 /me 请求验证返回结果
    me_response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    me_data = me_response.json()
    
    # 核心验证点：extra 字段必须包含 avatar_url
    assert "extra" in me_data
    assert "avatar_url" in me_data["extra"]
    assert me_data["extra"]["avatar_url"] == uploaded_url
    
    print(f"\nSuccess: Integration cycle verified. /me returned avatar_url: {me_data['extra']['avatar_url']}")
