# Spider Testing & Evaluation System

## Overview

The fd-scraw-harness now includes a comprehensive spider testing and evaluation system that validates spider code, checks fd-open-data-protocol compliance, and provides detailed feedback for debugging.

## Features

### 1. **Schema Validation**
- Validates DatasourceManifest YAML against fd-open-data-protocol schema
- Checks for required fields (name, label, functions)
- Validates column types and structure
- Reports specific validation failures with path information

### 2. **Spider Execution Testing**
- **Syntax-only mode**: Validates Python syntax without execution
- **Mock execution**: Imports spider module and checks structure
- **Full testing**: Complete execution with data fetching (when Scrapy available)
- Captures errors, tracebacks, and execution metrics

### 3. **Database Integration**
- Stores test results in SQLite database
- Tracks execution metrics (time, records fetched)
- Maintains validation reports with failure details
- Enables querying and analysis of test history

### 4. **CLI Commands**
- Test individual spiders by manifest ID or file path
- Test all spiders in parallel
- View test results and summaries
- Generate evaluation reports with recommendations

## Commands

### Test a Single Spider

```bash
# Test by manifest ID
fd-scraw-harness test 1

# Test by file path
fd-scraw-harness test ./path/to/spider.py

# Test with verbose output
fd-scraw-harness test 1 --verbose

# Output as JSON
fd-scraw-harness test 1 --json

# Specify test type
fd-scraw-harness test 1 --type syntax_only
fd-scraw-harness test 1 --type mock_execution
fd-scraw-harness test 1 --type full
```

### Test All Spiders

```bash
# Test all spiders
fd-scraw-harness test-all

# Limit number of spiders
fd-scraw-harness test-all --limit 10

# Run in parallel
fd-scraw-harness test-all --parallel 5

# Combine options
fd-scraw-harness test-all --limit 20 --parallel 4 --type syntax_only

# Output as JSON
fd-scraw-harness test-all --json
```

### View Test Results

```bash
# View summary
fd-scraw-harness test-results

# View as JSON
fd-scraw-harness test-results --format json

# Limit recent results
fd-scraw-harness test-results --limit 50
```

### Evaluate Results

```bash
# Get evaluation report with recommendations
fd-scraw-harness evaluate-results

# Verbose evaluation
fd-scraw-harness evaluate-results --verbose
```

## Test Types

### `syntax_only`
- Fastest test type
- Validates Python syntax
- Checks for Spider class and parse methods
- No actual execution

### `mock_execution`
- Imports spider module
- Validates imports and class definitions
- Checks Scrapy component usage
- Does not fetch data

### `full`
- Complete execution (requires Scrapy environment)
- Actually fetches data
- Validates output against schema
- Measures performance metrics

## Database Schema

### `spider_tests` Table
Stores test execution metadata:
- `id`: Test ID
- `manifest_id`: Associated manifest (nullable)
- `spider_path`: Path to spider file
- `test_type`: Type of test performed
- `status`: pending, running, passed, failed, error
- `error_message`: Error details if failed
- `error_traceback`: Full traceback
- `created_at`, `updated_at`: Timestamps

### `test_results` Table
Stores validation results:
- `id`: Result ID
- `test_id`: Foreign key to spider_tests
- `is_valid`: Boolean (1=valid, 0=invalid)
- `validation_report`: JSON with full validation details
- `failure_count`: Number of validation failures
- `warning_count`: Number of warnings

### `execution_metrics` Table
Stores performance metrics:
- `id`: Metrics ID
- `test_id`: Foreign key to spider_tests
- `execution_time_seconds`: Duration
- `records_fetched`: Number of records
- `memory_peak_mb`: Peak memory usage
- `cpu_time_seconds`: CPU time

## Output Formats

### Human-Readable (Default)
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

### JSON Format
```json
{
  "test_id": "123",
  "status": "pass",
  "reason": "All checks passed",
  "execution": {
    "success": true,
    "duration_seconds": 2.5,
    "records_fetched": 100
  },
  "validation": {
    "is_valid": true,
    "failure_count": 0,
    "warning_count": 1,
    "warnings": ["No fetch reference defined"]
  },
  "recommendations": [
    "✓ Spider successfully fetched 100 records"
  ]
}
```

## Validation Checks

### Schema Validation
1. **Required Fields**
   - `name`: Manifest name
   - `label`: Human-readable label
   - `functions`: At least one function defined

2. **Function Structure**
   - Each function must have a `command`
   - Columns must have unique names
   - Frequency values must be valid (daily, weekly, monthly, etc.)

3. **Concept Hints**
   - Referenced columns must exist in functions
   - Entity types must be specified

