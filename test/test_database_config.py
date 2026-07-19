import constant


def clear_database_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_get_database_url_allows_local_default_outside_deployment(monkeypatch):
    clear_database_env(monkeypatch)

    assert constant.get_database_url() == constant.DEFAULT_DATABASE_URL


def test_get_database_url_uses_env_value(monkeypatch):
    clear_database_env(monkeypatch)
    database_url = "postgresql://postgres:@127.0.0.1:5432/myapp"
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert constant.get_database_url() == database_url
