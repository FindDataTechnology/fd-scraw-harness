"""CLI entry point for fd-scraw-harness."""
from __future__ import annotations

import sys

import click

from .db import get_session, init_db


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
        session_id = run_discover(url=url)
        click.echo(f"Discovery session {session_id} created for URL: {url}")
    else:
        session_id = run_discover(keyword=keyword)
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
    analysis_id = run_analyze(target_url, discovery_id)
    click.echo(f"Analysis {analysis_id} complete.")
    click.echo(f"\nRun: fd-scraw-harness generate --discovery-id {discovery_id}")


@main.command()
@click.option("--discovery-id", type=int, required=True)
def generate(discovery_id: int) -> None:
    """Generate a DatasourceManifest from analysis data."""
    from .manifest_gen import generate as run_generate

    init_db()

    click.echo(f"Generating manifest for discovery {discovery_id}...")
    manifest_id = run_generate(discovery_id)

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


if __name__ == "__main__":
    main()
