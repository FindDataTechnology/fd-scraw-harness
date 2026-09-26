"""Coverage analysis module for fd-scraw-harness.

Analyzes whether candidate data sources are already covered by existing
data sources in fd-open-data-mcp or fd-industry-data spiders.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 数据源类型关键词映射
CATEGORY_KEYWORDS = {
    "government": ["gov.cn", "stats.gov", "统计局", "政府", "mof.gov", "nhc.gov"],
    "financial": ["wind.com", "eastmoney", "ifind", "金融", "证券", "银行"],
    "commodity": ["futures", "exchange", "交易所", "期货", "商品"],
    "industry": ["association", "协会", "industry", "行业"],
    "media": ["news", "media", "日报", "新闻"],
    "academic": ["cnki", "wanfang", "学术", "研究"],
    "social": ["wechat", "weibo", "社交", "微博"],
}


def get_fd_open_data_mcp_sources() -> list[dict[str, Any]]:
    """Get registered sources for overlap analysis (optional, read-only).

    Path comes from FD_SOURCES_DB (a daas.db / catalog sqlite); the old
    hardcoded dual-DB location is gone. Missing db = empty list, coverage
    still works with keyword-only overlap."""
    import os

    env_path = os.environ.get("FD_SOURCES_DB", "")
    if not env_path:
        return []
    mcp_db_path = Path(env_path)
    
    if not mcp_db_path.exists():
        logger.warning(f"fd-open-data-mcp database not found at {mcp_db_path}")
        return []
    
    conn = sqlite3.connect(str(mcp_db_path))
    conn.row_factory = sqlite3.Row
    
    try:
        cur = conn.cursor()
        
        # 获取所有数据源
        cur.execute("SELECT id, name, label, url, description FROM sources")
        sources = []
        
        for row in cur.fetchall():
            source_id = row["id"]
            
            # 获取该源关联的 concepts (字段)
            cur.execute("""
                SELECT DISTINCT code, name_en, name_zh 
                FROM concepts 
                WHERE source = ?
            """, (row["name"],))
            
            concepts = cur.fetchall()
            fields = [c["code"] for c in concepts]
            
            sources.append({
                "id": source_id,
                "name": row["name"],
                "label": row["label"],
                "url": row["url"],
                "description": row["description"],
                "functions": [],  # fd-open-data-mcp 不使用 functions 表
                "fields": fields,
            })
        
        return sources
    finally:
        conn.close()


def get_fd_industry_data_spiders() -> list[dict[str, Any]]:
    """Get all spider definitions from fd-industry-data."""
    spiders_dir = Path("/Users/chengsishi/finddata/fd-industry-data/spiers")
    
    if not spiders_dir.exists():
        logger.warning(f"fd-industry-data spiders directory not found at {spiders_dir}")
        return []
    
    spiders = []
    for spider_dir in spiders_dir.iterdir():
        if not spider_dir.is_dir():
            continue
        
        manifest_path = spider_dir / "manifest.yaml"
        readme_path = spider_dir / "README.md"
        
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = yaml.safe_load(f)
                
                spiders.append({
                    "name": spider_dir.name,
                    "manifest": manifest,
                    "source_url": manifest.get("source_url", ""),
                    "category": manifest.get("category", ""),
                    "fields": [col["name"] for col in manifest.get("columns", [])],
                    "functions": [func["command"] for func in manifest.get("functions", [])],
                })
            except Exception as e:
                logger.error(f"Failed to parse manifest for {spider_dir.name}: {e}")
    
    return spiders


def detect_category(url: str, title: str = "", description: str = "") -> str:
    """Detect the category of a data source based on URL and metadata."""
    text = f"{url} {title} {description}".lower()
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    
    return "other"


def check_url_coverage(url: str, existing_sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Check if a URL is already covered by existing sources."""
    url_lower = url.lower().rstrip("/")
    
    # Check fd-open-data-mcp sources
    for source in existing_sources:
        if source.get("url"):
            existing_url = source["url"].lower().rstrip("/")
            if url_lower == existing_url or url_lower.startswith(existing_url):
                return {
                    "covered": True,
                    "source": "fd-open-data-mcp",
                    "source_name": source.get("name"),
                    "overlap_reason": "exact_url_match",
                }
    
    return {"covered": False}


