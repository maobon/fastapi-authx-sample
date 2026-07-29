import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Disable database pooling during tests to allow psycopg.connect mocking
from config_loader import settings
settings.disable_db_pool = True
