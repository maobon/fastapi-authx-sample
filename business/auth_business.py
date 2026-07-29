from typing import Optional
import psycopg
from fastapi import HTTPException, status
from authx.schema import TokenPayload
from utils.crypto_utils import hash_token, verify_password as _verify_password
from model import TokenPairResponse
from business.deps import auth, crypto, database


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


def create_user(username: str, password: str) -> dict:
    """注册用户：哈希密码后写入 `user_info` 表，并返回公开用户信息。"""
    password_hash = crypto.hash_password(password)
    try:
        return database.create_user(username, password_hash)
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists"
        ) from exc


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


def verify_password(password: str, hashed: str) -> bool:
    """校验明文密码是否与哈希值匹配。"""
    return _verify_password(password, hashed)


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


def issue_token_pair(user: dict) -> TokenPairResponse:
    """签发短期 access token 和长期 refresh token，并把 refresh session 入库。"""
    access_token = auth.create_access_token(uid=user["username"])
    refresh_token = auth.create_refresh_token(uid=user["username"])
    create_session(user["id"], refresh_token)
    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token)
