"""Shared tool infrastructure: concurrency guards, timeouts, helpers."""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
from typing import Awaitable, Callable

logger = logging.getLogger("fd-scraw-harness")

# ───────────────────────── Concurrency Guards ─────────────────────────

# ponytail: global semaphores, per-resource limits. Raise limits if throughput matters.
_LLM_SEM = asyncio.Semaphore(int(os.environ.get("HARNESS_LLM_CONCURRENCY", "5")))
_SPIDER_SEM = asyncio.Semaphore(int(os.environ.get("HARNESS_SPIDER_CONCURRENCY", "3")))
_ANALYSIS_SEM = asyncio.Semaphore(int(os.environ.get("HARNESS_ANALYSIS_CONCURRENCY", "2")))

# ───────────────────────── Timeout Guard ──────────────────────────────

_DEFAULT_TIMEOUTS: dict[str, float] = {
    "analyze_page": 60.0,
    "test_spider": 300.0,
    "discover_sources": 120.0,
    "generate_manifest": 180.0,
    "coverage_report": 120.0,
    "test_all_spiders": 600.0,
}
_FALLBACK_TIMEOUT = 30.0


def _tool_timeout(name: str) -> float:
    env_key = f"HARNESS_TOOL_TIMEOUT_{name.upper()}"
    env_val = os.environ.get(env_key)
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    return _DEFAULT_TIMEOUTS.get(name, _FALLBACK_TIMEOUT)


def timeout_guard(tool_name: str):
    """Decorator: wraps an async tool handler with asyncio.wait_for + structured error."""
    def decorator(fn: Callable[..., Awaitable]):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            limit = _tool_timeout(tool_name)
            t0 = time.monotonic()
            try:
                return await asyncio.wait_for(fn(*args, **kwargs), timeout=limit)
            except asyncio.TimeoutError:
                elapsed = round(time.monotonic() - t0, 2)
                logger.warning("Tool %s timed out after %.1fs (limit=%.1fs)", tool_name, elapsed, limit)
                return {
                    "error": "timeout",
                    "tool": tool_name,
                    "elapsed_seconds": elapsed,
                    "limit_seconds": limit,
                }
        return wrapper
    return decorator


# ───────────────────────── Helpers ────────────────────────────────────


async def _check_ego_browser() -> bool:
    """Check if ego-browser is installed and available."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ego-browser", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            return False
        return proc.returncode == 0
    except FileNotFoundError:
        return False


def _anonymize_db_url(url: str) -> str:
    """Anonymize database URL by masking credentials."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return f"{scheme}://{rest}"
    creds_and_host, _, path = rest.partition("/")
    if ":" in creds_and_host:
        user_part, host_part = creds_and_host.split("@", 1) if "@" in creds_and_host else ("***", creds_and_host)
        if ":" in user_part:
            user, _ = user_part.split(":", 1)
            creds_and_host = f"{user}:***@{host_part}"
        else:
            creds_and_host = f"{'***'}:{'***'}@{host_part}"
    return f"{scheme}://{creds_and_host}/{path}"


# ───────────────────────── Utility Tools ──────────────────────────────

