from typing import Optional
import psycopg
from fastapi import APIRouter, HTTPException, Query, Request, status
from psycopg.rows import dict_row

from business.database_sql import (
    SELECT_NEWS,
    SELECT_NEWS_AUDIO,
    SELECT_NEWS_AUDIO_PAGED,
    SELECT_NEWS_PAGED,
)
from utils.database_utils import database_cursor
from business.deps import DATABASE_URL, DEFAULT_NEWS_PAGE_SIZE, MAX_NEWS_PAGE_SIZE, verify_access_token

router = APIRouter(prefix="/api", tags=["news"])

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

@router.get("/news")
async def get_news(
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

@router.get("/news-audio")
async def get_news_audio(
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
