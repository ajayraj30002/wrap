"""Tests for Alembic migration upgrade and downgrade for Phase 2C analytics."""

import asyncio
import importlib.util
import os
import asyncpg
import pytest
from alembic import command
from alembic.config import Config


def test_migration_script_structure():
    """Verify that the Phase 2C migration script is syntactically valid and exports required symbols."""
    spec = importlib.util.spec_from_file_location(
        "migration_phase2c",
        "alembic/versions/20260925_phase2c_analytics.py"
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "20260925_phase2c"
    assert mod.down_revision == "20260913_phase2b"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_hardening_migration_script_structure():
    """Verify that the Phase 2C hardening migration script is syntactically valid and exports required symbols."""
    spec = importlib.util.spec_from_file_location(
        "migration_phase2c_hardening",
        "alembic/versions/20260926_phase2c_hardening.py"
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "20260926_phase2c_hardening"
    assert mod.down_revision == "20260925_phase2c"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


@pytest.mark.asyncio
async def test_migration_upgrade_and_downgrade():
    """Verify that the Alembic migration history upgrades and downgrades without errors on PostgreSQL."""
    pg_url = os.environ.get("POSTGRES_TEST_URL", "postgresql+asyncpg://wrap:wrap@localhost:5433/wrap")
    is_pg_reachable = False
    try:
        conn = await asyncpg.connect("postgresql://wrap:wrap@localhost:5433/wrap", timeout=2)
        await conn.close()
        is_pg_reachable = True
    except Exception:
        pass

    if not is_pg_reachable:
        pytest.skip("PostgreSQL (port 5433) is not reachable, skipping live DDL migration test")

    old_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_url
    try:
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("script_location", "alembic")
        alembic_cfg.set_main_option("sqlalchemy.url", pg_url)
        # Ensure at head via to_thread since alembic/env.py calls asyncio.run()
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
        # Downgrade to 20260913_phase2b (prior to phase2c analytics)
        await asyncio.to_thread(command.downgrade, alembic_cfg, "20260913_phase2b")
        # Upgrade back to head
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    finally:
        if old_db_url:
            os.environ["DATABASE_URL"] = old_db_url
        else:
            os.environ.pop("DATABASE_URL", None)
