"""SQLAlchemy ORM models for fd-scraw-harness."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Discovery(Base):
    __tablename__ = "discoveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, nullable=False)
    query_type = Column(String(16), nullable=False, default="keyword")
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    discovery_id = Column(Integer, ForeignKey("discoveries.id"), nullable=False)
    url = Column(Text, nullable=False)
    title = Column(Text)
    description = Column(Text)
    estimated_data_type = Column(String(64))
    score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    discovery_id = Column(Integer, ForeignKey("discoveries.id"), nullable=False)
    page_url = Column(Text, nullable=False)
    page_title = Column(Text)
    dom_snapshot = Column(Text)
    api_endpoints = Column(Text)
    data_tables = Column(Text)
    download_links = Column(Text)
    forms = Column(Text)
    raw_analysis = Column(Text)
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class Manifest(Base):
    __tablename__ = "manifests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    discovery_id = Column(Integer, ForeignKey("discoveries.id"), nullable=False)
    analysis_id = Column(Integer, ForeignKey("analyses.id"))
    manifest_yaml = Column(Text, nullable=False)
    source_name = Column(String(128))
    model_used = Column(String(128))
    status = Column(String(32), nullable=False, default="draft")
    validation_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LLMCache(Base):
    __tablename__ = "llm_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prompt_hash = Column(String(64), nullable=False)
    model_name = Column(String(128), nullable=False)
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("prompt_hash", "model_name", name="uq_llm_cache_hash_model"),
    )
