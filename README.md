# fd-scraw-harness

Automated datasource discovery pipeline: web search via LLM, page analysis via ego-browser, manifest generation via LiteLLM, dual-database persistence.

## Install

```bash
cd fd-scraw-harness
uv sync
uv pip install -e ../fd-open-data-protocol
```

## Usage

### 1. Discover candidate data sources

```bash
# From a keyword (uses LLM web search)
fd-scraw-harness discover "Chinese GDP data"

# From a direct URL
fd-scraw-harness discover --url https://data.stats.gov.cn
```

### 2. Analyze a candidate via ego-browser

```bash
fd-scraw-harness analyze --discovery-id 1 --candidate-index 0
# or
fd-scraw-harness analyze --discovery-id 1 --url https://data.stats.gov.cn
```

### 3. Generate a DatasourceManifest

```bash
fd-scraw-harness generate --discovery-id 1
```

### 4. Review and approve

```bash
fd-scraw-harness list                    # list all manifests
fd-scraw-harness list --status draft     # filter by status
fd-scraw-harness approve 1               # approve manifest
fd-scraw-harness export 1                # print YAML to stdout
fd-scraw-harness export 1 -o manifest.yaml  # export to file
```

### 5. Analyze coverage (NEW!)

Automatically analyze which candidate data sources are already covered by existing sources in fd-open-data-mcp or fd-industry-data:

```bash
# Run coverage analysis
uv run scripts/analyze_coverage.py

# With verbose logging
uv run scripts/analyze_coverage.py --verbose
```

This will:
- Check if URLs are already registered in fd-open-data-mcp
- Analyze field overlap with existing data sources
- Automatically adjust priority scores (covered sources get lower priority)
- Generate a detailed report showing which sources are new vs. covered

**Output example:**
```
================================================================================
📊 覆盖分析报告
================================================================================

总计候选数据源: 320
  ✅ 已覆盖 (covered): 4
  ⚠️  部分覆盖 (partial): 0
  🆕 新数据源 (new): 316
  ❓ 未知 (unknown): 0

💡 建议:
  • 优先处理 'new' 状态的数据源（新增价值）
  • 谨慎处理 'covered' 状态的数据源（可能重复）
  • 评估 'partial' 状态的数据源（可能有独特数据）
================================================================================
```

**Integration with discovery workflow:**

The coverage analysis automatically runs after discovery and updates the `adjusted_score` field in the database. Use `adjusted_score` instead of `score` to prioritize truly new data sources.

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Database (default: SQLite at data/harness.db)
HARNESS_DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db

# LiteLLM model
HARNESS_LITELLM_MODEL=deepseek-chat
HARNESS_MODEL_DISCOVERY=doubao-pro-32k
HARNESS_MODEL_GENERATION=deepseek-chat

