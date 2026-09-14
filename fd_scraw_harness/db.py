"""Database layer: sync + async SQLAlchemy engines for SQLite and PostgreSQL."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from fd_scraw_harness.models import Base

logger = logging.getLogger(__name__)

_DEFAULT_SQLITE_PATH = "data/harness.db"
_ENV_VAR = "HARNESS_DATABASE_URL"


def _build_url() -> str:
    url = os.environ.get(_ENV_VAR)
    if url:
        return url
    return f"sqlite:///{_DEFAULT_SQLITE_PATH}"


def _async_url(sync_url: str) -> str:
    """Convert a sync DB URL to its async driver equivalent."""
    if sync_url.startswith("sqlite:///") and "+aiosqlite" not in sync_url:
        return sync_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if sync_url.startswith("postgresql://"):
        return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if sync_url.startswith("postgresql+psycopg2://"):
        return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    return sync_url


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///") and not url.endswith(":memory:"):
        db_path = url.replace("sqlite:///", "", 1)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


class HarnessDB:
    def __init__(self, database_url: Optional[str] = None):
        self._database_url = database_url or _build_url()
        self._engine: Optional[Engine] = None
        self._async_engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._async_session_factory: Optional[sessionmaker] = None

    @property
    def database_url(self) -> str:
        url = self._database_url
        if "@" in url and "://" in url:
            scheme, rest = url.split("://", 1)
            if ":" in rest.split("@", 1)[0]:
                creds, host = rest.split("@", 1)
                user = creds.split(":", 1)[0]
                return f"{scheme}://{user}:***@{host}"
        return url

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._init_engine()
        assert self._engine is not None
        return self._engine

    @property
    def async_engine(self) -> AsyncEngine:
        if self._async_engine is None:
            self._init_engine()
        assert self._async_engine is not None
        return self._async_engine

    def _init_engine(self) -> None:
        url = self._database_url
        _ensure_sqlite_dir(url)
        self._engine = create_engine(url, echo=False, future=True)
        if url.startswith("sqlite"):
            @event.listens_for(self._engine, "connect")
            def _set_wal(dbapi_conn, _conn_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
        self._session_factory = sessionmaker(bind=self._engine, future=True)

        aurl = _async_url(url)
        self._async_engine = create_async_engine(aurl, echo=False, future=True)
        if url.startswith("sqlite"):
            @event.listens_for(self._async_engine.sync_engine, "connect")
            def _set_wal_async(dbapi_conn, _conn_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
        self._async_session_factory = sessionmaker(
            bind=self._async_engine, class_=AsyncSession, expire_on_commit=False,
        )
        logger.info("harness DB ready (database: %s)", self.database_url)

    def get_session(self) -> Session:
        if self._session_factory is None:
            self._init_engine()
        assert self._session_factory is not None
        return self._session_factory()

    @asynccontextmanager
    async def async_session(self):
        if self._async_session_factory is None:
            self._init_engine()
        assert self._async_session_factory is not None
        async with self._async_session_factory() as sess:
            yield sess

    async def init_db(self) -> None:
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def init_db_sync(self) -> None:
        self.engine.connect()
        Base.metadata.create_all(self.engine)

    def test_connection(self) -> None:
        try:
            with self.engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
        except Exception as e:
            raise RuntimeError(
                f"Cannot connect to database ({self.database_url}): {e}"
            ) from e

    async def dispose(self) -> None:
        if self._async_engine is not None:
            await self._async_engine.dispose()
            self._async_engine = None
            self._async_session_factory = None
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None


_default_db: Optional[HarnessDB] = None


def get_db() -> HarnessDB:
    global _default_db
    if _default_db is None:
        _default_db = HarnessDB()
        _default_db.init_db_sync()
    return _default_db


async def async_init_db() -> None:
    db = get_db()
    await db.init_db()


def init_db() -> None:
    get_db().init_db_sync()


def get_session() -> Session:
    return get_db().get_session()


@asynccontextmanager
async def get_async_session():
    db = get_db()
    async with db.async_session() as sess:
        yield sess
