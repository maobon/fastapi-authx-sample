import contextlib

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from business.deps import (
    auth,
    database,
    verify_access_token,
    MINIO_BUCKET,
    init_http_client,
    close_http_client,
)
from business.auth_business import (
    create_user,
    get_user_by_username,
    update_user_password,
    delete_user,
    verify_password,
)
from business.news_router import router as news_router
from business.chat_router import router as chat_router
from utils.minio_manager import ensure_bucket_exists
from utils.logging_utils import setup_logging
from config import settings
from model import (
    LoginRequest,
    PasswordUpdateRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)


def init_database() -> None:
    """连接 PostgreSQL 数据库 `myapp`，并确保 `user_info` 表已经存在。"""
    database.init_database()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI 启动时初始化数据库，保证接口处理请求前表结构可用。"""
    setup_logging()
    database.open_pool()
    init_database()
    ensure_bucket_exists(MINIO_BUCKET)
    await init_http_client()
    yield
    await close_http_client()
    database.close_pool()


app = FastAPI(title="FastAPI+PostgreSQL AuthX App", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """全局 HTTP 请求日志中间件。"""
    head_pic = request.headers.get("head_pic")
    auth_header = "Present" if request.headers.get("authorization") else "Missing"
    msg = f">>> [HTTP] {request.method} {request.url.path} | Auth: {auth_header} | head_pic: {head_pic}"
    print(msg)
    response = await call_next(request)
    return response


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


@app.post("/login", response_model=TokenResponse)
def login(user: LoginRequest):
    """用户登录接口：查询用户、校验密码哈希，成功后签发 JWT Token。"""
    db_user = get_user_by_username(user.username, include_password_hash=True)
    if db_user is None or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    access_token = auth.create_access_token(uid=db_user["username"])
    return TokenResponse(access_token=access_token)


@app.get("/me", response_model=UserResponse)
async def read_me(request: Request):
    """查询当前登录用户信息。"""
    username = await verify_access_token(request)
    print(f"/me ${username} access token is passed...")
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


# 挂载业务模块
app.include_router(news_router)
app.include_router(chat_router)


@app.get("/")
def read_root():
    """公开接口：返回说明、数据库配置和可用接口列表。"""
    return {
        "message": "Welcome to AuthX PostgreSQL App",
        "database": {
            "url_env": "DATABASE_URL",
            "configured": True,
            "table": "user_info",
        },
        "endpoints": {
            "register": "POST /register - Register user",
            "login": "POST /login - Login and get JWT token",
            "me": "GET /me - Current user info",
            "api_news": "GET /api/news - List news",
            "api_news_audio": "GET /api/news-audio - List news audio",
            "ws": "WS /ws - Chat WebSocket",
            "upload": "POST /upload/pic - Upload image",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
