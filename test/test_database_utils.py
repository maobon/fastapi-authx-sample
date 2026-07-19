import pytest
import psycopg
from psycopg.rows import dict_row

from utils import database_utils


class FakeCursor:
    def __init__(self, error=None):
        self.error = error
        self.query = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query):
        self.query = query
        if self.error is not None:
            raise self.error


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_database_cursor_commits_and_closes_on_success(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    connect_calls = []

    def fake_connect(database_url, row_factory=None):
        connect_calls.append((database_url, row_factory))
        return connection

    monkeypatch.setattr(database_utils.psycopg, "connect", fake_connect)

    with database_utils.database_cursor("postgresql://test", row_factory=dict_row) as db_cursor:
        db_cursor.execute("SELECT 1")

    assert connect_calls == [("postgresql://test", dict_row)]
    assert cursor.query == "SELECT 1"
    assert connection.committed is True
    assert connection.rolled_back is False
    assert connection.closed is True


def test_database_cursor_rolls_back_and_closes_on_error(monkeypatch):
    cursor = FakeCursor(error=psycopg.OperationalError("connection failed"))
    connection = FakeConnection(cursor)

    def fake_connect(database_url, row_factory=None):
        return connection

    monkeypatch.setattr(database_utils.psycopg, "connect", fake_connect)

    with pytest.raises(psycopg.OperationalError):
        with database_utils.database_cursor("postgresql://test") as db_cursor:
            db_cursor.execute("SELECT 1")

    assert connection.committed is False
    assert connection.rolled_back is True
    assert connection.closed is True


@pytest.mark.parametrize(
    "query",
    [
        "DROP DATABASE myapp",
        "DROP TABLE user_info",
        "TRUNCATE news",
        "DELETE FROM user_info",
        "UPDATE user_info SET username = 'bad'",
    ],
)
def test_validate_database_statement_blocks_unsafe_sql(query):
    with pytest.raises(ValueError):
        database_utils.validate_database_statement(query)


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM user_info WHERE username = %s",
        "UPDATE user_info SET password_hash = %s WHERE username = %s",
        "SELECT * FROM news",
        "CREATE TABLE IF NOT EXISTS user_info (id BIGINT PRIMARY KEY)",
    ],
)
def test_validate_database_statement_allows_expected_sql(query):
    database_utils.validate_database_statement(query)


def test_database_cursor_rolls_back_and_closes_when_unsafe_sql_is_blocked(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)

    def fake_connect(database_url, row_factory=None):
        return connection

    monkeypatch.setattr(database_utils.psycopg, "connect", fake_connect)

    with pytest.raises(ValueError):
        with database_utils.database_cursor("postgresql://test") as db_cursor:
            db_cursor.execute("DROP DATABASE myapp")

    assert cursor.query is None
    assert connection.committed is False
    assert connection.rolled_back is True
    assert connection.closed is True
