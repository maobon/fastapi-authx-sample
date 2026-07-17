from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from .validators import (
    validate_login_password as ensure_login_password,
    validate_password as ensure_password,
    validate_username as ensure_username,
)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_register_username(cls, username: str) -> str:
        return ensure_username(username)

    @field_validator("password")
    @classmethod
    def validate_register_password(cls, password: str) -> str:
        return ensure_password(password)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_login_username(cls, username: str) -> str:
        return ensure_username(username)

    @field_validator("password")
    @classmethod
    def validate_login_password(cls, password: str) -> str:
        return ensure_login_password(password)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class PasswordUpdateRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_update_password(cls, password: str) -> str:
        return ensure_password(password)


class UserResponse(BaseModel):
    id: int
    username: str
    extra: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SessionResponse(BaseModel):
    id: int
    user_id: int
    refresh_jti: str
    revoked: bool
    expires_at: datetime
    created_at: datetime
    revoked_at: Optional[datetime]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