def check_field_coverage(
    candidate_fields: list[str],
    existing_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check how many fields are already covered by existing sources."""
    if not candidate_fields:
        return {"coverage": 0.0, "overlapping_fields": [], "sources": []}
    
    candidate_set = set(candidate_fields)
    all_existing_fields = set()
    overlapping_sources = []
    
    for source in existing_sources:
        source_fields = set(source.get("fields", []))
        all_existing_fields.update(source_fields)
        
        overlap = candidate_set & source_fields
        if overlap:
            overlapping_sources.append({
                "source": source.get("name"),
                "overlapping_fields": list(overlap),
            })
    
    overlap_count = len(candidate_set & all_existing_fields)
    coverage = overlap_count / len(candidate_set) if candidate_set else 0.0
    
    return {
        "coverage": coverage,
        "overlapping_fields": list(candidate_set & all_existing_fields),
        "sources": overlapping_sources,
    }


def analyze_candidate_coverage(
    candidate: dict[str, Any],
    mcp_sources: list[dict[str, Any]],
    industry_spiders: list[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze coverage status for a single candidate."""
    url = candidate["url"]
    title = candidate.get("title", "")
    description = candidate.get("description", "")
    
    # Check URL coverage
    url_coverage = check_url_coverage(url, mcp_sources)
    
    # Check field coverage (if we have field info)
    candidate_fields = candidate.get("fields", [])
    field_coverage = check_field_coverage(candidate_fields, mcp_sources)
    
    # Determine overall coverage status
    if url_coverage["covered"]:
        status = "covered"
        adjusted_score = max(0, candidate["score"] - 50)  # Reduce by 50 points
        coverage_details = {
            "url_coverage": url_coverage,
            "field_coverage": field_coverage,
            "reason": f"Already covered by {url_coverage.get('source_name', 'existing source')}",
        }
    elif field_coverage["coverage"] >= 0.8:
        status = "covered"
        adjusted_score = max(0, candidate["score"] - 40)
        coverage_details = {
            "url_coverage": url_coverage,
            "field_coverage": field_coverage,
            "reason": f"Fields {field_coverage['coverage']:.0%} covered by existing sources",
        }
    elif field_coverage["coverage"] >= 0.5:
        status = "partial"
        adjusted_score = max(0, candidate["score"] - 20)
        coverage_details = {
            "url_coverage": url_coverage,
            "field_coverage": field_coverage,
            "reason": f"Fields {field_coverage['coverage']:.0%} covered, may have unique data",
        }
    else:
        status = "new"
        adjusted_score = candidate["score"]
        coverage_details = {
            "url_coverage": url_coverage,
            "field_coverage": field_coverage,
            "reason": "New data source with unique fields",
        }
    
    return {
        "status": status,
        "adjusted_score": adjusted_score,
        "details": coverage_details,
    }


async def analyze_all_candidates(db_path: str = "data/harness.db") -> dict[str, Any]:
    """Analyze coverage for all candidates in the database (async)."""
    from sqlalchemy import select
    from fd_scraw_harness.db import get_async_session, async_init_db
    from fd_scraw_harness.models import Candidate

    await async_init_db()

    # Get existing sources (sync — fast local reads)
    mcp_sources = get_fd_open_data_mcp_sources()
    industry_spiders = get_fd_industry_data_spiders()

    logger.info(f"Found {len(mcp_sources)} sources in fd-open-data-mcp")
    logger.info(f"Found {len(industry_spiders)} spiders in fd-industry-data")

    results = {
        "total": 0,
        "covered": 0,
        "partial": 0,
        "new": 0,
        "unknown": 0,
        "candidates": [],
    }

    async with get_async_session() as sess:
        c_result = await sess.execute(select(Candidate))
        candidates = c_result.scalars().all()

        for candidate in candidates:
            results["total"] += 1

            coverage = analyze_candidate_coverage(
                {
                    "url": candidate.url,
                    "title": candidate.title or "",
                    "description": candidate.description or "",
                    "score": candidate.score or 0,
                    "fields": [],
                },
                mcp_sources,
                industry_spiders,
            )

            candidate.coverage_status = coverage["status"]
            candidate.coverage_details = json.dumps(coverage["details"], ensure_ascii=False)
            candidate.adjusted_score = coverage["adjusted_score"]

            results[coverage["status"]] += 1

            results["candidates"].append({
                "id": candidate.id,
                "url": candidate.url,
                "title": candidate.title,
                "original_score": candidate.score,
                "coverage_status": coverage["status"],
                "adjusted_score": coverage["adjusted_score"],
                "reason": coverage["details"].get("reason", ""),
            })

        await sess.commit()

    return results


def print_coverage_report(results: dict[str, Any]) -> None:
    """Print a formatted coverage analysis report."""
    print("\n" + "=" * 80)
    print("📊 覆盖分析报告")
    print("=" * 80)
    
    print(f"\n总计候选数据源: {results['total']}")
    print(f"  ✅ 已覆盖 (covered): {results['covered']}")
    print(f"  ⚠️  部分覆盖 (partial): {results['partial']}")
    print(f"  🆕 新数据源 (new): {results['new']}")
    print(f"  ❓ 未知 (unknown): {results['unknown']}")
    
    print("\n" + "-" * 80)
    print("📋 详细列表 (按调整后分数排序):")
    print("-" * 80)
    
    # Sort by adjusted score descending
    sorted_candidates = sorted(
        results["candidates"],
        key=lambda x: x["adjusted_score"],
        reverse=True,
    )
    
    for i, c in enumerate(sorted_candidates[:20], 1):
        status_icon = {
            "covered": "✅",
            "partial": "⚠️ ",
            "new": "🆕",
            "unknown": "❓",
        }.get(c["coverage_status"], "❓")
        
        score_change = c["adjusted_score"] - c["original_score"]
        score_str = f"{c['adjusted_score']:3d}"
        if score_change < 0:
            score_str += f" ({score_change:+d})"
        
        print(f"\n{i}. {status_icon} [{score_str}] {c['title'] or 'N/A'}")
        print(f"   URL: {c['url']}")
        print(f"   原因: {c['reason']}")
    
    if len(sorted_candidates) > 20:
        print(f"\n... 还有 {len(sorted_candidates) - 20} 个数据源")
    
    print("\n" + "=" * 80)
    print("💡 建议:")
    print("  • 优先处理 'new' 状态的数据源（新增价值）")
    print("  • 谨慎处理 'covered' 状态的数据源（可能重复）")
    print("  • 评估 'partial' 状态的数据源（可能有独特数据）")
    print("=" * 80)
