"""FastMCP server for fd-scraw-harness - datasource discovery pipeline (async).

Exposes the full harness workflow as MCP tools: discover_sources, analyze_page,
generate_manifest, list_candidates, approve/reject_manifest, export_manifest,
coverage_report, test_spider, and harness_status.

Entry: uv run --directory fd-scraw-harness python -m fd_scraw_harness.server
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

# Try to load .env file for LINJIE_API_KEY and other settings
try:
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parents[2]  # repo root
    load_dotenv(_ROOT / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
except ImportError:
    pass

from sqlalchemy import select
from fastmcp import FastMCP

from fd_scraw_harness import __version__
from fd_scraw_harness.db import get_async_session, get_db, async_init_db
from fd_scraw_harness.models import Analysis, Candidate, Discovery, Manifest

logger = logging.getLogger("fd-scraw-harness")
app = FastMCP(name="fd-scraw-harness")

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


@app.tool
@timeout_guard("harness_status")
async def harness_status() -> dict:
    """Report server capabilities and configuration status.

    Returns information about LLM availability, ego-browser detection,
    database connection, and current mode (direct_llm vs disabled).
    """
    await async_init_db()
    db = get_db()

    has_api_key = bool(os.environ.get("LINJIE_API_KEY"))
    models_available = ["gm51model", "qmodel_latest"] if has_api_key else []
    ego_available = await _check_ego_browser()
    anon_url = _anonymize_db_url(db.database_url)

    return {
        "mode": "direct_llm" if has_api_key else "disabled",
        "models_available": models_available,
        "ego_browser_available": ego_available,
        "database_url": anon_url,
        "harness_version": __version__,
    }


# ───────────────────────── Discovery Tools ────────────────────────────


@app.tool
@timeout_guard("discover_sources")
async def discover_sources(keyword: Optional[str] = None, url: Optional[str] = None) -> dict:
    """Discover candidate data sources from a keyword or direct URL.

    Uses LLM-powered web search via Linjie AI to find relevant data sources.
    If URL provided, skips LLM search and directly analyzes that page.

    Args:
        keyword: Search keyword/topic (e.g. "半导体行业数据源")
        url: Direct URL to analyze (skips LLM web search)

    Returns:
        DiscoverySummary with discovery_id, candidates_count, and candidate list
    """
    await async_init_db()

    if not keyword and not url:
        return {"error": "provide keyword or url"}

    try:
        from fd_scraw_harness.discovery import discover as run_discover

        discovery_id = await run_discover(keyword=keyword, url=url)

        async with get_async_session() as sess:
            c_result = await sess.execute(
                select(Candidate).filter_by(discovery_id=discovery_id)
            )
            candidates = c_result.scalars().all()

            candidates_summary = [
                {
                    "id": c.id,
                    "url": c.url,
                    "title": c.title or "Untitled",
                    "description": (c.description or "")[:200],
                    "estimated_data_type": c.estimated_data_type,
                    "score": c.score,
                    "coverage_status": c.coverage_status,
                    "adjusted_score": c.adjusted_score or c.score,
                }
                for c in candidates
            ]

        async with get_async_session() as sess:
            d_result = await sess.execute(
                select(Discovery).filter_by(id=discovery_id)
            )
            d = d_result.scalar_one_or_none()

        return {
            "discovery_id": discovery_id,
            "query": d.query,
            "query_type": d.query_type,
            "status": d.status,
            "candidates_count": len(candidates),
            "candidates": candidates_summary,
            "created_at": d.created_at.isoformat(),
        }

    except Exception as e:
        logger.exception("Discovery failed")
        return {"error": f"Discovery failed: {type(e).__name__}: {str(e)[:200]}"}


@app.tool
@timeout_guard("analyze_page")
async def analyze_page(url: str, discovery_id: int, candidate_index: Optional[int] = None) -> dict:
    """Analyze a candidate page's structure using ego-browser automation.

    Extracts DOM snapshot, table counts, form counts, API endpoints,
    and download links from the specified URL.

    Args:
        url: Candidate URL to analyze
        discovery_id: Discovery session ID containing this candidate
        candidate_index: Index of candidate from list_candidates results (optional)

    Returns:
        AnalysisSummary with analysis_id, page info, and structural findings
    """
    await async_init_db()

    if not await _check_ego_browser():
        return {"error": "ego-browser not found. Please install from https://lite.ego.app/"}

    async with get_async_session() as sess:
        query = select(Candidate).filter_by(discovery_id=discovery_id)
        if candidate_index is not None:
            result = await sess.execute(query.offset(candidate_index).limit(1))
            candidate = result.scalar_one_or_none()
            if not candidate:
                return {"error": f"Candidate index {candidate_index} out of range"}
        else:
            result = await sess.execute(query.filter_by(url=url))
            candidate = result.scalar_one_or_none()
            if not candidate:
                return {"error": "No candidate found matching URL"}

        candidate_id = candidate.id
        candidate_url = candidate.url

    try:
        from fd_scraw_harness.analyzer import analyze as run_analyze

        async with _ANALYSIS_SEM:
            analysis_id = await run_analyze(candidate_url, discovery_id)

        async with get_async_session() as sess:
            a_result = await sess.execute(
                select(Analysis).filter_by(id=analysis_id)
            )
            a = a_result.scalar_one_or_none()

            api_endpoints = []
            if a.api_endpoints:
                try:
                    api_endpoints = json.loads(a.api_endpoints)
                except json.JSONDecodeError:
                    pass

            download_links = []
            if a.download_links:
                try:
                    download_links = json.loads(a.download_links)
                except json.JSONDecodeError:
                    pass

            dom_preview = (a.dom_snapshot or "")[:1000] + "..." if a.dom_snapshot else ""

        return {
            "analysis_id": analysis_id,
            "page_url": a.page_url,
            "page_title": a.page_title or "",
            "tables_count": int(a.data_tables or 0),
            "forms_count": int(a.forms or 0),
            "api_endpoints": api_endpoints,
            "download_links": download_links,
            "dom_snapshot_preview": dom_preview,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }

    except FileNotFoundError as e:
        return {"error": f"ego-browser not found: {e}"}
    except asyncio.TimeoutError:
        return {"error": "Timeout analyzing page (max 60s). Try again."}
    except Exception as e:
        logger.exception("Page analysis failed")
        return {"error": f"Analysis failed: {type(e).__name__}: {str(e)[:200]}"}


@app.tool
@timeout_guard("generate_manifest")
async def generate_manifest(discovery_id: int) -> dict:
    """Generate a DatasourceManifest YAML from analysis data using LLM.

    Creates manifest YAML conforming to fd-open-data-protocol schema.
    Includes single retry on validation failure with error context.

    Args:
        discovery_id: Discovery session ID (must have completed analysis)

    Returns:
        ManifestSummary with manifest_id, status, source name, and model used
    """
    await async_init_db()

    try:
        from fd_scraw_harness.manifest_gen import generate as run_generate

        async with _LLM_SEM:
            manifest_id = await run_generate(discovery_id)

        async with get_async_session() as sess:
            m_result = await sess.execute(
                select(Manifest).filter_by(id=manifest_id)
            )
            m = m_result.scalar_one_or_none()

        return {
            "manifest_id": manifest_id,
            "status": m.status,
            "source_name": m.source_name or "unknown",
            "label": m.label or "Unknown Source",
            "model_used": m.model_used or "unknown",
            "validation_error": m.validation_error,
            "created_at": m.created_at.isoformat(),
        }

    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.exception("Manifest generation failed")
        return {"error": f"Generation failed: {type(e).__name__}: {str(e)[:200]}"}


# ──────────────────────── Manifest Management Tools ───────────────────


@app.tool
@timeout_guard("approve_manifest")
async def approve_manifest(manifest_id: int) -> dict:
    """Approve a draft manifest for export.

    Changes manifest status from "draft" to "approved". Only draft manifests
    can be approved.

    Args:
        manifest_id: ID of manifest to approve

    Returns:
        Success object with approved boolean
    """
    await async_init_db()

    async with get_async_session() as sess:
        result = await sess.execute(select(Manifest).filter_by(id=manifest_id))
        m = result.scalar_one_or_none()

        if not m:
            return {"error": f"Manifest {manifest_id} not found"}
        if m.status != "draft":
            return {"error": f"Manifest {manifest_id} is {m.status}, not draft"}

        m.status = "approved"
        await sess.commit()

    return {"approved": True, "manifest_id": manifest_id}


@app.tool
@timeout_guard("reject_manifest")
async def reject_manifest(manifest_id: int) -> dict:
    """Reject a draft manifest (mark without export).

    Changes manifest status from "draft" to "rejected".

    Args:
        manifest_id: ID of manifest to reject

    Returns:
        Success object with rejected boolean
    """
    await async_init_db()

    async with get_async_session() as sess:
        result = await sess.execute(select(Manifest).filter_by(id=manifest_id))
        m = result.scalar_one_or_none()

        if not m:
            return {"error": f"Manifest {manifest_id} not found"}

        m.status = "rejected"
        await sess.commit()

    return {"rejected": True, "manifest_id": manifest_id}


@app.tool
@timeout_guard("list_candidates")
async def list_candidates(discovery_id: int) -> list[dict]:
    """List all candidates for a discovery session with coverage analysis.

    Shows discovered sources with their coverage status (new/partial/covered)
    and adjusted priority scores.

    Args:
        discovery_id: Discovery session ID

    Returns:
        Array of CandidateRecord objects
    """
    await async_init_db()

    async with get_async_session() as sess:
        result = await sess.execute(
            select(Candidate)
            .filter_by(discovery_id=discovery_id)
            .order_by(Candidate.adjusted_score.desc())
        )
        candidates = result.scalars().all()

        return [
            {
                "id": c.id,
                "url": c.url,
                "title": c.title or "Untitled",
                "description": (c.description or "")[:200],
                "estimated_data_type": c.estimated_data_type or "unknown",
                "score": c.score,
                "adjusted_score": c.adjusted_score or c.score,
                "coverage_status": c.coverage_status,
                "created_at": c.created_at.isoformat(),
            }
            for c in candidates
        ]


@app.tool
@timeout_guard("list_manifests")
async def list_manifests(status: Optional[str] = None) -> list[dict]:
    """List all manifests with optional status filter.

    Shows generated manifests with their validation status and metadata.

    Args:
        status: Filter by status ("draft", "approved", "rejected")

    Returns:
        Array of ManifestRecord objects
    """
    await async_init_db()

    async with get_async_session() as sess:
        query = select(Manifest)
        if status:
            query = query.filter_by(status=status)
        query = query.order_by(Manifest.created_at.desc())

        result = await sess.execute(query)
        manifests = result.scalars().all()

        return [
            {
                "id": m.id,
                "status": m.status,
                "source_name": m.source_name or "unknown",
                "label": m.label or "Unknown Source",
                "model_used": m.model_used or "unknown",
                "validation_error": m.validation_error,
                "created_at": m.created_at.isoformat(),
            }
            for m in manifests
        ]


@app.tool
@timeout_guard("export_manifest")
async def export_manifest(manifest_id: int) -> dict:
    """Export an approved manifest, aligned to the content-repo v2 contract.

    Returns YAML (version coerced to "2", no scheduling fields), plus the
    associated spider file path/code when present in the workspace — ready
    to feed fd-industry-data scripts/land_source.py.

    Args:
        manifest_id: Manifest to export

    Returns:
        Object with yaml, size_bytes, spider_path, spider_code
    """
    await async_init_db()

    async with get_async_session() as sess:
        result = await sess.execute(select(Manifest).filter_by(id=manifest_id))
        m = result.scalar_one_or_none()

    if not m:
        return {"error": f"Manifest {manifest_id} not found"}

    if m.status != "approved":
        return {"error": f"Manifest {manifest_id} is {m.status}, not approved"}

    # Align to the content-repo v2 contract: version coerced to "2",
    # scheduling fields stripped (landing must never light a source up).
    import yaml as _yaml

    try:
        data = _yaml.safe_load(m.manifest_yaml or "") or {}
    except _yaml.YAMLError:
        data = {}
    if isinstance(data, dict):
        data["version"] = "2"
        for sched in ("schedule", "memory_limit", "cpu_limit", "enabled"):
            data.pop(sched, None)
        yaml_text = _yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    else:
        yaml_text = m.manifest_yaml or ""
    size_bytes = len(yaml_text.encode("utf-8"))

    # Associated spider file follows the spider_tester path convention.
    source_name = m.source_name or f"manifest_{manifest_id}"
    spider_path = None
    for cand in (f"fd-industry-data/spiders/{source_name}/spider.py",
                 f"fd-industry-data/spiders/{source_name.replace('-', '_')}/spider.py"):
        if Path(cand).exists():
            spider_path = cand
            break
    spider_code = Path(spider_path).read_text() if spider_path else None

    return {"yaml": yaml_text, "size_bytes": size_bytes,
            "spider_path": spider_path, "spider_code": spider_code}


# ───────────────────── Coverage and Testing Tools ─────────────────────


@app.tool
@timeout_guard("coverage_report")
async def coverage_report() -> dict:
    """Generate full coverage analysis report for all candidates.

    Analyzes all discovered sources against existing datasources
    in fd-open-data-mcp catalog and fd-industry-data spiders.

    Returns:
        CoverageReport with breakdown by status (new/partial/covered)
    """
    await async_init_db()

    try:
        from fd_scraw_harness.coverage import analyze_all_candidates

        results = await analyze_all_candidates()

        return {
            "total_candidates": results["total"],
            "covered": results["covered"],
            "partial": results["partial"],
            "new": results["new"],
            "candidates": results["candidates"],
        }

    except Exception as e:
        logger.exception("Coverage analysis failed")
        return {"error": f"Coverage analysis failed: {type(e).__name__}: {str(e)[:200]}"}


@app.tool
@timeout_guard("test_spider")
async def test_spider(
    manifest_id_or_path,
    test_type: str = "full",
    verbose: bool = False,
) -> dict:
    """Test a spider implementation for syntax errors and mock execution.

    Accepts either a manifest_id (integer) or file path (string).
    Runs validation checks and mock data fetching.

    Args:
        manifest_id_or_path: Manifest ID (int) or spider file path (string)
        test_type: Type of test ("full", "syntax_only", "mock_execution")
        verbose: Enable verbose output

    Returns:
        TestReport with status, failures, warnings, and metrics
    """
    await async_init_db()

    try:
        from fd_scraw_harness.spider_tester import test_single_spider_async

        try:
            manifest_id_int = int(manifest_id_or_path)
        except (ValueError, TypeError):
            manifest_id_int = manifest_id_or_path

        async with _SPIDER_SEM:
            report = await test_single_spider_async(
                manifest_id_int,
                test_type=test_type,
                store_results=True,
            )

        return {
            "test_id": report.get("test_id"),
            "manifest_id": report.get("manifest_id"),
            "spider_path": report.get("spider_path"),
            "test_type": report.get("test_type"),
            "status": report.get("status"),
            "is_valid": report.get("is_valid"),
            "execution_success": report.get("execution_success"),
            "records_fetched": report.get("records_fetched"),
            "failure_reasons": report.get("failure_reasons", []),
            "warning_messages": report.get("warning_messages", []),
            "execution_time_seconds": report.get("execution_time_seconds"),
            "error_message": report.get("error_message"),
            "created_at": report.get("created_at"),
        }

    except Exception as e:
        logger.exception("Spider test failed")
        return {"error": f"Test failed: {type(e).__name__}: {str(e)[:200]}"}


@app.tool
@timeout_guard("test_all_spiders")
async def test_all_spiders(limit: Optional[int] = None, parallel: int = 1) -> dict:
    """Run tests on all manifests in the database.

    Supports limiting count and parallel workers. Returns summary
    with pass rate and individual results.

    Args:
        limit: Maximum number of spiders to test (None = all)
        parallel: Number of concurrent workers (default 1)

    Returns:
        TestSummary with total, passed, failed, errors, pass_rate, and results
    """
    await async_init_db()

    try:
        from fd_scraw_harness.spider_tester import test_all_spiders_async

        summary = await test_all_spiders_async(limit=limit, parallel=parallel)

        pass_rate = summary.get("pass_rate", 0.0)
        if isinstance(pass_rate, float):
            pass_rate = round(pass_rate, 4)
        elif isinstance(pass_rate, (int, type(None))):
            pass_rate = float(pass_rate or 0) / max(summary.get("total", 1), 1)

        return {
            "total": summary.get("total", 0),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "errors": summary.get("errors", 0),
            "pass_rate": pass_rate,
            "results": summary.get("results", []),
        }

    except Exception as e:
        logger.exception("Batch test failed")
        return {"error": f"Batch test failed: {type(e).__name__}: {str(e)[:200]}"}


if __name__ == "__main__":
    # Run with: uv run --directory fd-scraw-harness python -m fd_scraw_harness.server
    app.run()
