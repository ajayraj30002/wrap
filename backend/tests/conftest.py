import os
import sys
from pathlib import Path
import pytest

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Force an in-memory SQLite database and test secrets for tests to prevent wiping the development Postgres DB
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"
os.environ["WRAP_MASTER_KEY"] = "test_master_key_minimum_32_characters_long_12345"
os.environ["WRAP_API_KEYS"] = "wrap_test_api_key_minimum_16_chars_12345"


