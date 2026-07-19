import os
from urllib.parse import urlparse


# database path for local development only
DEFAULT_DATABASE_URL = "postgresql://postgres:@127.0.0.1:5432/myapp"
DEFAULT_JWT_SECRET_KEY = "dev-only-change-me-32-byte-secret-key"

_TRUTHY_VALUES = {"1", "true", "yes", "on"}
_ADMIN_DATABASE_NAMES = {"postgres", "template0", "template1"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY_VALUES


def validate_deployment_database_url(database_url: str) -> None:
    """Validate DATABASE_URL before running in deployment mode."""
    parsed_url = urlparse(database_url)
    if parsed_url.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError("DATABASE_URL must use postgresql:// or postgres://.")

    database_name = parsed_url.path.lstrip("/").split("/", 1)[0]
    if not database_name:
        raise RuntimeError("DATABASE_URL must include a database name.")

    if database_name in _ADMIN_DATABASE_NAMES:
        raise RuntimeError(f"Refusing to deploy against PostgreSQL admin database '{database_name}'.")


def get_database_url() -> str:
    """Return the configured database URL with optional deployment safety checks."""
    database_url = os.environ.get("DATABASE_URL")
    require_database_url = _env_flag("REQUIRE_DATABASE_URL") or _env_flag("REQUIRE_SAFE_DATABASE_URL")

    if not database_url:
        if require_database_url:
            raise RuntimeError("DATABASE_URL is required in deployment mode.")
        return DEFAULT_DATABASE_URL

    if _env_flag("REQUIRE_SAFE_DATABASE_URL"):
        validate_deployment_database_url(database_url)

    return database_url
