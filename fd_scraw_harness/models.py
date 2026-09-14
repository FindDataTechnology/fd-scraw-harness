"""SQLAlchemy ORM models for fd-scraw-harness."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
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
    # 覆盖分析字段
    coverage_status = Column(String(32), default="unknown")  # covered, partial, new, unknown
    coverage_details = Column(Text)  # JSON: {existing_sources: [...], overlapping_fields: [...]}
    adjusted_score = Column(Integer)  # 调整后的优先级分数
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


class SpiderTest(Base):
    """Test execution results for spiders."""
    __tablename__ = "spider_tests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manifest_id = Column(Integer, ForeignKey("manifests.id"), nullable=True)
    spider_path = Column(Text)  # Path to spider.py file
    test_type = Column(String(32), nullable=False, default="full")  # full, syntax_only, mock_execution
    status = Column(String(32), nullable=False, default="pending")  # pending, running, passed, failed, error
    error_message = Column(Text)
    error_traceback = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TestResult(Base):
    """Detailed validation results for a spider test."""
    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(Integer, ForeignKey("spider_tests.id"), nullable=False)
    is_valid = Column(Integer, nullable=False, default=1)  # Boolean: 1=valid, 0=invalid
    validation_report = Column(Text)  # JSON: full validation report
    failure_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExecutionMetrics(Base):
    """Execution metrics for spider tests."""
    __tablename__ = "execution_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(Integer, ForeignKey("spider_tests.id"), nullable=False)
    execution_time_seconds = Column(Float, default=0.0)
    records_fetched = Column(Integer, default=0)
    memory_peak_mb = Column(Float, default=0.0)
    cpu_time_seconds = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
