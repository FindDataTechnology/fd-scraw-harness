"""Discovery module: keyword search via LLM or direct URL."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from fd_scraw_harness.db import get_session
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


def discover(keyword: str | None = None, url: str | None = None) -> int:
    if keyword:
        return _discover_keyword(keyword)
    if url:
        return _discover_url(url)
    raise ValueError("Provide keyword or url")


def _discover_keyword(keyword: str) -> int:
    with get_session() as sess:
        discovery = Discovery(query=keyword, query_type="keyword", status="discovering")
        sess.add(discovery)
        sess.commit()
        sess.refresh(discovery)
        discovery_id = discovery.id

    prompt = _DISCOVERY_PROMPT.format(keyword=keyword)
    raw = call_llm(prompt, phase="discovery")

    try:
        candidates = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            candidates = json.loads(raw[start:end])
        else:
            raise ValueError(f"LLM did not return valid JSON: {raw[:200]}")

    with get_session() as sess:
        for c in candidates:
            candidate = Candidate(
                discovery_id=discovery_id,
                url=c.get("url", ""),
                title=c.get("title"),
                description=c.get("description"),
                estimated_data_type=c.get("estimated_data_type"),
                score=c.get("score", 0),
            )
            sess.add(candidate)

        d = sess.query(Discovery).filter_by(id=discovery_id).first()
        d.status = "discovered"
        sess.commit()

    logger.info("Discovery %d: found %d candidates for %r", discovery_id, len(candidates), keyword)
    return discovery_id


def _discover_url(url: str) -> int:
    with get_session() as sess:
        discovery = Discovery(query=url, query_type="url", status="discovered")
        sess.add(discovery)
        sess.commit()
        sess.refresh(discovery)
        discovery_id = discovery.id

        candidate = Candidate(discovery_id=discovery_id, url=url, title=url, score=100)
        sess.add(candidate)
        sess.commit()

    return discovery_id
