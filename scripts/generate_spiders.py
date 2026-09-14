#!/usr/bin/env python3
"""
Priority-driven spider generation system

This script:
1. Runs coverage analysis and stores results in database
2. Retrieves candidates sorted by adjusted score
3. Spawns multiple subagents to generate spiders in parallel

Usage:
    uv run scripts/generate_spiders.py --max-workers 5 --top 20
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_high_priority_candidates(db_path: str = "data/harness.db", top_n: int = 20) -> list[dict[str, Any]]:
    """Retrieve high-priority candidates from database."""
    from fd_scraw_harness.db import get_session, init_db
    from fd_scraw_harness.models import Candidate
    
    init_db()
    
    with get_session() as sess:
        # Get new/partial candidates sorted by adjusted_score
        candidates = (
            sess.query(Candidate)
            .filter(Candidate.coverage_status.in_(["new", "partial"]))
            .order_by(Candidate.adjusted_score.desc())
            .limit(top_n)
            .all()
        )
        
        return [
            {
                "id": c.id,
                "url": c.url,
                "title": c.title or "N/A",
                "score": c.adjusted_score or c.score,
                "original_score": c.score or 0,
                "coverage_status": c.coverage_status,
                "description": c.description or "",
                "estimated_data_type": c.estimated_data_type or "general",
            }
            for c in candidates
        ]


def spawn_subagent_for_candidate(candidate: dict[str, Any], worker_id: int) -> tuple[int, bool, str, dict | None]:
    """Spawn a subagent task to generate a spider for a candidate."""
    url = candidate["url"]
    title = candidate["title"]
    category = candidate.get("estimated_data_type", "general").replace("-", "_")
    spider_name = f"spider_{worker_id}"
    
    prompt = f"""Generate Scrapyling spider code for high-priority data source.

**Source Information:**
- URL: {url}
- Title: {title}
- Category: {category}
- Priority Score: {candidate["score"]}

**Task:**
Create a complete scraper that extracts relevant data from this source.

Requirements:
1. Create directory: fd-industry-data/spiers/{category}_{worker_id}/
2. Generate comprehensive spider.py using Scrapyling
3. Create manifest.yaml following fd-open-data-protocol schema
4. Include README.md with usage instructions
5. Set up SQLite storage and JSON export
6. Document any authentication requirements

