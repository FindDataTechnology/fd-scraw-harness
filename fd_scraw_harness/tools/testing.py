"""Spider testing tools for fd-scraw-harness."""
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
    """Register spider testing tools tools on the FastMCP app."""

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
