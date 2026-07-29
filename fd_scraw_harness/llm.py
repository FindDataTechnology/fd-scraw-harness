"""LiteLLM integration with response caching."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from fd_scraw_harness.models import LLMCache

logger = logging.getLogger(__name__)


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def _cache_get(sess: Session, prompt_hash: str, model: str) -> Optional[str]:
    row = sess.query(LLMCache).filter_by(prompt_hash=prompt_hash, model_name=model).first()
    return row.response if row else None


def _cache_set(sess: Session, prompt_hash: str, model: str, prompt: str, response: str) -> None:
    entry = LLMCache(prompt_hash=prompt_hash, model_name=model, prompt=prompt, response=response)
    sess.add(entry)
    sess.commit()


def get_llm_model(phase: Optional[str] = None) -> str:
    if phase == "discovery":
        return os.environ.get("HARNESS_MODEL_DISCOVERY") or os.environ.get("HARNESS_LITELLM_MODEL") or "deepseek-chat"
    if phase == "generation":
        return os.environ.get("HARNESS_MODEL_GENERATION") or os.environ.get("HARNESS_LITELLM_MODEL") or "deepseek-chat"
    return os.environ.get("HARNESS_LITELLM_MODEL") or "deepseek-chat"


def call_llm(prompt: str, model: Optional[str] = None, phase: Optional[str] = None, use_cache: bool = True) -> str:
    model = model or get_llm_model(phase)
    prompt_hash = _hash_prompt(prompt)

    if use_cache:
        from fd_scraw_harness.db import get_session
        with get_session() as sess:
            cached = _cache_get(sess, prompt_hash, model)
            if cached is not None:
                logger.info("LLM cache hit for model=%s", model)
                return cached

    logger.info("Calling LLM: model=%s", model)
    from litellm import completion
    response = completion(model=model, messages=[{"role": "user", "content": prompt}])
    text = response["choices"][0]["message"]["content"]

    if use_cache:
        from fd_scraw_harness.db import get_session
        with get_session() as sess:
            _cache_set(sess, prompt_hash, model, prompt, text)

    return text
