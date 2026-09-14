"""Additional CLI commands for fd-scraw-harness."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from .db import get_session, init_db

logger = logging.getLogger(__name__)


@click.command("generate-spiders")
@click.option("--top", "-t", default=20, help="Number of top priority sources to process")
@click.option("--workers", "-w", default=5, help="Maximum parallel workers")
@click.option("--skip-analysis", is_flag=True, help="Skip coverage analysis step")
def generate_spiders(top: int, workers: int, skip_analysis: bool) -> None:
    """Generate spiders for high-priority data sources using parallel subagents."""
    
    logger.info("=" * 80)
    logger.info("🚀 Priority-Driven Spider Generation System")
    logger.info("=" * 80)
    
    # Step 1: Run coverage analysis if requested
    if not skip_analysis:
        logger.info("\n📊 Step 1: Running coverage analysis...")
        from .coverage import analyze_all_candidates
        
        results = analyze_all_candidates()
        
        logger.info(f"   Total candidates: {results['total']}")
        logger.info(f"   New sources: {results['new']}")
        logger.info(f"   Partial coverage: {results['partial']}")
        logger.info(f"   Already covered: {results['covered']}")
        
        # Check if we have any candidates to process
        if results["new"] + results["partial"] == 0:
            logger.warning("\n⚠️  No new or partially-covered sources found!")
            logger.info("Consider running 'fd-scraw-harness discover <keyword>' first")
            return
    
    # Step 2: Get high-priority candidates
    init_db()
    
    with get_session() as sess:
        from .models import Candidate
        
        candidates = (
            sess.query(Candidate)
            .filter(Candidate.coverage_status.in_(["new", "partial"]))
            .order_by(Candidate.adjusted_score.desc())
            .limit(top)
            .all()
        )
        
        if not candidates:
            logger.warning("\n⚠️  No high-priority candidates found in database")
            return
        
        logger.info(f"\n📋 Step 2: Retrieving top {len(candidates)} priority candidates...")
        for i, c in enumerate(candidates[:5], 1):
            logger.info(f"   {i}. [{c.adjusted_score or c.score}] {c.title or 'N/A'} ({c.url[:40]})")
        
        # Step 3: Generate spiders (placeholder - integration with subagent framework needed)
        logger.info(f"\n🏭 Step 3: Generating spiders with {workers} workers...")
        logger.info("-" * 80)
        
        # Note: Actual spider generation requires integration with subagent framework
        # For now, just report what would be done
        logger.info(f"   Would generate {len(candidates)} spiders in parallel")
        logger.info(f"   Target directory: /Users/chengsishi/finddata/fd-industry-data/spiers/")
        
        logger.info("\n" + "=" * 80)
        logger.info("💡 Note: Full parallel generation requires subagent framework")
        logger.info("   The coverage analysis and prioritization system is working correctly.")
        logger.info("   To integrate with subagent: modify the code to spawn tasks.")
        logger.info("=" * 80)
