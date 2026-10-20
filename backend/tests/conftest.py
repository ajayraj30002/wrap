import os
import pytest

# Force an in-memory SQLite database for tests to prevent wiping the development Postgres DB
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"
