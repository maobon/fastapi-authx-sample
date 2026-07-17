import os
from contextlib import asynccontextmanager
from typing import Optional

import psycopg
from fastapi import FastAPI, HTTPException, Request, status

from authx import AuthX, AuthXConfig
from authx.schema import TokenPayload
from utils.crypto_utils import CryptoUtils, hash_token, verify_password
from utils.database_utils import DatabaseUtils
from model import (
    AccessTokenResponse,
    LoginRequest,
    PasswordUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
    TokenPairResponse,
    UserResponse,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql:///myapp")
PASSWORD_HASH_ITERATIONS = 260_000
database = DatabaseUtils(DATABASE_URL)
crypto = CryptoUtils(PASSWORD_HASH_ITERATIONS)


def decode_refresh_token(refresh_token: str) -> TokenPayload:
    """解码并校验 refresh token；这里处理的是请求体里的原始 JWT 字符串。"""
    payload = TokenPayload.decode(
        token=refresh_token,
        key=auth.config.public_key,
        algorithms=[auth.config.JWT_ALGORITHM],
        audience=auth.config.JWT_DECODE_AUDIENCE,
        issuer=auth.config.JWT_DECODE_ISSUER,
    )
    if payload.type != "refresh":
        raise ValueError("Refresh token required")
    return payload


def init_database() -> None:
    """初始化用户表和登录会话表。"""
    database.init_advanced_database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 启动时初始化数据库，保证接口处理请求前表结构可用。"""
    init_database()
    yield


app = FastAPI(title="FastAPI+PostgreSQL AuthX Sample", lifespan=lifespan)

auth_config = AuthXConfig(
    JWT_ALGORITHM="HS256",
    JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY", "your-secret-key"),
    JWT_TOKEN_LOCATION=["headers", "json"],
    JWT_HEADER_TYPE="Bearer",
    JWT_ACCESS_TOKEN_EXPIRES=60 * 15,
    JWT_REFRESH_TOKEN_EXPIRES=60 * 60 * 24 * 30,
)

auth = AuthX(config=auth_config)
auth.handle_errors(app)


def create_user(username: str, password: str) -> dict:
    """注册用户：哈希密码后写入 `user_info` 表，并返回公开用户信息。"""
    password_hash = crypto.hash_password(password)
    try:
        return database.create_user(username, password_hash)
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists") from exc


def get_user_by_username(username: str, include_password_hash: bool = False) -> Optional[dict]:
    """按用户名查询用户；登录场景才返回 `password_hash` 用于密码校验。"""
    return database.get_user_by_username(username, include_password_hash=include_password_hash)


def update_user_password(username: str, password: str) -> Optional[dict]:
    """更新当前用户密码：重新生成密码哈希，并刷新 `updated_at` 时间。"""
    password_hash = crypto.hash_password(password)
    return database.update_user_password(username, password_hash)


def delete_user(username: str) -> bool:
    """删除当前用户记录；级联删除该用户的所有 session。"""
    return database.delete_user(username)


def create_session(user_id: int, refresh_token: str) -> dict:
    """保存 refresh token 对应的登录会话；数据库保存哈希和 jti，不保存原始 token。"""
    refresh_payload = decode_refresh_token(refresh_token)
    return database.create_session(
        user_id=user_id,
        refresh_token_hash=hash_token(refresh_token),
        refresh_jti=refresh_payload.jti,
        expires_at=refresh_payload.expiry_datetime,
    )


def get_active_session(refresh_token: str) -> Optional[dict]:
    """根据 refresh token 查询未吊销、未过期的 session。"""
    return database.get_active_session(hash_token(refresh_token))


def revoke_session(refresh_token: str) -> bool:
    """吊销指定 refresh token 对应的 session，用于退出登录或 token 轮换。"""
    return database.revoke_session(hash_token(refresh_token))


def revoke_all_user_sessions(username: str) -> int:
    """吊销某个用户的全部 session，适合修改密码后让所有设备重新登录。"""
    return database.revoke_all_user_sessions(username)


def list_user_sessions(username: str) -> list[dict]:
    """列出当前用户的 session，便于查看多设备登录和吊销状态。"""
    return database.list_user_sessions(username)


async def get_current_username(request: Request) -> str:
    """从请求头提取并校验 access token，返回 token subject 中的用户名。"""
    token = await auth.get_access_token_from_request(request)
    payload = auth.verify_token(token)
    return payload.sub


def issue_token_pair(user: dict) -> TokenPairResponse:
    """签发短期 access token 和长期 refresh token，并把 refresh session 入库。"""
    access_token = auth.create_access_token(uid=user["username"])
    refresh_token = auth.create_refresh_token(uid=user["username"])
    create_session(user["id"], refresh_token)
    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token)


@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: RegisterRequest):
    """用户注册接口：保存用户信息到 PostgreSQL。"""
    return create_user(user.username, user.password)


@app.post("/login", response_model=TokenPairResponse)
def login(user: LoginRequest):
    """用户登录接口：校验密码后签发 access token，并保存 refresh token session。"""
    db_user = get_user_by_username(user.username, include_password_hash=True)
    if db_user is None or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    return issue_token_pair(db_user)


@app.post("/refresh", response_model=AccessTokenResponse)
def refresh_token(data: RefreshRequest):
    """续签 access token：refresh token 必须有效、未过期且 session 未被吊销。"""
    try:
        refresh_payload = decode_refresh_token(data.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    session = get_active_session(data.refresh_token)
    if session is None or session["username"] != refresh_payload.sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session is not active")

    access_token = auth.create_access_token(uid=refresh_payload.sub)
    return AccessTokenResponse(access_token=access_token)


@app.post("/refresh/rotate", response_model=TokenPairResponse)
def rotate_refresh_token(data: RefreshRequest):
    """轮换 refresh token：旧 session 立即吊销，新 refresh token 入库。"""
    try:
        refresh_payload = decode_refresh_token(data.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    session = get_active_session(data.refresh_token)
    if session is None or session["username"] != refresh_payload.sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session is not active")

    revoke_session(data.refresh_token)
    return issue_token_pair({"id": session["user_id"], "username": session["username"]})


@app.post("/logout")
def logout(data: RefreshRequest):
    """退出登录：吊销当前 refresh token 对应的 session。"""
    revoked = revoke_session(data.refresh_token)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refresh session not found")
    return {"message": "Successfully logged out"}


@app.post("/logout-all")
async def logout_all(request: Request):
    """退出所有设备：吊销当前用户的全部 refresh token session。"""
    username = await get_current_username(request)
    revoked_count = revoke_all_user_sessions(username)
    return {"message": "All sessions revoked", "revoked_count": revoked_count}


@app.get("/me", response_model=UserResponse)
async def read_me(request: Request):
    """查询当前登录用户信息。"""
    username = await get_current_username(request)
    db_user = get_user_by_username(username)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user


@app.get("/me/sessions", response_model=list[SessionResponse])
async def read_my_sessions(request: Request):
    """查询当前用户的所有 refresh token session。"""
    username = await get_current_username(request)
    return list_user_sessions(username)


@app.put("/me/password", response_model=UserResponse)
async def update_me_password(request: Request, data: PasswordUpdateRequest):
    """修改当前登录用户密码，并吊销该用户所有 refresh token session。"""
    username = await get_current_username(request)
    db_user = update_user_password(username, data.password)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    revoke_all_user_sessions(username)
    return db_user


@app.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(request: Request):
    """删除当前登录用户；`user_sessions` 会通过外键级联删除。"""
    username = await get_current_username(request)
    if not delete_user(username):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return None


@app.get("/protected")
async def protected_route(request: Request):
    """受保护接口：只有携带有效 access token 的请求才能访问。"""
    username = await get_current_username(request)
    return {"message": "You have access to this protected resource", "username": username}


@app.get("/")
def read_root():
    """公开接口：返回高级示例说明、数据库配置和可用接口列表。"""
    return {
        "message": "Welcome to AuthX PostgreSQL Advanced Database Example",
        "database": {
            "url_env": "DATABASE_URL",
            "default": "postgresql:///myapp",
            "tables": ["user_info", "user_sessions"],
        },
        "token_storage": {
            "access_token": "not stored; short-lived JWT verified by signature",
            "refresh_token": "stored as SHA-256 hash in user_sessions",
        },
        "endpoints": {
            "register": "POST /register - Create user_info record",
            "login": "POST /login - Get access and refresh tokens",
            "refresh": "POST /refresh - Get a new access token",
            "rotate": "POST /refresh/rotate - Rotate refresh token",
            "logout": "POST /logout - Revoke one refresh token session",
            "logout_all": "POST /logout-all - Revoke all current user's sessions",
            "sessions": "GET /me/sessions - List current user's sessions",
            "protected": "GET /protected - Access protected resource",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
