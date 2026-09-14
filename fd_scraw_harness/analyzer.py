"""Async page analyzer: uses ego-browser to visit URLs and extract structure."""
from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select

from fd_scraw_harness.db import get_async_session
from fd_scraw_harness.models import Analysis, Candidate

logger = logging.getLogger(__name__)

_EGO_HEREDOC = """
const task = await useOrCreateTaskSpace('harness-analyze')
cliLog('task space id: ' + task.id)

await openOrReuseTab('{url}', {{ wait: true, timeout: 20 }})

const info = await pageInfo()
cliLog(JSON.stringify({{ url: info.url, title: info.title }}))

const snapshot = await snapshotText()
cliLog('SNAPSHOT_START')
cliLog(snapshot)
cliLog('SNAPSHOT_END')

const links = await js(String.raw`(function() {{
    const tables = document.querySelectorAll('table')
    const forms = document.querySelectorAll('form')
    const apis = [...document.querySelectorAll('a[href*="api"], a[href*="json"], a[href*="csv"], a[href*="download"]')]
    return JSON.stringify({{
        tables: tables.length,
        forms: forms.length,
        api_links: apis.map(a => ({{ href: a.href, text: a.textContent.trim().slice(0, 100) }})).slice(0, 20),
        download_links: [...document.querySelectorAll('a[download], a[href$=".csv"], a[href$=".xlsx"], a[href$=".json"]')].map(a => ({{ href: a.href, text: a.textContent.trim().slice(0, 100) }})).slice(0, 20)
    }})
}})()`)
cliLog('STRUCTURE_START')
cliLog(links)
cliLog('STRUCTURE_END')

await completeTaskSpace('harness-analyze', {{ keep: false }})
"""


async def analyze(url: str, discovery_id: int) -> int:
    await _check_ego_browser()

    async with get_async_session() as sess:
        result = await sess.execute(
            select(Candidate).filter_by(discovery_id=discovery_id, url=url)
        )
        candidate = result.scalar_one_or_none()
        if not candidate:
            raise ValueError(f"No candidate found for URL {url} in discovery {discovery_id}")
        candidate_id = candidate.id

    analysis = Analysis(
        candidate_id=candidate_id,
        discovery_id=discovery_id,
        page_url=url,
        status="analyzing",
    )
    async with get_async_session() as sess:
        sess.add(analysis)
        await sess.commit()
        await sess.refresh(analysis)
        analysis_id = analysis.id

    heredoc = _EGO_HEREDOC.format(url=url)
    try:
        proc = await asyncio.create_subprocess_exec(
            "ego-browser", "nodejs",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(input=heredoc.encode()), timeout=60)
        output = stdout.decode(errors="replace")
    except FileNotFoundError:
        raise RuntimeError("ego-browser not found. Install from https://lite.ego.app/")
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"ego-browser timed out analyzing {url}")

    page_info = _extract_json_line(output)
    snapshot = _extract_between(output, "SNAPSHOT_START", "SNAPSHOT_END")
    structure_raw = _extract_between(output, "STRUCTURE_START", "STRUCTURE_END")

    structure = {}
    if structure_raw:
        try:
            structure = json.loads(structure_raw.strip())
        except json.JSONDecodeError:
            logger.warning("Could not parse structure JSON")

    async with get_async_session() as sess:
        result = await sess.execute(select(Analysis).filter_by(id=analysis_id))
        a = result.scalar_one()
        a.page_title = page_info.get("title", "") if page_info else ""
        a.dom_snapshot = snapshot or ""
        a.api_endpoints = json.dumps(structure.get("api_links", []))
        a.data_tables = str(structure.get("tables", 0))
        a.download_links = json.dumps(structure.get("download_links", []))
        a.forms = str(structure.get("forms", 0))
        a.raw_analysis = output
        a.status = "completed"
        await sess.commit()

    logger.info("Analysis %d complete for %s", analysis_id, url)
    return analysis_id


async def _check_ego_browser() -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ego-browser", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5)
    except FileNotFoundError:
        raise RuntimeError("ego-browser not found. Install from https://lite.ego.app/")


def _extract_json_line(output: str) -> dict | None:
    for line in output.strip().split("\n"):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _extract_between(output: str, start_marker: str, end_marker: str) -> str | None:
    try:
        start = output.index(start_marker) + len(start_marker)
        end = output.index(end_marker)
        return output[start:end].strip()
    except ValueError:
        return None
