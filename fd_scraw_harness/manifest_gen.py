"""Manifest generator: uses LiteLLM to produce DatasourceManifest YAML from analysis."""
from __future__ import annotations

import logging

from sqlalchemy import select

from fd_scraw_harness.db import get_async_session
from fd_scraw_harness.llm import call_llm
from fd_scraw_harness.models import Analysis, Discovery, Manifest

logger = logging.getLogger(__name__)

_GENERATION_PROMPT = """You are a data source manifest generator. Given page analysis data, generate a DatasourceManifest YAML.

The YAML must conform to this schema:
```yaml
version: "2"
name: <source-name>
label: <human-readable label>
source_url: <url>
ranking_seed: [0.5, 0.5]
functions:
  - command: <function_name>
    category: <macro|stocks|reference|news|fund|bond|crypto>
    description: <what this function fetches>
    parameters:
      - name: <param_name>
        type: <str|int|float>
        required: true|false
        description: <what this param does>
    columns:
      - name: <column_name>
        type: <str|float|int|datetime>
        description: <what this column contains>
    frequency: <daily|weekly|monthly|quarterly|annual|realtime>
concepts:
  - column: <column_name>
    concept: <concept_name>
    entity_type: <stock|country|city|industry>
fetch:
  runner: <source-name>
```

Analysis data:
{analysis_data}

Generate ONLY the YAML. No markdown, no explanation."""


async def generate(discovery_id: int, max_retries: int = 1) -> int:
    async with get_async_session() as sess:
        d_result = await sess.execute(
            select(Discovery).filter_by(id=discovery_id)
        )
        discovery = d_result.scalar_one_or_none()
        if not discovery:
            raise ValueError(f"Discovery {discovery_id} not found")

        a_result = await sess.execute(
            select(Analysis).filter_by(discovery_id=discovery_id, status="completed")
        )
        analyses = a_result.scalars().all()
        if not analyses:
            raise ValueError(f"No completed analyses for discovery {discovery_id}")

        analysis = analyses[0]
        analysis_data = {
            "url": analysis.page_url,
            "title": analysis.page_title,
            "snapshot_preview": (analysis.dom_snapshot or "")[:2000],
            "api_endpoints": analysis.api_endpoints,
            "data_tables": analysis.data_tables,
            "download_links": analysis.download_links,
            "forms": analysis.forms,
        }

    manifest_yaml = None
    validation_error = None
    model_used = None
    raw = ""

    for attempt in range(max_retries + 1):
        prompt = _GENERATION_PROMPT.format(analysis_data=analysis_data)
        model_used = _get_model()

        try:
            raw = await call_llm(prompt, phase="generation")
            yaml_text = _extract_yaml(raw)
            _validate_yaml(yaml_text)
            manifest_yaml = yaml_text
            break
        except Exception as e:
            validation_error = str(e)
            logger.warning("Manifest generation attempt %d failed: %s", attempt + 1, e)
            if attempt < max_retries:
                prompt = f"Previous attempt failed validation: {e}\n\nPlease fix and regenerate.\n\n" + prompt

    status = "draft" if manifest_yaml else "invalid"

    async with get_async_session() as sess:
        manifest = Manifest(
            discovery_id=discovery_id,
            analysis_id=analysis.id,
            manifest_yaml=manifest_yaml or raw or "",
            model_used=model_used,
            status=status,
            validation_error=validation_error,
        )
        sess.add(manifest)
        await sess.commit()
        await sess.refresh(manifest)
        manifest_id = manifest.id

    logger.info("Manifest %d generated for discovery %d: status=%s", manifest_id, discovery_id, status)
    return manifest_id


def _get_model() -> str:
    from fd_scraw_harness.llm import get_llm_model
    return get_llm_model("generation")


def _extract_yaml(raw: str) -> str:
    if "```yaml" in raw:
        start = raw.index("```yaml") + 7
        end = raw.index("```", start)
        return raw[start:end].strip()
    if "```" in raw:
        start = raw.index("```") + 3
        end = raw.index("```", start)
        return raw[start:end].strip()
    return raw.strip()


def _validate_yaml(yaml_text: str) -> None:
    import yaml
    from fd_open_data_protocol.loader import load_catalog

    data = yaml.safe_load(yaml_text)
    if not isinstance(data, dict):
        raise ValueError("YAML did not parse to a dict")
    load_catalog(data)
