"""Async discovery module: keyword search via LLM or direct URL."""
from __future__ import annotations

import json
import logging

from sqlalchemy import select

from fd_scraw_harness.db import get_async_session
from fd_scraw_harness.llm import call_llm
from fd_scraw_harness.models import Candidate, Discovery

logger = logging.getLogger(__name__)

_DISCOVERY_PROMPT = """You are a data source discovery assistant. Given a keyword or topic, find candidate data sources on the web.

Return a JSON array of objects with these fields:
- url: the URL of the data source
- title: a short title
- description: what data is available
- estimated_data_type: e.g. "macro-economic", "stock-market", "government-statistics", "financial-report"
- score: 0-100 relevance score

Topic: {keyword}

Return ONLY valid JSON. No markdown, no explanation."""


async def discover(keyword: str | None = None, url: str | None = None) -> int:
    if keyword:
        return await _discover_keyword(keyword)
    if url:
        return await _discover_url(url)
    raise ValueError("Provide keyword or url")


async def _discover_keyword(keyword: str) -> int:
    async with get_async_session() as sess:
        discovery = Discovery(query=keyword, query_type="keyword", status="discovering")
        sess.add(discovery)
        await sess.flush()
        await sess.refresh(discovery)
        discovery_id = discovery.id

    prompt = _DISCOVERY_PROMPT.format(keyword=keyword)
    raw = await call_llm(prompt, phase="discovery")

    try:
        candidates = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            candidates = json.loads(raw[start:end])
        else:
            raise ValueError(f"LLM did not return valid JSON: {raw[:200]}")

    async with get_async_session() as sess:
        for c in candidates:
            sess.add(Candidate(
                discovery_id=discovery_id,
                url=c.get("url", ""),
                title=c.get("title"),
                description=c.get("description"),
                estimated_data_type=c.get("estimated_data_type"),
                score=c.get("score", 0),
            ))

        result = await sess.execute(select(Discovery).filter_by(id=discovery_id))
        d = result.scalar_one()
        d.status = "discovered"
        await sess.commit()

    logger.info("Discovery %d: found %d candidates for %r", discovery_id, len(candidates), keyword)
    return discovery_id


async def _discover_url(url: str) -> int:
    async with get_async_session() as sess:
        discovery = Discovery(query=url, query_type="url", status="discovered")
        sess.add(discovery)
        await sess.flush()
        await sess.refresh(discovery)
        discovery_id = discovery.id

        sess.add(Candidate(discovery_id=discovery_id, url=url, title=url, score=100))
        await sess.commit()

    return discovery_id
