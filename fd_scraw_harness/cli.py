"""CLI entry point for fd-scraw-harness."""
from __future__ import annotations

import asyncio
import sys

import click

from .db import get_session, init_db

_STATUS_ICON = {  # coverage + test statuses share one lookup (no key collision)
    "covered": "✅", "partial": "⚠️ ", "new": "🆕", "unknown": "❓",
    "passed": "✅", "failed": "❌", "error": "⚠️",
}


def _section(title: str) -> None:
    """Print an ``=== title ===`` banner."""
    click.echo("=" * 80)
    click.echo(title)
    click.echo("=" * 80)


@click.group()
@click.version_option(package_name="fd-scraw-harness")
def main() -> None:
    """fd-scraw-harness: automated datasource discovery pipeline."""


@main.command()
@click.argument("keyword", required=False)
@click.option("--url", help="Direct URL to analyze (skips LLM web search)")
def discover(keyword: str | None, url: str | None) -> None:
    """Discover candidate data sources from a keyword or URL."""
    if not keyword and not url:
        click.echo("Error: provide a keyword or --url", err=True)
        sys.exit(1)

    from .discovery import discover as run_discover

    init_db()

    if url:
        session_id = asyncio.run(run_discover(url=url))
        click.echo(f"Discovery session {session_id} created for URL: {url}")
    else:
        session_id = asyncio.run(run_discover(keyword=keyword))
        click.echo(f"Discovery session {session_id} created for keyword: {keyword!r}")

    with get_session() as sess:
        from .models import Candidate

        candidates = (
            sess.query(Candidate)
            .filter_by(discovery_id=session_id)
            .all()
        )
        click.echo(f"\n{len(candidates)} candidate(s) found:")
        for i, c in enumerate(candidates):
            click.echo(f"  [{i}] {c.title or 'Untitled'}")
            click.echo(f"      URL: {c.url}")
            if c.description:
                click.echo(f"      {c.description[:120]}")
        click.echo(f"\nRun: fd-scraw-harness analyze --discovery-id {session_id}")


@main.command()
@click.option("--discovery-id", type=int, required=True)
@click.option("--url", help="Specific candidate URL to analyze")
@click.option("--candidate-index", type=int, help="Index from discover output")
def analyze(discovery_id: int, url: str | None, candidate_index: int | None) -> None:
    """Analyze a candidate URL via ego-browser."""
    from .analyzer import analyze as run_analyze
    from .models import Candidate

    init_db()

    with get_session() as sess:
        candidates = (
            sess.query(Candidate)
            .filter_by(discovery_id=discovery_id)
            .all()
        )
        if not candidates:
            click.echo(f"No candidates found for discovery {discovery_id}", err=True)
            sys.exit(1)

        if candidate_index is not None:
            if candidate_index >= len(candidates):
                click.echo(f"Index {candidate_index} out of range (0-{len(candidates)-1})", err=True)
                sys.exit(1)
            target_url = candidates[candidate_index].url
        elif url:
            target_url = url
        else:
            click.echo("Provide --url or --candidate-index", err=True)
            sys.exit(1)

    click.echo(f"Analyzing: {target_url}")
    analysis_id = asyncio.run(run_analyze(target_url, discovery_id))
    click.echo(f"Analysis {analysis_id} complete.")
    click.echo(f"\nRun: fd-scraw-harness generate --discovery-id {discovery_id}")


@main.command()
@click.option("--discovery-id", type=int, required=True)
def generate(discovery_id: int) -> None:
    """Generate a DatasourceManifest from analysis data."""
    from .manifest_gen import generate as run_generate

    init_db()

    click.echo(f"Generating manifest for discovery {discovery_id}...")
    manifest_id = asyncio.run(run_generate(discovery_id))

    with get_session() as sess:
        from .models import Manifest

        m = sess.query(Manifest).filter_by(id=manifest_id).first()
        if m:
            click.echo(f"\nManifest {m.id} [{m.status}]")
            click.echo(f"  Source: {m.source_name or 'unknown'}")
            click.echo(f"  Model:  {m.model_used}")
            if m.validation_error:
                click.echo(f"  Error:  {m.validation_error}")
            click.echo(f"\nRun: fd-scraw-harness approve {m.id}")


