# Harness Data Source Monitor

## Status
- **Started**: 2026-08-01 04:07:48
- **Check Interval**: Every 5 minutes
- **Log File**: `/tmp/harness_monitor.log`
- **PID File**: `/tmp/harness_monitor.pid`

## Current Data Sources (as of last check)
- Total: 3 sources
- ID 1: None (deepseek-chat) - 2026-07-29
- ID 2: flowers-kifc-auction (gm51model) - 2026-07-29
- ID 3: integration-test (None) - 2026-07-31

## Monitoring Script
Location: `fd-scraw-harness/scripts/monitor_discovery.py`

The script:
1. Queries the harness database for all manifests
2. Tracks which sources have been seen (by ID)
3. Reports new sources when discovered
4. Waits 5 minutes before next check

## Commands

### Check if monitor is running
```bash
ps aux | grep monitor_discovery
```

### View live log
```bash
tail -f /tmp/harness_monitor.log
```

### Stop the monitor
```bash
pkill -f monitor_discovery
```

### Restart the monitor
```bash
cd fd-scraw-harness
nohup uv run python -u scripts/monitor_discovery.py > /tmp/harness_monitor.log 2>&1 &
echo $! > /tmp/harness_monitor.pid
```

### View current data sources
```bash
cd fd-scraw-harness
sqlite3 data/harness.db "SELECT id, source_name, status, created_at FROM manifests ORDER BY created_at DESC;"
```

## Auto-Evaluation
To enable automatic LLM evaluation of new sources:
```bash
export LINJIE_API_KEY='your-key-here'
```
Then restart the monitor.

## Next Steps
When new data sources are discovered:
1. Review the source name and model used
2. Evaluate data quality (authority, reliability, comprehensiveness, freshness)
3. Approve high-quality sources for integration
4. Generate manifests for approved sources
5. Export manifests to YAML for use in scraw-* projects
