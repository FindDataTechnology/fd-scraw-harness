"""Async LLM integration with response caching."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

import httpx
from sqlalchemy import select

from fd_scraw_harness.models import LLMCache

logger = logging.getLogger(__name__)

_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0))
    return _http_client


async def close_http() -> None:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def get_llm_model(phase: Optional[str] = None) -> str:
    if phase == "discovery":
        return os.environ.get("HARNESS_MODEL_DISCOVERY") or os.environ.get("HARNESS_LITELLM_MODEL") or "gm51model"
    if phase == "generation":
        return os.environ.get("HARNESS_MODEL_GENERATION") or os.environ.get("HARNESS_LITELLM_MODEL") or "qmodel_latest"
    return os.environ.get("HARNESS_LITELLM_MODEL") or "gm51model"


async def call_llm(
    prompt: str,
    model: Optional[str] = None,
    phase: Optional[str] = None,
    use_cache: bool = True,
) -> str:
    model_name = model or get_llm_model(phase)
    prompt_hash = _hash_prompt(prompt)

    linjie_api_key = os.environ.get("LINJIE_API_KEY", "")
    # 默认值是 OpenAI 兼容的通用入口，不是某个具体中转站——选哪家是部署决定，不是代码决定。
    linjie_base_url = os.environ.get("LINJIE_BASE_URL", "https://api.openai.com/v1")

    if not linjie_api_key:
        raise RuntimeError("Please set LINJIE_API_KEY environment variable")

    if use_cache:
        from fd_scraw_harness.db import get_async_session
        async with get_async_session() as sess:
            result = await sess.execute(
                select(LLMCache).filter_by(prompt_hash=prompt_hash, model_name=model_name)
            )
            row = result.scalar_one_or_none()
            if row is not None:
                logger.info("LLM cache hit for model=%s", model_name)
                return row.response

    logger.info("Calling LLM: model=%s", model_name)

    client = _get_http_client()
    resp = await client.post(
        f"{linjie_base_url}/chat/completions",
        json={
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        },
        headers={
            "Authorization": f"Bearer {linjie_api_key}",
            "Content-Type": "application/json",
        },
    )

    if resp.status_code != 200:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")

    data = resp.json()
    text = data["choices"][0]["message"]["content"]

    if use_cache:
        from fd_scraw_harness.db import get_async_session
        async with get_async_session() as sess:
            sess.add(LLMCache(
                prompt_hash=prompt_hash, model_name=model_name,
                prompt=prompt, response=text,
            ))
            await sess.commit()

    return text