@main.command("list")
@click.option("--status", default=None, help="Filter by status (draft/approved/rejected)")
def list_(status: str | None) -> None:
    """List manifests."""
    init_db()

    with get_session() as sess:
        from .models import Manifest

        q = sess.query(Manifest)
        if status:
            q = q.filter_by(status=status)
        manifests = q.order_by(Manifest.created_at.desc()).all()

        if not manifests:
            click.echo("No manifests found.")
            return

        click.echo(f"{'ID':>4}  {'Status':<10}  {'Source':<24}  {'Model':<20}  Created")
        click.echo("-" * 80)
        for m in manifests:
            click.echo(
                f"{m.id:>4}  {m.status:<10}  "
                f"{(m.source_name or 'unknown')[:24]:<24}  "
                f"{(m.model_used or '')[:20]:<20}  "
                f"{m.created_at:%Y-%m-%d %H:%M}"
            )


@main.command()
@click.argument("manifest_id", type=int)
def approve(manifest_id: int) -> None:
    """Approve a draft manifest."""
    init_db()

    with get_session() as sess:
        from .models import Manifest

        m = sess.query(Manifest).filter_by(id=manifest_id).first()
        if not m:
            click.echo(f"Manifest {manifest_id} not found", err=True)
            sys.exit(1)
        if m.status != "draft":
            click.echo(f"Manifest {manifest_id} is {m.status}, not draft", err=True)
            sys.exit(1)
        m.status = "approved"
        sess.commit()
        click.echo(f"Manifest {manifest_id} approved.")


@main.command()
@click.argument("manifest_id", type=int)
def reject(manifest_id: int) -> None:
    """Reject a draft manifest."""
    init_db()

    with get_session() as sess:
        from .models import Manifest

        m = sess.query(Manifest).filter_by(id=manifest_id).first()
        if not m:
            click.echo(f"Manifest {manifest_id} not found", err=True)
            sys.exit(1)
        m.status = "rejected"
        sess.commit()
        click.echo(f"Manifest {manifest_id} rejected.")


@main.command()
@click.argument("manifest_id", type=int)
@click.option("--output", "-o", default=None, help="Output file path (default: stdout)")
def export(manifest_id: int, output: str | None) -> None:
    """Export an approved manifest to YAML."""
    init_db()

    with get_session() as sess:
        from .models import Manifest

        m = sess.query(Manifest).filter_by(id=manifest_id).first()
        if not m:
            click.echo(f"Manifest {manifest_id} not found", err=True)
            sys.exit(1)
        if m.status != "approved":
            click.echo(f"Manifest {manifest_id} is {m.status}, not approved", err=True)
            sys.exit(1)

        if output:
            with open(output, "w") as f:
                f.write(m.manifest_yaml)
            click.echo(f"Manifest exported to {output}")
        else:
            click.echo(m.manifest_yaml)


@main.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed coverage analysis")
def analyze_coverage(verbose: bool) -> None:
    """Analyze coverage of candidate data sources against existing sources."""
    init_db()
    
    from .coverage import analyze_all_candidates, print_coverage_report
    
    click.echo("Analyzing coverage of candidate data sources...")
    click.echo("Checking fd-open-data-mcp and fd-industry-data for existing sources...")
    
    results = asyncio.run(analyze_all_candidates())
    
    print_coverage_report(results)
    
    if verbose:
        click.echo("\n📝 详细覆盖信息:")
        for c in results["candidates"]:
            if c["coverage_status"] != "new":
                click.echo(f"\n  {c['title'] or 'N/A'}")
                click.echo(f"    URL: {c['url']}")
                click.echo(f"    状态: {c['coverage_status']}")
                click.echo(f"    原因: {c['reason']}")


