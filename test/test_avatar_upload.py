import pytest
from starlette.testclient import TestClient
from unittest.mock import MagicMock, patch
import basic_server
from business.chat_business import handle_image_upload
from utils.database_utils import DatabaseUtils

@pytest.fixture
def client():
    with TestClient(basic_server.app) as test_client:
        yield test_client

@pytest.fixture
def token():
    """Generate a valid JWT token for testing."""
    return basic_server.auth.create_access_token(uid="TestUser")

def test_upload_avatar_flow(client, token, monkeypatch):
    """验证上传头像的完整流程，包括数据库更新调用。"""
    # 1. Mock MinIO 客户端
    mock_minio = MagicMock()
    monkeypatch.setattr("business.chat_router.minio_client", mock_minio)

    # 2. Mock 数据库工具
    mock_database = MagicMock()
    # 注意：handle_image_upload 内部是从 business.deps 导入 database 的
    monkeypatch.setattr("business.chat_business.database", mock_database)

    # 3. 准备文件数据
    file_content = b"fake avatar content"
    headers = {
        "Authorization": f"Bearer {token}",
        "head_pic": "true"
    }

    # 4. 发起请求
    response = client.post(
        "/upload/pic",
        headers=headers,
        files={"file": ("avatar.png", file_content, "image/png")}
    )

    # 5. 验证响应
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    image_url = data["url"]

    # 6. 验证 MinIO 是否被调用
    assert mock_minio.put_object.called

    # 7. 核心验证：验证数据库更新方法是否被正确调用
    # 预期的用户名是 'TestUser' (从 token 中解析)
    # 预期的参数是用户名和包含 avatar_url 的字典
    mock_database.update_user_extra.assert_called_once_with("TestUser", {"avatar_url": image_url})

def test_upload_normal_pic_no_db_update(client, token, monkeypatch):
    """验证普通图片上传不会触发数据库更新。"""
    mock_minio = MagicMock()
    monkeypatch.setattr("business.chat_router.minio_client", mock_minio)
    
    mock_database = MagicMock()
    monkeypatch.setattr("business.chat_business.database", mock_database)

    file_content = b"normal image content"
    headers = {
        "Authorization": f"Bearer {token}",
        "head_pic": "false" # 或者不传
    }

    response = client.post(
        "/upload/pic",
        headers=headers,
        files={"file": ("pic.png", file_content, "image/png")}
    )

    assert response.status_code == 200
    assert mock_database.update_user_extra.called is False

def test_database_utils_update_extra_sql(monkeypatch):
    """验证 DatabaseUtils.update_user_extra 生成的 SQL 语句是否正确。"""
    from utils import database_utils
    
    # Mock database_cursor 以便捕获执行的 SQL
    mock_cursor = MagicMock()
    @pytest.fixture
    def mock_db_cursor():
        yield mock_cursor

    # 手动模拟 contextmanager 行为
    class MockContextManager:
        def __enter__(self):
            return mock_cursor
        def __exit__(self, *args):
            pass

    def fake_database_cursor(url, row_factory=None):
        return MockContextManager()

    monkeypatch.setattr(database_utils, "database_cursor", fake_database_cursor)
    
    db_utils = DatabaseUtils("postgresql://dummy")
    db_utils.update_user_extra("test_user", {"avatar_url": "http://test.com/img.jpg"})
    
    # 验证是否调用了 execute
    assert mock_cursor.execute.called
    args, _ = mock_cursor.execute.call_args
    sql = args[0]
    params = args[1]
    
    # 验证 SQL 包含核心关键词
    assert "UPDATE user_info" in sql
    assert "extra = extra ||" in sql
    assert "WHERE username = %s" in sql
    
    # 验证参数
    assert params[1] == "test_user"
    # params[0] 应该是 psycopg.types.json.Jsonb 对象
    assert hasattr(params[0], "obj")
    assert params[0].obj == {"avatar_url": "http://test.com/img.jpg"}
