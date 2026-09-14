# Spider Testing - Quick Start Guide

## 🚀 Get Started in 5 Minutes

### 1. Test Your First Spider

```bash
# Test a specific manifest
fd-scraw-harness test 1

# See detailed output
fd-scraw-harness test 1 --verbose

# Get JSON output
fd-scraw-harness test 1 --json
```

### 2. Test All Spiders

```bash
# Test everything
fd-scraw-harness test-all

# Test top 10 with 5 parallel workers
fd-scraw-harness test-all --limit 10 --parallel 5

# Save results to file
fd-scraw-harness test-all --json > results.json
```

### 3. View Results

```bash
# See summary
fd-scraw-harness test-results

# Get recommendations
fd-scraw-harness evaluate-results
```

## 📊 Common Workflows

### Workflow 1: Generate & Test

```bash
# Generate spiders with automatic testing
uv run scripts/generate_spiders.py --top 20

# Check what failed
fd-scraw-harness test-results

# Get fix recommendations
fd-scraw-harness evaluate-results
```

### Workflow 2: Debug a Failed Spider

```bash
# 1. Find failed tests
fd-scraw-harness test-results | grep "failed"

# 2. Test specific spider with details
fd-scraw-harness test 42 --verbose

# 3. Get JSON for analysis
fd-scraw-harness test 42 --json | jq '.validation.failures'
```

### Workflow 3: Batch Validation

```bash
# Test all with syntax-only (fast)
fd-scraw-harness test-all --type syntax_only

# Test all with mock execution (medium)
fd-scraw-harness test-all --type mock_execution

# Test all with full execution (slow)
fd-scraw-harness test-all --type full
```

## 🎯 Test Types Explained

| Type | Speed | What It Does | When to Use |
|------|-------|--------------|-------------|
| `syntax_only` | ⚡️ Fast | Checks Python syntax | Quick validation |
| `mock_execution` | 🏃 Medium | Imports & validates structure | Structural checks |
| `full` | 🐢 Slow | Actually runs spider | Final validation |

## 📋 Output Examples

### Human-Readable Output
```
✅ Test 123 - PASS
Reason: All checks passed

Execution:
  Success: True
  Duration: 2.500s
  Records: 100

Validation:
  Valid: True
  Failures: 0
  Warnings: 1

Recommendations:
  1. ✓ Spider successfully fetched 100 records
```

### JSON Output
```json
{
  "test_id": "123",
  "status": "pass",
  "execution": {
    "success": true,
    "records_fetched": 100
  },
  "validation": {
    "is_valid": true,
    "failure_count": 0
  }
}
```

## 🔧 Troubleshooting

### Problem: "No manifests found"
**Solution**: Run discovery and generation first
```bash
fd-scraw-harness discover "your keyword"
fd-scraw-harness generate --discovery-id 1
```

### Problem: Import errors
**Solution**: Install dependencies
```bash
uv sync
```

### Problem: Slow parallel testing
**Solution**: Reduce workers
```bash
fd-scraw-harness test-all --parallel 2
```

## 💡 Pro Tips

1. **Use syntax_only for quick checks**
   ```bash
   fd-scraw-harness test-all --type syntax_only
   ```

2. **Export results for analysis**
   ```bash
   fd-scraw-harness test-all --json | jq '.results[] | select(.status == "fail")'
   ```

3. **Test specific file**
   ```bash
   fd-scraw-harness test ./path/to/spider.py
   ```

4. **Check pass rate**
   ```bash
   fd-scraw-harness evaluate-results | grep "Pass Rate"
   ```

## 📚 More Information

- Full documentation: `docs/SPIDER_TESTING.md`
- Implementation report: `TESTING_SYSTEM_REPORT.md`
- Test suite: `test_spider_testing_system.py`

## 🎉 You're Ready!

Start testing your spiders now:
```bash
fd-scraw-harness test 1
```