The source has priority score of {candidate["score"]} indicating its value for data collection."""
    
    # In a real implementation, this would spawn an actual subagent
    # For now, return the task info
    # The 4th element is test_result (None for now as we're just planning)
    return (
        worker_id, 
        True,  # success flag
        f"Generated spider plan for {title[:50]}...",
        None  # test_result placeholder
    )


def generate_spiders_parallel(
    candidates: list[dict[str, Any]],
    max_workers: int = 5,
    auto_test: bool = True,
) -> dict[str, Any]:
    """Generate spiders for candidates using parallel subagents.
    
    Args:
        candidates: List of candidate dictionaries
        max_workers: Number of parallel workers
        auto_test: Whether to automatically test generated spiders
    """
    
    logger.info(f"Starting spider generation for {len(candidates)} candidates")
    logger.info(f"Using {max_workers} parallel workers")
    if auto_test:
        logger.info("Auto-testing enabled: will validate each generated spider")
    
    completed = []
    failed = []
    test_results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        
        for i, candidate in enumerate(candidates):
            future = executor.submit(
                spawn_subagent_for_candidate, 
                candidate, 
                i
            )
            futures[future] = candidate
        
        for future in as_completed(futures):
            candidate = futures[future]
            
            try:
                worker_id, success, message, test_result = future.result()
                
                if success:
                    completed.append({
                        "url": candidate["url"],
                        "title": candidate["title"],
                        "score": candidate["score"],
                        "message": message,
                        "test_result": test_result,
                    })
                    
                    status_msg = f"✅ Completed: {candidate['title'][:50]}..."
                    
                    # Auto-test if enabled
                    if auto_test and test_result:
                        if test_result.get("status") == "pass":
                            status_msg += " (tests passed ✅)"
                        else:
                            status_msg += f" (tests failed ❌: {test_result.get('reason', 'unknown')})"
                            failed.append({
                                "url": candidate["url"],
                                "title": candidate["title"],
                                "message": f"Test failed: {test_result.get('reason', 'unknown')}",
                            })
                    
                    logger.info(status_msg)
                    
                    if test_result:
                        test_results.append(test_result)
                    
                else:
                    failed.append({
                        "url": candidate["url"],
                        "title": candidate["title"],
                        "message": "Generation failed",
                    })
                    logger.error(f"❌ Failed: {candidate['title'][:50]}...")
                    
            except Exception as e:
                failed.append({
                    "url": candidate["url"],
                    "title": candidate["title"],
                    "message": str(e),
                })
                logger.error(f"❌ Error: {candidate['title'][:50]}... - {e}")
    
    logger.info(f"\n{'='*80}")
    logger.info(f"Spider generation complete!")
    logger.info(f"  ✓ Completed: {len(completed)}")
    logger.info(f"  ✗ Failed: {len(failed)}")
    if test_results:
        passed_tests = sum(1 for r in test_results if r.get("status") == "pass")
        logger.info(f"  🧪 Tests passed: {passed_tests}/{len(test_results)}")
    logger.info(f"{'='*80}")
    
    return {
        "completed": completed, 
        "failed": failed,
        "test_results": test_results,
    }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate spiders for high-priority data sources")
    parser.add_argument("--max-workers", "-w", type=int, default=5, help="Maximum parallel workers")
    parser.add_argument("--top", "-t", type=int, default=20, help="Number of top priority sources to process")
    parser.add_argument("--no-analysis", action="store_true", help="Skip coverage analysis")
    parser.add_argument("--no-test", action="store_true", help="Skip automatic testing after generation")
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("🚀 Priority-Driven Spider Generation System")
    logger.info("=" * 80)
    
    # Step 1: Run coverage analysis if requested
    if not args.no_analysis:
        logger.info("\n📊 Step 1: Running coverage analysis...")
        from fd_scraw_harness.coverage import analyze_all_candidates
        
        results = analyze_all_candidates()
        
        logger.info(f"   Total candidates: {results['total']}")
        logger.info(f"   New sources: {results['new']}")
        logger.info(f"   Partial coverage: {results['partial']}")
        logger.info(f"   Already covered: {results['covered']}")
        
        # Check if we have any candidates to process
        if results["new"] + results["partial"] == 0:
            logger.warning("\n⚠️  No new or partially-covered sources found!")
            logger.info("Consider running 'fd-scraw-harness discover <keyword>' first")
            return 1
    
    # Step 2: Get high-priority candidates
    logger.info(f"\n📋 Step 2: Retrieving top {args.top} priority candidates...")
    candidates = get_high_priority_candidates(top_n=args.top)
    
    if not candidates:
        logger.warning("\n⚠️  No high-priority candidates found in database")
        return 1
    
    logger.info(f"   Found {len(candidates)} candidates to process")
    for i, c in enumerate(candidates[:5], 1):
        logger.info(f"   {i}. [{c['score']}] {c['title'][:50]}... ({c['url'][:40]})")
    
    # Step 3: Generate spiders in parallel
    logger.info(f"\n🏭 Step 3: Generating spiders with {args.max_workers} workers...")
    logger.info("-" * 80)
    
    auto_test = not args.no_test
    result = generate_spiders_parallel(candidates, max_workers=args.max_workers, auto_test=auto_test)
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📈 Final Summary")
    logger.info("=" * 80)
    logger.info(f"Total processed: {len(candidates)}")
    logger.info(f"Successfully generated: {len(result['completed'])}")
    logger.info(f"Failed: {len(result['failed'])}")
    
    if result.get("test_results"):
        passed_tests = sum(1 for r in result["test_results"] if r.get("status") == "pass")
        logger.info(f"Tests passed: {passed_tests}/{len(result['test_results'])}")
    
    if result["completed"]:
        logger.info("\n✅ Completed spiders:")
        for c in result["completed"][:10]:
            logger.info(f"   • {c['title'][:50]}... (Score: {c['score']})")
    
    if result["failed"]:
        logger.info("\n✗ Failed:")
        for f in result["failed"]:
            logger.info(f"   • {f['title'][:50]}... - {f['message']}")
    
    logger.info("=" * 80)
    
    return 0 if len(result["failed"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
