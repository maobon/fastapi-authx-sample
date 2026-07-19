import os


# database path for local development only
DEFAULT_DATABASE_URL = "postgresql://postgres:@127.0.0.1:5432/myapp"
DEFAULT_JWT_SECRET_KEY = "dev-only-change-me-32-byte-secret-key"


def get_database_url() -> str:
    """Return DATABASE_URL from the environment or the shared default."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
