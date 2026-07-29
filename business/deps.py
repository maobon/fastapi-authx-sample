from datetime import timedelta
from fastapi import Request
from authx import AuthX, AuthXConfig
from config_loader import settings
from utils.database_utils import DatabaseUtils
from utils.crypto_utils import CryptoUtils
from utils.chat_utils import ConnectionManager, init_http_client, close_http_client
from utils.minio_manager import MINIO_BUCKET

# 全局共享变量
PASSWORD_HASH_ITERATIONS = 260_000
DEFAULT_NEWS_PAGE_SIZE = 20
MAX_NEWS_PAGE_SIZE = 100

database = DatabaseUtils(settings.database_url)
crypto = CryptoUtils(PASSWORD_HASH_ITERATIONS)
manager = ConnectionManager()

auth_config = AuthXConfig(
    JWT_ALGORITHM="HS256",
    JWT_SECRET_KEY=settings.jwt_secret_key,
    JWT_TOKEN_LOCATION=["headers", "json"],
    JWT_HEADER_TYPE="Bearer",
    JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=15),
    JWT_REFRESH_TOKEN_EXPIRES=timedelta(days=30),
)

auth = AuthX(config=auth_config)

async def verify_access_token(request: Request) -> str:
    """从请求头提取并校验 JWT Token，返回 Token subject 中的用户名。"""
    token = await auth.get_access_token_from_request(request)
    payload = auth.verify_token(token)
    return payload.sub

async def get_current_username(request: Request) -> str:
    """别名，用于高级服务器中更通用的命名。"""
    return await verify_access_token(request)
