"""DB backend switch tests (harness-platform-integration 1.1/3.3).

Covers URL conversion, a full sqlite round-trip via HarnessDB, and the
server registration smoke. The central-PG round-trip itself was verified
live against fd_open_data (discovery write/read/delete) during rollout.
"""
from __future__ import annotations

import asyncio

import pytest

from fd_scraw_harness.db import HarnessDB, _async_url


def test_async_url_conversions():
    assert _async_url("sqlite:///data/harness.db") == "sqlite+aiosqlite:///data/harness.db"
    assert _async_url("postgresql://fd:p@h:1/db") == "postgresql+asyncpg://fd:p@h:1/db"
    assert _async_url("postgresql+psycopg2://fd:p@h/db") == "postgresql+asyncpg://fd:p@h/db"
    assert _async_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"


def test_anonymized_url_masks_password():
    db = HarnessDB("postgresql://fd:secret@host:5432/name")
    assert "secret" not in db.database_url
    assert db.database_url.startswith("postgresql://fd:***@")


@pytest.mark.asyncio
async def test_sqlite_round_trip(tmp_path):
    db = HarnessDB(f"sqlite:///{tmp_path / 't.db'}")

    async def flow():
        await db.init_db()
        async with db.async_session() as sess:
            from fd_scraw_harness.models import Discovery

            sess.add(Discovery(query="q", status="done"))
            await sess.commit()
        async with db.async_session() as sess:
            from sqlalchemy import select

            from fd_scraw_harness.models import Discovery

            rows = (await sess.execute(select(Discovery))).scalars().all()
            assert len(rows) == 1 and rows[0].query == "q"

    await asyncio.get_event_loop().run_in_executor(None, lambda: None)
    await flow()
    await db.dispose()


@pytest.mark.asyncio
async def test_server_registers_twelve_tools():
    from fd_scraw_harness.server import app

    tools = await app.list_tools()
    names = {t.name for t in tools}
    assert len(names) == 12
    assert {"discover_sources", "generate_manifest", "export_manifest",
            "test_spider", "harness_status"} <= names
