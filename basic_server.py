import os
from contextlib import asynccontextmanager
from typing import Optional

import psycopg
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, status
from psycopg.rows import dict_row

from authx import AuthX, AuthXConfig

from business.database_sql import (
    SELECT_NEWS,
    SELECT_NEWS_AUDIO,
    SELECT_NEWS_AUDIO_PAGED,
    SELECT_NEWS_PAGED,
)
from constant import DEFAULT_JWT_SECRET_KEY, get_database_url
from utils.crypto_utils import CryptoUtils, verify_password
from utils.database_utils import DatabaseUtils, database_cursor
from model import LoginRequest, PasswordUpdateRequest, RegisterRequest, TokenResponse, UserResponse

DATABASE_URL = get_database_url()
PASSWORD_HASH_ITERATIONS = 260_000
DEFAULT_NEWS_PAGE_SIZE = 20
MAX_NEWS_PAGE_SIZE = 100
database = DatabaseUtils(DATABASE_URL)
crypto = CryptoUtils(PASSWORD_HASH_ITERATIONS)


def init_database() -> None:
    """连接 PostgreSQL 数据库 `myapp`，并确保 `user_info` 表已经存在。"""
    database.init_database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 启动时初始化数据库，保证接口处理请求前表结构可用。"""
    init_database()
    yield


app = FastAPI(title="FastAPI+PostgreSQL AuthX Sample", lifespan=lifespan)
protected_router = APIRouter(prefix="/api", tags=["router-protected"])

auth_config = AuthXConfig(
    JWT_ALGORITHM="HS256",
    JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY", DEFAULT_JWT_SECRET_KEY),
    JWT_TOKEN_LOCATION=["headers"],
    JWT_HEADER_TYPE="Bearer",
    JWT_ACCESS_TOKEN_EXPIRES=60 * 60 * 24,
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
    """删除当前用户记录；返回值表示数据库中是否实际删除了数据。"""
    return database.delete_user(username)


def list_news(page: Optional[int] = None, page_size: int = DEFAULT_NEWS_PAGE_SIZE) -> list[dict]:
    """读取 PostgreSQL 数据库中 `news` 表的新闻数据。"""
    with database_cursor(DATABASE_URL, row_factory=dict_row) as cursor:
        if page is None:
            cursor.execute(SELECT_NEWS)
        else:
            cursor.execute(
                SELECT_NEWS_PAGED,
                (page_size, (page - 1) * page_size),
            )
        return cursor.fetchall()


def list_news_audio(page: Optional[int] = None, page_size: int = DEFAULT_NEWS_PAGE_SIZE) -> list[dict]:
    """读取 PostgreSQL 数据库中 `news_audio` 表的音频新闻数据。"""
    with database_cursor(DATABASE_URL, row_factory=dict_row) as cursor:
        if page is None:
            cursor.execute(SELECT_NEWS_AUDIO)
        else:
            cursor.execute(
                SELECT_NEWS_AUDIO_PAGED,
                (page_size, (page - 1) * page_size),
            )
        return cursor.fetchall()


async def verify_access_token(request: Request) -> str:
    """从请求头提取并校验 JWT Token，返回 Token subject 中的用户名。"""
    token = await auth.get_access_token_from_request(request)
    payload = auth.verify_token(token)
    return payload.sub


@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: RegisterRequest):
    """用户注册接口：保存用户信息到 PostgreSQL。"""
    return create_user(user.username, user.password)


@app.post("/login", response_model=TokenResponse)
def login(user: LoginRequest):
    """用户登录接口：查询用户、校验密码哈希，成功后签发 JWT Token。"""
    db_user = get_user_by_username(user.username, include_password_hash=True)
    if db_user is None or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    access_token = auth.create_access_token(uid=db_user["username"])
    return TokenResponse(access_token=access_token)


@app.get("/me", response_model=UserResponse)
async def read_me(request: Request):
    """查询当前登录用户信息。"""
    username = await verify_access_token(request)
    db_user = get_user_by_username(username)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user


@app.put("/me/password", response_model=UserResponse)
async def update_me_password(request: Request, data: PasswordUpdateRequest):
    """修改当前登录用户密码。"""
    username = await verify_access_token(request)
    db_user = update_user_password(username, data.password)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user


@app.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(request: Request):
    """删除当前登录用户。"""
    username = await verify_access_token(request)
    if not delete_user(username):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"message": "You have delete your account", "username": username}


@app.get("/protected")
async def protected_route(request: Request):
    """受保护接口：这里的 `@app.get("/protected")` 就是在直接注册一个 route。"""
    username = await verify_access_token(request)
    return {"message": "You have access to this protected resource", "username": username}


@protected_router.get("/protected")
async def protected_router_route(request: Request):
    """APIRouter 示例：先把 route 注册到 router，再由 app.include_router 挂载。"""
    username = await verify_access_token(request)
    return {"message": "You have access to this router protected resource", "username": username}


@protected_router.get("/news")
async def protected_news(
    request: Request,
    page: Optional[int] = Query(default=None, ge=1),
    page_size: int = Query(default=DEFAULT_NEWS_PAGE_SIZE, ge=1, le=MAX_NEWS_PAGE_SIZE),
):
    """受保护新闻接口：JWT 校验通过后返回 `news` 表中的新闻数据。"""
    await verify_access_token(request)
    try:
        news = list_news(page=page, page_size=page_size)
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query news",
        ) from exc

    return {"news": news}


@app.get("/news-audio")
@protected_router.get("/news-audio")
async def protected_news_audio(
    request: Request,
    page: Optional[int] = Query(default=None, ge=1),
    page_size: int = Query(default=DEFAULT_NEWS_PAGE_SIZE, ge=1, le=MAX_NEWS_PAGE_SIZE),
):
    """受保护音频新闻接口：JWT 校验通过后返回 `news_audio` 表中的音频新闻数据。"""
    await verify_access_token(request)
    try:
        news_audio = list_news_audio(page=page, page_size=page_size)
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query news audio",
        ) from exc

    return {"news_audio": news_audio}


app.include_router(protected_router)


@app.get("/")
def read_root():
    """公开接口：返回示例说明、数据库配置和可用接口列表。"""
    return {
        "message": "Welcome to AuthX PostgreSQL Database Example",
        "database": {
            "url_env": "DATABASE_URL",
            "configured": bool(os.environ.get("DATABASE_URL")),
            "table": "user_info",
        },
        "endpoints": {
            "register": "POST /register - Create user_info record",
            "login": "POST /login - Verify password hash and get JWT token",
            "me": "GET /me - Read current user",
            "update_password": "PUT /me/password - Update current user's password",
            "delete_me": "DELETE /me - Delete current user",
            "protected": "GET /protected - Access protected resource",
            "news_audio": "GET /news-audio - List news_audio records after JWT verification",
            "router_protected": "GET /api/protected - Same protection implemented with APIRouter",
            "router_news": "GET /api/news - List news records after JWT verification",
            "router_news_audio": "GET /api/news-audio - List news_audio records after JWT verification",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
