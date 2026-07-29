from fastapi import APIRouter, HTTPException, Request, status
from model import AccessTokenResponse, RefreshRequest, SessionResponse, TokenPairResponse
from business.deps import auth, get_current_username
from business.auth_business import (
    decode_refresh_token,
    get_active_session,
    issue_token_pair,
    list_user_sessions,
    revoke_all_user_sessions,
    revoke_session,
)

router = APIRouter(tags=["advanced-auth"])


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_token(data: RefreshRequest):
    """续签 access token：refresh token 必须有效、未过期且 session 未被吊销。"""
    try:
        refresh_payload = decode_refresh_token(data.refresh_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        ) from exc

    session = get_active_session(data.refresh_token)
    if session is None or session["username"] != refresh_payload.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh session is not active"
        )

    access_token = auth.create_access_token(uid=refresh_payload.sub)
    return AccessTokenResponse(access_token=access_token)


@router.post("/refresh/rotate", response_model=TokenPairResponse)
def rotate_refresh_token(data: RefreshRequest):
    """轮换 refresh token：旧 session 立即吊销，新 refresh token 入库。"""
    try:
        refresh_payload = decode_refresh_token(data.refresh_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        ) from exc

    session = get_active_session(data.refresh_token)
    if session is None or session["username"] != refresh_payload.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh session is not active"
        )

    revoke_session(data.refresh_token)
    return issue_token_pair({"id": session["user_id"], "username": session["username"]})


@router.post("/logout")
def logout(data: RefreshRequest):
    """退出登录：吊销当前 refresh token 对应的 session。"""
    revoked = revoke_session(data.refresh_token)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh session not found"
        )
    return {"message": "Successfully logged out"}


@router.post("/logout-all")
async def logout_all(request: Request):
    """退出所有设备：吊销当前用户的全部 refresh token session。"""
    username = await get_current_username(request)
    revoked_count = revoke_all_user_sessions(username)
    return {"message": "All sessions revoked", "revoked_count": revoked_count}


@router.get("/me/sessions", response_model=list[SessionResponse])
async def read_my_sessions(request: Request):
    """查询当前用户的所有 refresh token session。"""
    username = await get_current_username(request)
    return list_user_sessions(username)
