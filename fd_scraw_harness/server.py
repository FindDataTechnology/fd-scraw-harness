"""FastMCP server for fd-scraw-harness - datasource discovery pipeline (async).

Thin composition root: creates the app and registers the phase tool modules
(tools/discovery, tools/generation, tools/testing). Tool behavior and
signatures are unchanged from the pre-split monolith.

Entry: uv run --directory fd-scraw-harness python -m fd_scraw_harness.server
"""
from __future__ import annotations

from pathlib import Path

# Try to load .env file for LINJIE_API_KEY and other settings
try:
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parents[2]  # repo root
    load_dotenv(_ROOT / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
except ImportError:
    pass

from fastmcp import FastMCP

from fd_scraw_harness import tools

app = FastMCP(name="fd-scraw-harness")
tools.register_all(app)


if __name__ == "__main__":
    app.run()