@main.command()
@click.option("--status", type=click.Choice(["covered", "partial", "new", "unknown"]), help="Filter by coverage status")
@click.option("--min-score", type=int, default=0, help="Minimum adjusted score")
def list_candidates(status: str | None, min_score: int) -> None:
    """List candidate data sources with coverage analysis."""
    init_db()
    
    with get_session() as sess:
        from .models import Candidate
        
        query = sess.query(Candidate)
        
        if status:
            query = query.filter_by(coverage_status=status)
        
        if min_score > 0:
            query = query.filter(Candidate.adjusted_score >= min_score)
        
        candidates = query.order_by(Candidate.adjusted_score.desc()).all()
        
        if not candidates:
            click.echo("No candidates found matching criteria.")
            return
        
        click.echo(f"\n📋 候选数据源列表 ({len(candidates)} 个):")
        click.echo("-" * 80)
        
        for i, c in enumerate(candidates, 1):
            status_icon = _STATUS_ICON.get(c.coverage_status, "❓")
            
            score_str = f"{c.adjusted_score or c.score:3d}"
            if c.adjusted_score and c.adjusted_score != c.score:
                score_str += f" (原:{c.score})"
            
            click.echo(f"\n{i}. {status_icon} [{score_str}] {c.title or 'N/A'}")
            click.echo(f"   URL: {c.url}")
            if c.description:
                click.echo(f"   描述: {c.description[:100]}...")
            if c.coverage_details:
                import json
                details = json.loads(c.coverage_details)
                click.echo(f"   原因: {details.get('reason', 'N/A')}")


@main.command()
@click.argument("target")
@click.option("--type", "test_type", type=click.Choice(["full", "syntax_only", "mock_execution"]), 
              default="full", help="Test type")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def test(target: str, test_type: str, verbose: bool, output_json: bool) -> None:
    """Test a single spider (by manifest ID or file path)."""
    import json as json_module
    
    from .spider_tester import format_test_report, test_single_spider
    
    init_db()
    
    # Determine if target is manifest ID or file path
    try:
        manifest_id = int(target)
        if not output_json:
            click.echo(f"Testing manifest {manifest_id}...")
        report = test_single_spider(manifest_id, test_type=test_type, store_results=True)
    except ValueError:
        # It's a file path
        if not output_json:
            click.echo(f"Testing spider file: {target}")
        report = test_single_spider(target, test_type=test_type, store_results=True)
    
    if output_json:
        click.echo(json_module.dumps(report, indent=2))
    else:
        click.echo(format_test_report(report, verbose=verbose))
    
    # Exit with appropriate code
    sys.exit(0 if report.get("status") == "pass" else 1)


@main.command("test-all")
@click.option("--limit", "-l", type=int, default=None, help="Limit number of spiders to test")
@click.option("--parallel", "-p", type=int, default=1, help="Number of parallel workers")
@click.option("--type", "test_type", type=click.Choice(["full", "syntax_only", "mock_execution"]),
              default="full", help="Test type")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def test_all(limit: int | None, parallel: int, test_type: str, output_json: bool) -> None:
    """Test all spiders in the database."""
    import json as json_module
    
    from .spider_tester import test_all_spiders
    
    init_db()
    
    click.echo(f"Testing all spiders (limit={limit}, parallel={parallel})...")
    click.echo("")
    
    summary = test_all_spiders(limit=limit, parallel=parallel, test_type=test_type)
    
    if output_json:
        click.echo(json_module.dumps(summary, indent=2))
    else:
        # Print summary
        _section("📊 Test Summary")
        click.echo(f"Total: {summary['total']}")
        click.echo(f"Passed: {summary['passed']} ✅")
        click.echo(f"Failed: {summary['failed']} ❌")
        click.echo(f"Errors: {summary['errors']} ⚠️")
        click.echo(f"Pass Rate: {summary['pass_rate']:.1%}")
        click.echo("=" * 80)
        
        # Show failed tests
        failed = [r for r in summary["results"] if r["status"] == "fail"]
        if failed:
            click.echo(f"\n❌ Failed Tests ({len(failed)}):")
            for report in failed[:10]:  # Show first 10
                click.echo(f"  • Test {report['test_id']}: {report['reason']}")
            if len(failed) > 10:
                click.echo(f"  ... and {len(failed) - 10} more")
    
    sys.exit(0 if summary["failed"] == 0 and summary["errors"] == 0 else 1)


