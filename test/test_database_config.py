import pytest

import constant


def clear_database_env(monkeypatch):
    for name in (
        "DATABASE_URL",
        "REQUIRE_DATABASE_URL",
        "REQUIRE_SAFE_DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_get_database_url_allows_local_default_outside_deployment(monkeypatch):
    clear_database_env(monkeypatch)

    assert constant.get_database_url() == constant.DEFAULT_DATABASE_URL


def test_get_database_url_requires_explicit_url_in_deployment(monkeypatch):
    clear_database_env(monkeypatch)
    monkeypatch.setenv("REQUIRE_DATABASE_URL", "1")

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        constant.get_database_url()


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://app:secret@127.0.0.1:5432/postgres",
        "postgresql://app:secret@127.0.0.1:5432/template1",
    ],
)
def test_get_database_url_blocks_unsafe_deployment_urls(monkeypatch, database_url):
    clear_database_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("REQUIRE_SAFE_DATABASE_URL", "1")

    with pytest.raises(RuntimeError):
        constant.get_database_url()


def test_get_database_url_accepts_postgres_empty_password_deployment_url(monkeypatch):
    clear_database_env(monkeypatch)
    database_url = "postgresql://postgres:@127.0.0.1:5432/myapp"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("REQUIRE_SAFE_DATABASE_URL", "1")

    assert constant.get_database_url() == database_url
