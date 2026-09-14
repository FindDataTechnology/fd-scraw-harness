"""Tests for async MCP tool handlers."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import patch

from fd_scraw_harness.server import (
    harness_status,
    _tool_timeout,
    timeout_guard,
)


@pytest.mark.asyncio
async def test_harness_status_async():
    """Test harness_status returns expected structure."""
    result = await harness_status()

    assert isinstance(result, dict)
    assert "mode" in result
    assert "models_available" in result
    assert "ego_browser_available" in result
    assert "database_url" in result
    assert "harness_version" in result
    assert result["harness_version"] == "0.2.0"


@pytest.mark.asyncio
async def test_timeout_guard_returns_structured_error():
    """Test timeout guard returns structured error on timeout."""

    @timeout_guard("test_tool")
    async def slow_tool():
        await asyncio.sleep(10)
        return {"result": "done"}

    # Override timeout to 0.1s for test
    with patch.dict("os.environ", {"HARNESS_TOOL_TIMEOUT_TEST_TOOL": "0.1"}):
        result = await slow_tool()

    assert isinstance(result, dict)
    assert result.get("error") == "timeout"
    assert result.get("tool") == "test_tool"
    assert "elapsed_seconds" in result
    assert "limit_seconds" in result
    assert result["limit_seconds"] == 0.1


@pytest.mark.asyncio
async def test_timeout_guard_success():
    """Test timeout guard allows fast tools to complete."""

    @timeout_guard("fast_tool")
    async def fast_tool():
        await asyncio.sleep(0.01)
        return {"result": "done"}

    result = await fast_tool()
    assert result == {"result": "done"}


def test_tool_timeout_defaults():
    """Test timeout defaults are applied correctly."""
    assert _tool_timeout("analyze_page") == 60.0
    assert _tool_timeout("test_spider") == 300.0
    assert _tool_timeout("unknown_tool") == 30.0  # fallback


def test_tool_timeout_env_override():
    """Test environment variable overrides timeout."""
    import os
    os.environ["HARNESS_TOOL_TIMEOUT_CUSTOM"] = "123.4"
    try:
        assert _tool_timeout("custom") == 123.4
    finally:
        del os.environ["HARNESS_TOOL_TIMEOUT_CUSTOM"]


@pytest.mark.asyncio
async def test_async_db_session():
    """Test async session context manager works."""
    from fd_scraw_harness.db import get_async_session
    from fd_scraw_harness.models import Discovery
    from sqlalchemy import select

    # Just verify we can create a session and query
    async with get_async_session() as sess:
        result = await sess.execute(select(Discovery).limit(1))
        # Should not raise an error
        assert result is not None


@pytest.mark.asyncio
async def test_concurrent_async_operations():
    """Test multiple async DB operations can run concurrently."""
    from fd_scraw_harness.db import get_async_session
    from fd_scraw_harness.models import Discovery
    from sqlalchemy import select

    async def query_discoveries():
        async with get_async_session() as sess:
            result = await sess.execute(select(Discovery).limit(1))
            return "ok"

    # Run 5 concurrent queries
    results = await asyncio.gather(*[query_discoveries() for _ in range(5)])

    assert len(results) == 5
    assert all(r == "ok" for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
