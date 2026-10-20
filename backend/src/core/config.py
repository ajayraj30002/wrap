import secrets
import string
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


def bootstrap_env(env_path: Path) -> None:
    """Generate secure secrets if they are missing or equal to placeholders in .env."""
    if not env_path.exists():
        return

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    modified = False
    master_key_placeholder = "replace-with-at-least-32-random-characters"
    api_key_placeholder = "wrap_replace_with_a_long_random_gateway_key"

    has_master = False
    has_api = False

    def generate_key(length: int = 32) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    new_lines = []
    for line in lines:
        if line.startswith("WRAP_MASTER_KEY="):
            has_master = True
            val = line.split("=", 1)[1].strip("\"'")
            if val == master_key_placeholder or not val:
                line = f"WRAP_MASTER_KEY={generate_key(32)}"
                modified = True
        elif line.startswith("WRAP_API_KEYS="):
            has_api = True
            val = line.split("=", 1)[1].strip("\"'")
            if val == api_key_placeholder or not val:
                line = f"WRAP_API_KEYS=wrap_{generate_key(32)}"
                modified = True
        new_lines.append(line)

    if not has_master:
        new_lines.append(f"WRAP_MASTER_KEY={generate_key(32)}")
        modified = True

    if not has_api:
        new_lines.append(f"WRAP_API_KEYS=wrap_{generate_key(32)}")
        modified = True

    if modified:
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# Run bootstrap before reading settings
bootstrap_env(BASE_DIR / ".env")


class Settings(BaseSettings):
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str
    WRAP_MASTER_KEY: str
    WRAP_API_KEYS: str = Field(description="Comma-separated API keys accepted by WRAP.")

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    REQUEST_TIMEOUT_SECONDS: float = 300.0
    STREAM_IDLE_TIMEOUT_SECONDS: float = 120.0
    MAX_REQUEST_BYTES: int = 1_048_576
    CATALOG_REFRESH_INTERVAL_SECONDS: int = 21_600
    WORKER_HEALTH_CHECK_INTERVAL_SECONDS: float = 300.0
    DAG_MAX_NODES: int = 12
    DAG_MAX_DEPTH: int = 4
    DAG_MAX_PARALLEL_NODES: int = 6
    DAG_MAX_TOTAL_EXECUTION_SECONDS: int = 300
    DAG_MAX_RETRIES_PER_NODE: int = 3

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("WRAP_MASTER_KEY")
    @classmethod
    def validate_master_key(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        if len(value) < 32:
            raise ValueError("WRAP_MASTER_KEY must be at least 32 characters")
        if info.data.get("ENVIRONMENT") == "production" and value == "replace-with-at-least-32-random-characters":
            raise ValueError("WRAP_MASTER_KEY placeholder cannot be used in production")
        return value

    @field_validator("WRAP_API_KEYS")
    @classmethod
    def validate_api_keys(cls, value: str, info: ValidationInfo) -> str:
        keys = [item.strip() for item in value.split(",") if item.strip()]
        if not keys:
            raise ValueError("WRAP_API_KEYS must contain at least one key")
        if any(len(item) < 16 for item in keys):
            raise ValueError("Each WRAP API key must be at least 16 characters")
        if info.data.get("ENVIRONMENT") == "production" and "wrap_replace_with_a_long_random_gateway_key" in keys:
            raise ValueError("WRAP_API_KEYS placeholder cannot be used in production")
        return value

    @property
    def api_keys(self) -> set[str]:
        return {item.strip() for item in self.WRAP_API_KEYS.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
