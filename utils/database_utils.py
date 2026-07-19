import re
from contextlib import contextmanager, suppress
from typing import Any, Iterator, Optional

import psycopg
from psycopg.rows import dict_row

from utils.database_sql import (
    CREATE_USER_INFO_TABLE,
    CREATE_USER_SESSIONS_TABLE,
    DELETE_USER_BY_USERNAME,
    INSERT_USER,
    INSERT_USER_SESSION,
    REVOKE_ALL_USER_SESSIONS_BY_USERNAME,
    REVOKE_SESSION_BY_REFRESH_TOKEN_HASH,
    SELECT_ACTIVE_SESSION_BY_REFRESH_TOKEN_HASH,
    SELECT_USER_BY_USERNAME,
    SELECT_USER_SESSIONS_BY_USERNAME,
    SELECT_USER_WITH_PASSWORD_HASH_BY_USERNAME,
    UPDATE_USER_PASSWORD,
)


_DROP_PATTERN = re.compile(r"\bDROP\s+(DATABASE|TABLE)\b", re.IGNORECASE)
_TRUNCATE_PATTERN = re.compile(r"\bTRUNCATE\b", re.IGNORECASE)


def _normalize_sql(query: Any) -> str:
    return " ".join(str(query).strip().split())


def validate_database_statement(query: Any) -> None:
    normalized_query = _normalize_sql(query)
    padded_query = f" {normalized_query.upper()} "

    if _DROP_PATTERN.search(normalized_query) or _TRUNCATE_PATTERN.search(normalized_query):
        raise ValueError("Unsafe database statement blocked")

    if padded_query.startswith(" DELETE FROM ") and " WHERE " not in padded_query:
        raise ValueError("Unsafe DELETE without WHERE blocked")

    if padded_query.startswith(" UPDATE ") and " WHERE " not in padded_query:
        raise ValueError("Unsafe UPDATE without WHERE blocked")


class SafeCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    def execute(self, query: Any, *args: Any, **kwargs: Any):
        validate_database_statement(query)
        return self._cursor.execute(query, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


def _connect(database_url: str, row_factory: Optional[Any] = None):
    if row_factory is None:
        return psycopg.connect(database_url)
    return psycopg.connect(database_url, row_factory=row_factory)


def _connection_is_open(connection: Any) -> bool:
    return not getattr(connection, "closed", False)


@contextmanager
def database_cursor(database_url: str, row_factory: Optional[Any] = None) -> Iterator[Any]:
    """Open a PostgreSQL cursor and always close or reset the transaction state."""
    connection = None
    try:
        connection = _connect(database_url, row_factory=row_factory)
        with connection.cursor() as cursor:
            yield SafeCursor(cursor)
        connection.commit()
    except Exception:
        if connection is not None and _connection_is_open(connection):
            with suppress(Exception):
                connection.rollback()
        raise
    finally:
        if connection is not None and _connection_is_open(connection):
            connection.close()


class DatabaseUtils:
    """PostgreSQL 数据库工具类，集中封装连接、建表和用户 CRUD 操作。"""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def init_database(self) -> None:
        """确保基础用户表存在。"""
        with database_cursor(self.database_url) as cursor:
            cursor.execute(CREATE_USER_INFO_TABLE)

    def init_advanced_database(self) -> None:
        """确保用户表和登录会话表都存在。"""
        with database_cursor(self.database_url) as cursor:
            cursor.execute(CREATE_USER_INFO_TABLE)
            cursor.execute(CREATE_USER_SESSIONS_TABLE)

    def create_user(self, username: str, password_hash: str) -> dict:
        """新增用户，返回公开用户信息。"""
        with database_cursor(self.database_url, row_factory=dict_row) as cursor:
            cursor.execute(
                INSERT_USER,
                (username, password_hash),
            )
            return cursor.fetchone()

    def get_user_by_username(self, username: str, include_password_hash: bool = False) -> Optional[dict]:
        """按用户名查询用户；登录场景可选择返回密码哈希。"""
        if include_password_hash:
            query = SELECT_USER_WITH_PASSWORD_HASH_BY_USERNAME
        else:
            query = SELECT_USER_BY_USERNAME

        with database_cursor(self.database_url, row_factory=dict_row) as cursor:
            cursor.execute(
                query,
                (username,),
            )
            return cursor.fetchone()

    def update_user_password(self, username: str, password_hash: str) -> Optional[dict]:
        """更新用户密码哈希。"""
        with database_cursor(self.database_url, row_factory=dict_row) as cursor:
            cursor.execute(
                UPDATE_USER_PASSWORD,
                (password_hash, username),
            )
            return cursor.fetchone()

    def delete_user(self, username: str) -> bool:
        """按用户名删除用户，返回是否删除成功。"""
        with database_cursor(self.database_url) as cursor:
            cursor.execute(DELETE_USER_BY_USERNAME, (username,))
            return cursor.rowcount > 0

    def create_session(
        self,
        user_id: int,
        refresh_token_hash: str,
        refresh_jti: str,
        expires_at,
    ) -> dict:
        """新增 refresh token 登录会话。"""
        with database_cursor(self.database_url, row_factory=dict_row) as cursor:
            cursor.execute(
                INSERT_USER_SESSION,
                (user_id, refresh_token_hash, refresh_jti, expires_at),
            )
            return cursor.fetchone()

    def get_active_session(self, refresh_token_hash: str) -> Optional[dict]:
        """按 refresh token 哈希查询未吊销、未过期的 session。"""
        with database_cursor(self.database_url, row_factory=dict_row) as cursor:
            cursor.execute(
                SELECT_ACTIVE_SESSION_BY_REFRESH_TOKEN_HASH,
                (refresh_token_hash,),
            )
            return cursor.fetchone()

    def revoke_session(self, refresh_token_hash: str) -> bool:
        """按 refresh token 哈希吊销单个 session。"""
        with database_cursor(self.database_url) as cursor:
            cursor.execute(
                REVOKE_SESSION_BY_REFRESH_TOKEN_HASH,
                (refresh_token_hash,),
            )
            return cursor.rowcount > 0

    def revoke_all_user_sessions(self, username: str) -> int:
        """吊销指定用户的所有 session。"""
        with database_cursor(self.database_url) as cursor:
            cursor.execute(
                REVOKE_ALL_USER_SESSIONS_BY_USERNAME,
                (username,),
            )
            return cursor.rowcount

    def list_user_sessions(self, username: str) -> list[dict]:
        """列出指定用户的所有 session。"""
        with database_cursor(self.database_url, row_factory=dict_row) as cursor:
            cursor.execute(
                SELECT_USER_SESSIONS_BY_USERNAME,
                (username,),
            )
            return cursor.fetchall()
