from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from .validators import (
    validate_login_password as ensure_login_password,
    validate_password as ensure_password,
    validate_username as ensure_username,
)


class RegisterRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=150,
        description="Desired username for registration",
        examples=["john_doe"]
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Secure password (at least 8 characters and two character types)",
        examples=["SecurePass123!"]
    )

    @field_validator("username")
    @classmethod
    def validate_register_username(cls, username: str) -> str:
        return ensure_username(username)

    @field_validator("password")
    @classmethod
    def validate_register_password(cls, password: str) -> str:
        return ensure_password(password)


class LoginRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=150,
        description="Username for authentication",
        examples=["john_doe"]
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Account password",
        examples=["SecurePass123!"]
    )

    @field_validator("username")
    @classmethod
    def validate_login_username(cls, username: str) -> str:
        return ensure_username(username)

    @field_validator("password")
    @classmethod
    def validate_login_password(cls, password: str) -> str:
        return ensure_login_password(password)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(
        ...,
        min_length=1,
        description="The refresh token string issued during login",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."]
    )


class PasswordUpdateRequest(BaseModel):
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="The new password to set",
        examples=["NewSecurePass99!"]
    )

    @field_validator("password")
    @classmethod
    def validate_update_password(cls, password: str) -> str:
        return ensure_password(password)


class UserResponse(BaseModel):
    id: int = Field(..., description="Unique user identifier", examples=[1])
    username: str = Field(..., description="The user's unique username", examples=["john_doe"])
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional user metadata (e.g., avatar_url)",
        examples=[{"avatar_url": "http://minio/images/avatar.jpg"}]
    )
    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Account last update timestamp")


class SessionResponse(BaseModel):
    id: int = Field(..., description="Session identifier", examples=[10])
    user_id: int = Field(..., description="Owner's user ID", examples=[1])
    refresh_jti: str = Field(..., description="Unique JTI for the refresh token")
    revoked: bool = Field(..., description="Whether the session has been revoked")
    expires_at: datetime = Field(..., description="Token expiration timestamp")
    created_at: datetime = Field(..., description="Session creation timestamp")
    revoked_at: Optional[datetime] = Field(None, description="Revocation timestamp if revoked")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token string")
    token_type: str = Field("bearer", description="Token type prefix")


class TokenPairResponse(BaseModel):
    access_token: str = Field(..., description="Short-lived JWT access token")
    refresh_token: str = Field(..., description="Long-lived JWT refresh token")
    token_type: str = Field("bearer", description="Token type prefix")


class AccessTokenResponse(BaseModel):
    access_token: str = Field(..., description="Renewed JWT access token")
    token_type: str = Field("bearer", description="Token type prefix")
