import contextlib
import os

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from business.deps import (
    auth,
    database,
    get_current_username,
    init_http_client,
    close_http_client,
    MINIO_BUCKET,
)
from business.auth_business import (
    create_user,
    get_user_by_username,
    issue_token_pair,
    update_user_password,
    delete_user,
    verify_password,
    revoke_all_user_sessions,
)
from business.news_router import router as news_router
from business.chat_router import router as chat_router
from business.advanced_auth_router import router as advanced_auth_router
from utils.minio_manager import ensure_bucket_exists
from utils.logging_utils import setup_logging
from model import (
    LoginRequest,
    PasswordUpdateRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)

def init_database() -> None:
    """初始化用户表和登录会话表。"""
    database.init_advanced_database()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 启动时初始化数据库，保证接口处理请求前表结构可用。"""
    setup_logging()
    init_database()
    ensure_bucket_exists(MINIO_BUCKET)
    await init_http_client()
    yield
    await close_http_client()


app = FastAPI(title="FastAPI+PostgreSQL AuthX Advanced App", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

auth.handle_errors(app)


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


@app.get("/me", response_model=UserResponse)
async def read_me(request: Request):
    """查询当前登录用户信息。"""
    username = await get_current_username(request)
    db_user = get_user_by_username(username)
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user


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


# advanced JWT features
app.include_router(advanced_auth_router)

# 挂载业务模块
app.include_router(news_router)
app.include_router(chat_router)


@app.get("/")
def read_root():
    """公开接口：返回说明、数据库配置和可用接口列表。"""
    return {
        "message": "Welcome to AuthX PostgreSQL Advanced App",
        "database": {
            "url_env": "DATABASE_URL",
            "configured": bool(os.environ.get("DATABASE_URL")),
            "tables": ["user_info", "user_sessions"],
        },
        "endpoints": {
            "register": "POST /register - Register user",
            "login": "POST /login - Login and get token pair",
            "refresh": "POST /refresh - Refresh access token",
            "me": "GET /me - Current user info",
            "api_news": "GET /api/news - List news",
            "api_news_audio": "GET /api/news-audio - List news audio",
            "ws": "WS /ws - Chat WebSocket",
            "upload": "POST /upload/pic - Upload image",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
