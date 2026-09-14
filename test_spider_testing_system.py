#!/usr/bin/env python3
"""
Comprehensive test of the spider testing and evaluation system.

This script tests:
1. Schema validation
2. Spider loading and execution
3. CLI commands
4. Database integration
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from fd_scraw_harness.db import get_session, init_db
from fd_scraw_harness.models import Manifest
from fd_scraw_harness.schema_validator import (
    ValidationResult,
    validate_manifest_yaml,
    create_validation_report,
    generate_recommendations,
)
from fd_scraw_harness.spider_tester import (
    test_single_spider,
    test_all_spiders,
    get_test_summary,
    format_test_report,
    load_spider_from_file,
)


def test_schema_validation():
    """Test schema validation with various inputs."""
    print("\n" + "=" * 80)
    print("🧪 Test 1: Schema Validation")
    print("=" * 80)
    
    # Valid manifest
    valid_yaml = """
version: "1"
name: test-datasource
label: Test Data Source
functions:
  - command: "fetch_data"
    description: "Fetch sample data"
    columns:
      - name: id
        type: integer
      - name: name
        type: string
"""
    
    result = validate_manifest_yaml(valid_yaml, "test-valid")
    print(f"\n✅ Valid manifest: is_valid={result.is_valid}")
    assert result.is_valid, "Valid manifest should pass validation"
    
    # Invalid manifest (missing required fields)
    invalid_yaml = """
version: "1"
# Missing name and label
functions: []
"""
    
    result = validate_manifest_yaml(invalid_yaml, "test-invalid")
    print(f"❌ Invalid manifest: is_valid={result.is_valid}, failures={len(result.failures)}")
    assert not result.is_valid, "Invalid manifest should fail validation"
    
    print("\n✅ Schema validation tests passed")


def test_spider_loading():
    """Test spider loading functionality."""
    print("\n" + "=" * 80)
    print("🧪 Test 2: Spider Loading")
    print("=" * 80)
    
    # Test loading from non-existent file
    result = load_spider_from_file("/nonexistent/path/spider.py")
    print(f"\n❌ Non-existent file: success={result.success}")
    assert not result.success, "Should fail for non-existent file"
    
    # Test loading from invalid file type
    test_file = Path("/tmp/test_spider.txt")
    test_file.write_text("not a python or yaml file")
    
    result = load_spider_from_file(str(test_file))
    print(f"❌ Invalid file type: success={result.success}")
    assert not result.success, "Should fail for unsupported file type"
    
    # Test loading from valid Python file
    test_py = Path("/tmp/test_spider.py")
    test_py.write_text("""
class TestSpider:
    name = "test"
    
    def parse(self, response):
        pass
""")
    
    result = load_spider_from_file(str(test_py))
    print(f"✅ Valid Python file: success={result.success}, name={result.manifest_name}")
    assert result.success, "Should succeed for valid Python file"
    
    print("\n✅ Spider loading tests passed")


def test_validation_report():
    """Test validation report generation."""
    print("\n" + "=" * 80)
    print("🧪 Test 3: Validation Report Generation")
    print("=" * 80)
    
    validation_result = ValidationResult(is_valid=True, manifest_name="test")
    
    report = create_validation_report(
        test_id="test_123",
        validation_result=validation_result,
        execution_success=True,
        records_fetched=100,
        execution_time_seconds=2.5,
    )
    
    print(f"\n✅ Report generated: status={report['status']}")
    assert report["status"] == "pass", "Should pass when all checks succeed"
    
    # Test recommendations
    recommendations = generate_recommendations(report)
    print(f"💡 Recommendations: {len(recommendations)}")
    
    print("\n✅ Validation report tests passed")


def test_database_integration():
    """Test database integration with test results."""
    print("\n" + "=" * 80)
    print("🧪 Test 4: Database Integration")
    print("=" * 80)
    
    init_db()
    
    # Create a test manifest
    with get_session() as sess:
        manifest = Manifest(
            discovery_id=1,
            manifest_yaml="""
version: "1"
name: integration-test
label: Integration Test
functions:
  - command: "fetch"
    columns:
      - name: id
        type: integer
""",
            source_name="integration-test",
            status="draft",
        )
        sess.add(manifest)
        sess.commit()
        manifest_id = manifest.id
    
    print(f"\n✅ Created test manifest: id={manifest_id}")
    
    # Test the manifest
    report = test_single_spider(manifest_id, test_type="syntax_only", store_results=True)
    print(f"✅ Test executed: status={report['status']}")
    
    # Get summary
    summary = get_test_summary()
    print(f"✅ Summary retrieved: total_tests={summary['total_tests']}")
    
    assert summary["total_tests"] > 0, "Should have at least one test"
    
    print("\n✅ Database integration tests passed")


def test_cli_commands():
    """Test CLI command execution."""
    print("\n" + "=" * 80)
    print("🧪 Test 5: CLI Commands")
    print("=" * 80)
    
    import subprocess
    
    # Test help
    result = subprocess.run(
        ["uv", "run", "fd-scraw-harness", "--help"],
        capture_output=True,
        text=True,
    )
    print(f"\n✅ Help command: exit_code={result.returncode}")
    assert result.returncode == 0, "Help should succeed"
    assert "test" in result.stdout, "Should show test command"
    
    # Test test-results
    result = subprocess.run(
        ["uv", "run", "fd-scraw-harness", "test-results"],
        capture_output=True,
        text=True,
    )
    print(f"✅ test-results command: exit_code={result.returncode}")
    assert result.returncode == 0, "test-results should succeed"
    
    # Test evaluate-results
    result = subprocess.run(
        ["uv", "run", "fd-scraw-harness", "evaluate-results"],
        capture_output=True,
        text=True,
    )
    print(f"✅ evaluate-results command: exit_code={result.returncode}")
    assert result.returncode == 0, "evaluate-results should succeed"
    
    print("\n✅ CLI command tests passed")


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("🚀 Spider Testing System - Comprehensive Test Suite")
    print("=" * 80)
    
    try:
        test_schema_validation()
        test_spider_loading()
        test_validation_report()
        test_database_integration()
        test_cli_commands()
        
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        print("\n📊 Summary:")
        print("  • Schema validation: ✅")
        print("  • Spider loading: ✅")
        print("  • Validation reports: ✅")
        print("  • Database integration: ✅")
        print("  • CLI commands: ✅")
        print("\n🎉 Spider testing system is ready for use!")
        print("\nTry these commands:")
        print("  fd-scraw-harness test <manifest-id>")
        print("  fd-scraw-harness test-all --limit 10")
        print("  fd-scraw-harness test-results")
        print("  fd-scraw-harness evaluate-results")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
