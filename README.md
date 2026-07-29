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
