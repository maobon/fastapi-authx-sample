import os
import sys
from pathlib import Path
from typing import Optional

import psycopg
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constant import get_database_url
from business.database_sql import SELECT_NEWS, SELECT_NEWS_PAGED
from utils.database_utils import database_cursor


DATABASE_URL = get_database_url()
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

app = FastAPI(title="News Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def list_news(page: Optional[int] = None, page_size: int = DEFAULT_PAGE_SIZE) -> list[dict]:
    """读取 PostgreSQL `myapp` 数据库中的 `news` 表数据。"""
    with database_cursor(DATABASE_URL, row_factory=dict_row) as cursor:
        if page is None:
            cursor.execute(SELECT_NEWS)
        else:
            cursor.execute(
                SELECT_NEWS_PAGED,
                (page_size, (page - 1) * page_size),
            )
        return cursor.fetchall()


@app.get("/news")
def get_news(
    page: Optional[int] = Query(default=None, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    """返回新闻列表，默认返回全部；传入 `page` 时按页返回。"""
    try:
        news = list_news(page=page, page_size=page_size)
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query news",
        ) from exc

    return {"news": news}


@app.get("/")
def read_root():
    """返回业务服务说明。"""
    return {
        "message": "Welcome to News Service",
        "database": {
            "url_env": "DATABASE_URL",
            "configured": bool(os.environ.get("DATABASE_URL")),
            "table": "news",
        },
        "endpoints": {
            "news": "GET /news - List news records",
            "news_paged": "GET /news?page=1&page_size=20 - List news records by page",
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