# API keys (set the ones you need)
DEEPSEEK_API_KEY=sk-...
ARK_API_KEY=...        # for Doubao via Volcengine Ark
```

## Architecture

```
keyword/URL → discover (LLM search) → analyze (ego-browser) → generate (LLM → YAML) → approve → export
```

- **SQLite** (local, default) or **PostgreSQL** (remote) for persistence
- **LiteLLM** for multi-model LLM calls with response caching
- **ego-browser** for live page structure analysis
- Output conforms to `fd-open-data-protocol.DatasourceManifest`

---

## Using as MCP Server

The harness can be used as an MCP server integrated with agents like OpenCode and Claude Code.

### Quick Setup

Add this to your `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "fd-scraw-harness": {
      "enabled": true,
      "command": "uv",
      "args": ["run", "--directory", "/Users/chengsishi/finddata/fd-scraw-harness", "python", "-m", "fd_scraw_harness.server"],
      "env": {
        "LINJIE_API_KEY": "sk-...",
        "HARNESS_LITELLM_MODEL": "linjie/gm51model"
      }
    }
  }
}
```

Or set `LINJIE_API_KEY` in your shell environment before starting the agent.

### Available MCP Tools

Once connected, agents can call:

| Tool | Description |
|------|-------------|
| `harness_status()` | Report server capabilities (mode, models, ego-browser availability) |
| `discover_sources(keyword)` | Discover candidates from keyword via LLM web search |
| `discover_sources(url="...")` | Analyze direct URL (skips LLM search) |
| `analyze_page(url, discovery_id)` | Page structure analysis via ego-browser |
| `generate_manifest(discovery_id)` | Generate DatasourceManifest YAML |
| `list_candidates(discovery_id)` | List discovered sources with coverage status |
| `list_manifests(status?)` | List manifests filtered by status |
| `approve_manifest(id)` | Mark draft manifest as approved |
| `reject_manifest(id)` | Reject a draft manifest |
| `export_manifest(id)` | Export approved manifest as YAML text |
| `coverage_report()` | Full coverage analysis report |
| `test_spider(manifest_id)` | Test spider implementation |
| `test_all_spiders(limit?, parallel?)` | Batch test all spiders |

### Example Workflow

**Agent can now:**

```
1. harness_status() → verify server is ready
2. discover_sources(keyword="半导体行业数据源") → get discovery_id
3. list_candidates(discovery_id=N) → see discovered sources
4. analyze_page(url="...", discovery_id=N) → analyze top candidate
5. generate_manifest(discovery_id=N) → create manifest
6. approve_manifest(M) → mark as ready
7. export_manifest(M) → get full YAML
8. test_spider(M) → validate generated spider
9. coverage_report() → check for duplicates
```

All without leaving the agent's workflow!

### Environment Variables

Required for LLM calls:
- `LINJIE_API_KEY`: Your Linjie AI API key (from https://www.linjie.love/)

Optional model selection:
- `HARNESS_LITELLM_MODEL`: Default model (default: gm51model)
- `HARNESS_MODEL_DISCOVERY`: Discovery phase model (default: gm51model)
- `HARNESS_MODEL_GENERATION`: Manifest generation model (default: qmodel_latest)

Database:
- `HARNESS_DATABASE_URL`: PostgreSQL URL for remote DB (default: SQLite at data/harness.db)

## Async Architecture (v0.2.0+)

Starting from v0.2.0, the MCP server uses async tool handlers for improved concurrency and throughput:

- All 14 MCP tools are `async def` handlers
- Database layer uses SQLAlchemy 2.0+ async engine (`aiosqlite` for SQLite, `asyncpg` for PostgreSQL)
- HTTP calls use `httpx.AsyncClient` (LLM, discovery, analysis)
- Subprocess calls use `asyncio.create_subprocess_exec` (ego-browser)
- Per-tool timeout guards prevent hangs (configurable via `HARNESS_TOOL_TIMEOUT_*` env vars)
- Semaphore-based concurrency limits for resource protection (LLM, spider tests, analysis)

### Deployment

The async MCP server runs on FastMCP's async runtime. No special deployment changes needed — `app.run()` handles the event loop. For production, ensure your environment supports async Python (Python 3.10+).

### Concurrency Tuning

Environment variables for concurrency limits:
- `HARNESS_LLM_CONCURRENCY`: Max concurrent LLM calls (default: 5)
- `HARNESS_SPIDER_CONCURRENCY`: Max concurrent spider tests (default: 3)
- `HARNESS_ANALYSIS_CONCURRENCY`: Max concurrent page analyses (default: 2)

### Timeout Configuration

Per-tool timeouts (seconds):
- `HARNESS_TOOL_TIMEOUT_ANALYZE_PAGE`: 60 (default)
- `HARNESS_TOOL_TIMEOUT_TEST_SPIDER`: 300 (default)
- `HARNESS_TOOL_TIMEOUT_DISCOVER_SOURCES`: 120 (default)
- `HARNESS_TOOL_TIMEOUT_GENERATE_MANIFEST`: 180 (default)
- `HARNESS_TOOL_TIMEOUT_COVERAGE_REPORT`: 120 (default)
- `HARNESS_TOOL_TIMEOUT_TEST_ALL_SPIDERS`: 600 (default)
- Others: 30 (default)
