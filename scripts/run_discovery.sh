#!/bin/bash
# Automated multi-industry data source discovery scheduler
# Runs every 6 hours to find new data sources across all SW industries

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/fd-scraw-discovery-$(date +%Y%m%d).log"

echo "=========================================="
echo "Starting Multi-Industry Discovery"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

cd "$SCRIPT_DIR"

# API key: taken from the environment, or from a .env file (never hardcode keys here)
if [ -z "${LINJIE_API_KEY:-}" ]; then
  for env_file in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/../.env" "$SCRIPT_DIR/../../.env"; do
    if [ -f "$env_file" ] && grep -q 'LINJIE_API_KEY' "$env_file"; then
      LINJIE_API_KEY="$(grep -E '^\s*(export\s+)?LINJIE_API_KEY=' "$env_file" | tail -n1 | head -1 | sed 's/^[^=]*=//; s/^"\(.*\)"$/\1/')"
      break
    fi
  done
fi
export LINJIE_API_KEY="${LINJIE_API_KEY:-sk-your-linjie-api-key}"
export LINJIE_BASE_URL="${LINJIE_BASE_URL:-https://www.linjie.love/v1}"

# Run batch discovery for first 10 industries (can be expanded)
uv run python scripts/batch_discover.py >> "$LOG_FILE" 2>&1

# Check results
RESULT_COUNT=$(uv run python << 'EOF'
from fd_scraw_harness.db import get_session, init_db
init_db()
with get_session() as sess:
    from fd_scraw_harness.models import Candidate
    total = sess.query(Candidate).filter(Candidate.created_at > "2026-07-29").count()
    print(total)
EOF
)

echo ""
echo "✅ Discovery completed!"
echo "   New candidates found: $RESULT_COUNT"
echo "   Log file: $LOG_FILE"
echo "=========================================="