@main.command("test-results")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
@click.option("--limit", "-l", type=int, default=20, help="Number of recent results to show")
def test_results(output_format: str, limit: int) -> None:
    """View test results summary."""
    import json as json_module
    
    from .spider_tester import get_test_summary
    
    init_db()
    
    summary = get_test_summary()
    
    if output_format == "json":
        click.echo(json_module.dumps(summary, indent=2))
    else:
        _section("📊 Test Results Summary")
        click.echo(f"Total Tests: {summary['total_tests']}")
        click.echo(f"Passed: {summary['passed']} ✅")
        click.echo(f"Failed: {summary['failed']} ❌")
        click.echo(f"Errors: {summary['errors']} ⚠️")
        click.echo(f"Pass Rate: {summary['pass_rate']:.1%}")
        click.echo("=" * 80)
        
        if summary["recent_tests"]:
            click.echo(f"\n📋 Recent Tests (last {limit}):")
            for test in summary["recent_tests"][:limit]:
                status_icon = _STATUS_ICON.get(test["status"], "❓")
                
                click.echo(f"\n  {status_icon} Test #{test['id']} - {test['status']}")
                if test["manifest_id"]:
                    click.echo(f"     Manifest: {test['manifest_id']}")
                if test["spider_path"]:
                    click.echo(f"     Path: {test['spider_path']}")
                if test["error"]:
                    click.echo(f"     Error: {test['error'][:100]}")
                click.echo(f"     Time: {test['tested_at']}")


@main.command("evaluate-results")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed analysis")
def evaluate_results(verbose: bool) -> None:
    """Evaluate all test results and provide recommendations."""
    from .spider_tester import get_test_summary
    
    init_db()
    
    summary = get_test_summary()
    
    _section("🔍 Evaluation Report")
    
    # Overall health
    total = summary["total_tests"]
    passed = summary["passed"]
    failed = summary["failed"]
    errors = summary["errors"]
    
    if total == 0:
        click.echo("\n⚠️  No tests have been run yet.")
        click.echo("Run: fd-scraw-harness test-all")
        return
    
    pass_rate = summary["pass_rate"]
    
    click.echo(f"\n📊 Overall Health: {'✅ GOOD' if pass_rate > 0.8 else '⚠️ NEEDS ATTENTION' if pass_rate > 0.5 else '❌ POOR'}")
    click.echo(f"   Pass Rate: {pass_rate:.1%} ({passed}/{total})")
    
    # Analyze failure patterns
    if failed > 0 or errors > 0:
        click.echo(f"\n❌ Issues Found: {failed + errors}")
        
        # Get recent failures
        recent_failures = [
            t for t in summary["recent_tests"]
            if t["status"] in ["failed", "error"]
        ]
        
        if recent_failures:
            click.echo("\n📋 Recent Failures:")
            for test in recent_failures[:5]:
                path_or_manifest = test['spider_path'] or f"Manifest {test['manifest_id']}"
                click.echo(f"  • {path_or_manifest}")
                if test["error"]:
                    click.echo(f"    Error: {test['error'][:100]}")
    
    if errors > 0:
        click.echo(f"\n⚠️  {errors} tests had execution errors - check error logs")
    
    click.echo("=" * 80)


if __name__ == "__main__":
    main()