4. **Fetch Reference**
   - Must specify either `module` or `runner`
   - Module path should follow `package.module:func` format

### Execution Validation
1. **Syntax Checks**
   - Valid Python syntax
   - Proper indentation
   - No undefined variables

2. **Structure Checks**
   - Spider class defined
   - Parse methods present
   - Required imports available

3. **Runtime Checks**
   - No import errors
   - No runtime exceptions
   - Data conforms to schema

## Recommendations System

The system automatically generates recommendations based on test results:

### Common Issues & Fixes

1. **Missing Dependencies**
   ```
   Recommendation: Verify all imports are available and packages are installed
   ```

2. **Syntax Errors**
   ```
   Recommendation: Review Python syntax and indentation
   ```

3. **Missing Commands**
   ```
   Recommendation: Add function commands - each function must have a 'command' field
   ```

4. **Empty Fields**
   ```
   Recommendation: Investigate empty fields - high null ratios may indicate extraction issues
   ```

5. **No Fetch Method**
   ```
   Recommendation: Specify fetch method - add 'fetch' section with module path or runner name
   ```

## Integration with Spider Generation

The `scripts/generate_spiders.py` script now includes automatic testing:

```bash
# Generate spiders with automatic testing
uv run scripts/generate_spiders.py --max-workers 5 --top 20

# Skip automatic testing
uv run scripts/generate_spiders.py --no-test
```

### Workflow
1. Generate spider code for high-priority candidates
2. Automatically test each generated spider
3. Store test results in database
4. Report pass/fail status
5. Provide recommendations for failed spiders

## Example Usage

### Test a Newly Generated Spider

```bash
# 1. Generate spiders
uv run scripts/generate_spiders.py --top 5

# 2. View test results
fd-scraw-harness test-results

# 3. Get detailed evaluation
fd-scraw-harness evaluate-results

# 4. Test specific spider
fd-scraw-harness test 42 --verbose
```

### Batch Testing

```bash
# Test all spiders in parallel
fd-scraw-harness test-all --parallel 8 --limit 50

# Export results to JSON
fd-scraw-harness test-all --json > test_results.json

# Analyze failures
fd-scraw-harness test-results --format json | jq '.recent_tests[] | select(.status == "failed")'
```

### Continuous Integration

```bash
# In CI/CD pipeline
fd-scraw-harness test-all --type syntax_only --json > results.json

# Check pass rate
PASS_RATE=$(jq '.pass_rate' results.json)
if (( $(echo "$PASS_RATE < 0.8" | bc -l) )); then
  echo "Pass rate too low: $PASS_RATE"
  exit 1
fi
```

## Troubleshooting

### Common Issues

1. **"No manifests found"**
   - Run discovery and generation first:
   ```bash
   fd-scraw-harness discover <keyword>
   fd-scraw-harness generate --discovery-id 1
   ```

2. **Import errors during testing**
   - Ensure all dependencies are installed:
   ```bash
   uv sync
   ```

3. **Database locked**
   - Close other processes using the database
   - Or use a different database:
   ```bash
   export HARNESS_DATABASE_URL="sqlite:///data/test.db"
   ```

4. **Slow parallel testing**
   - Reduce parallel workers:
   ```bash
   fd-scraw-harness test-all --parallel 2
   ```

## API Usage

### Python API

```python
from fd_scraw_harness.spider_tester import (
    test_single_spider,
    test_all_spiders,
    get_test_summary,
)

# Test single spider
report = test_single_spider(1, test_type="full")
print(report["status"])

# Test all spiders
summary = test_all_spiders(limit=10, parallel=4)
print(f"Pass rate: {summary['pass_rate']:.1%}")

# Get summary
summary = get_test_summary()
print(f"Total tests: {summary['total_tests']}")
```

### Schema Validation API

```python
from fd_scraw_harness.schema_validator import (
    validate_manifest_yaml,
    validate_sample_data,
)

# Validate manifest
result = validate_manifest_yaml(yaml_content, "my-manifest")
print(f"Valid: {result.is_valid}")
print(f"Failures: {len(result.failures)}")

# Validate sample data
from fd_open_data_protocol.schema import DatasourceManifest
manifest = DatasourceManifest.model_validate(data)
result = validate_sample_data(sample_records, manifest)
```

## Future Enhancements

- [ ] Integration with actual Scrapy execution
- [ ] Performance benchmarking
- [ ] Automated spider repair suggestions
- [ ] Historical trend analysis
- [ ] Visual dashboard for test results
- [ ] Automated retry for failed generations

## References

- [fd-open-data-protocol](../fd-open-data-protocol/) - Schema definition
- [Scrapy Documentation](https://docs.scrapy.org/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
