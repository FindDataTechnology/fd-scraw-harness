"""Manifest generation and management tools for fd-scraw-harness."""
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
    """Register manifest generation and management tools tools on the FastMCP app."""

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
