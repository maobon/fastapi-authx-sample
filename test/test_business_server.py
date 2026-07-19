from datetime import date

from starlette.testclient import TestClient
from psycopg.rows import dict_row

import business.server as business_server


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_get_news_returns_json(monkeypatch):
    rows = [
        {
            "id": 1,
            "title": "Test News",
            "url": "https://example.com/news/1",
            "image": "https://example.com/image.jpg",
            "summary": "A short summary",
            "date": date(2026, 7, 18),
            "img": None,
        }
    ]
    cursor = FakeCursor(rows)

    def fake_connect(database_url, row_factory):
        assert database_url == business_server.DATABASE_URL
        assert row_factory is dict_row
        return FakeConnection(cursor)

    monkeypatch.setattr(business_server.psycopg, "connect", fake_connect)

    response = TestClient(business_server.app).get("/news")

    assert response.status_code == 200
    assert response.json() == {
        "news": [
            {
                "id": 1,
                "title": "Test News",
                "url": "https://example.com/news/1",
                "image": "https://example.com/image.jpg",
                "summary": "A short summary",
                "date": "2026-07-18",
                "img": None,
            }
        ]
    }
    assert "FROM news" in cursor.query
    assert cursor.params is None


def test_get_news_uses_pagination(monkeypatch):
    cursor = FakeCursor([])

    def fake_connect(database_url, row_factory):
        return FakeConnection(cursor)

    monkeypatch.setattr(business_server.psycopg, "connect", fake_connect)

    response = TestClient(business_server.app).get("/news?page=2&page_size=10")

    assert response.status_code == 200
    assert response.json() == {"news": []}
    assert "LIMIT %s OFFSET %s" in cursor.query
    assert cursor.params == (10, 10)
