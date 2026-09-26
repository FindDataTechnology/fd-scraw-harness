"""Discovery tools for fd-scraw-harness."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from fd_scraw_harness import __version__
from fd_scraw_harness.db import async_init_db, get_async_session, get_db
from fd_scraw_harness.models import Analysis, Candidate, Discovery, Manifest

from .common import (
    _ANALYSIS_SEM,
    _LLM_SEM,
    _SPIDER_SEM,
    _anonymize_db_url,
    _check_ego_browser,
    logger,
    timeout_guard,
)


def register(app):
    """Register discovery tools tools on the FastMCP app."""

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
