import pytest
from pathlib import Path
from pydantic import ValidationError

from src.core.config import bootstrap_env, Settings

def test_bootstrap_env_generates_secrets_on_first_startup(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "WRAP_MASTER_KEY=replace-with-at-least-32-random-characters\n"
        "ENVIRONMENT=development\n"
    )

    bootstrap_env(env_file)
    content = env_file.read_text()
    
    assert "replace-with-at-least-32-random-characters" not in content
    assert "WRAP_MASTER_KEY=" in content

    lines = content.splitlines()
    master_key = [line.split("=")[1] for line in lines if line.startswith("WRAP_MASTER_KEY=")][0]
    
    assert len(master_key) == 32
    
def test_bootstrap_env_adds_missing_secrets(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("ENVIRONMENT=development\n")

    bootstrap_env(env_file)
    content = env_file.read_text()
    
    assert "WRAP_MASTER_KEY=" in content

def test_bootstrap_env_preserves_existing_valid_secrets_on_subsequent_startup(tmp_path: Path):
    env_file = tmp_path / ".env"
    valid_master = "a" * 32
    env_file.write_text(
        f"WRAP_MASTER_KEY={valid_master}\n"
    )

    bootstrap_env(env_file)
    content = env_file.read_text()
    
    assert f"WRAP_MASTER_KEY={valid_master}" in content

def test_settings_rejects_placeholders_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("WRAP_MASTER_KEY", "replace-with-at-least-32-random-characters")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    
    assert "WRAP_MASTER_KEY placeholder cannot be used in production" in str(exc.value)
