"""Spider testing: load, execute, and validate spider code."""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import logging
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from .db import get_db, get_session
from .models import ExecutionMetrics, Manifest, SpiderTest, TestResult
from .schema_validator import (
    ValidationResult,
    create_validation_report,
    generate_recommendations,
    validate_manifest_yaml,
)

logger = logging.getLogger(__name__)


@dataclass
class SpiderLoadResult:
    """Result of loading a spider."""
    success: bool
    spider_path: Optional[str] = None
    manifest_yaml: Optional[str] = None
    manifest_name: Optional[str] = None
    error: Optional[str] = None
    error_traceback: Optional[str] = None


@dataclass
class SpiderExecutionResult:
    """Result of executing a spider."""
    success: bool
    records_fetched: int = 0
    execution_time_seconds: float = 0.0
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    sample_data: Optional[list[dict]] = None


def load_spider_from_manifest(manifest_id: int) -> SpiderLoadResult:
    """Load spider code and manifest from database by manifest ID."""
    with get_session() as sess:
        manifest = sess.query(Manifest).filter_by(id=manifest_id).first()
        
        if not manifest:
            return SpiderLoadResult(
                success=False,
                error=f"Manifest {manifest_id} not found"
            )
        
        if not manifest.manifest_yaml:
            return SpiderLoadResult(
                success=False,
                error=f"Manifest {manifest_id} has no YAML content"
            )
        
        # Try to find associated spider file
        # Look in common locations
        source_name = manifest.source_name or f"manifest_{manifest_id}"
        spider_paths = [
            f"fd-industry-data/spiders/{source_name}/spider.py",
            f"fd-industry-data/spiders/{source_name.replace('-', '_')}/spider.py",
            f"fd-industry-data/spiders/{source_name}/spider.yaml",
        ]
        
        spider_path = None
        for path in spider_paths:
            if Path(path).exists():
                spider_path = path
                break
        
        return SpiderLoadResult(
            success=True,
            spider_path=spider_path,
            manifest_yaml=manifest.manifest_yaml,
            manifest_name=source_name
        )


def load_spider_from_file(file_path: str) -> SpiderLoadResult:
    """Load spider from a file path (Python or YAML)."""
    path = Path(file_path)
    
    if not path.exists():
        return SpiderLoadResult(
            success=False,
            error=f"File not found: {file_path}"
        )
    
    if path.suffix == ".py":
        # Python spider file
        try:
            with open(path) as f:
                code = f.read()
            
            # Check for syntax errors
            ast.parse(code)
            
            # Try to find companion manifest.yaml
            manifest_path = path.parent / "manifest.yaml"
            if manifest_path.exists():
                with open(manifest_path) as f:
                    manifest_yaml = f.read()
            else:
                # Create minimal manifest
                manifest_yaml = f"""
version: "1"
name: {path.stem}
label: {path.stem}
functions:
  - command: "fetch_data"
    description: "Fetch data from {path.stem}"
"""
            
            return SpiderLoadResult(
                success=True,
                spider_path=str(path),
                manifest_yaml=manifest_yaml,
                manifest_name=path.stem
            )
            
        except SyntaxError as e:
            return SpiderLoadResult(
                success=False,
                spider_path=str(path),
                error=f"Syntax error in {path}: {e}",
                error_traceback=traceback.format_exc()
            )
        except Exception as e:
            return SpiderLoadResult(
                success=False,
                spider_path=str(path),
                error=f"Failed to load {path}: {e}",
                error_traceback=traceback.format_exc()
            )
    
    elif path.suffix in [".yaml", ".yml"]:
        # YAML manifest file
        try:
            with open(path) as f:
                manifest_yaml = f.read()
            
            # Parse to get name
            data = yaml.safe_load(manifest_yaml)
            name = data.get("name", path.stem)
            
            # Look for companion spider.py
            spider_py = path.parent / "spider.py"
            spider_path = str(spider_py) if spider_py.exists() else None
            
            return SpiderLoadResult(
                success=True,
                spider_path=spider_path,
                manifest_yaml=manifest_yaml,
                manifest_name=name
            )
            
        except Exception as e:
            return SpiderLoadResult(
                success=False,
                spider_path=str(path),
                error=f"Failed to load {path}: {e}",
                error_traceback=traceback.format_exc()
            )
    
    else:
        return SpiderLoadResult(
            success=False,
            error=f"Unsupported file type: {path.suffix}"
        )


def execute_spider_syntax_check(spider_path: str) -> SpiderExecutionResult:
    """
    Perform syntax-only check on spider code.
    
    This validates Python syntax without actually executing the spider.
    """
    start_time = time.time()
    
    try:
        with open(spider_path) as f:
            code = f.read()
        
        # Parse to check syntax
        ast.parse(code)
        
        # Check for common Scrapy patterns
        has_spider_class = "class" in code and ("Spider" in code or "CrawlSpider" in code)
        has_parse_method = "def parse" in code
        
        if not has_spider_class:
            logger.warning(f"Spider {spider_path} may not define a Spider class")
        
        if not has_parse_method:
            logger.warning(f"Spider {spider_path} may not have a parse method")
        
        execution_time = time.time() - start_time
        
        return SpiderExecutionResult(
            success=True,
            execution_time_seconds=execution_time,
            records_fetched=0,  # Syntax check doesn't fetch
        )
        
    except SyntaxError as e:
        execution_time = time.time() - start_time
        return SpiderExecutionResult(
            success=False,
            execution_time_seconds=execution_time,
            error=f"Syntax error: {e}",
            error_traceback=traceback.format_exc()
        )
    except Exception as e:
        execution_time = time.time() - start_time
        return SpiderExecutionResult(
            success=False,
            execution_time_seconds=execution_time,
            error=f"Execution check failed: {e}",
            error_traceback=traceback.format_exc()
        )


def execute_spider_mock(spider_path: str, timeout_seconds: int = 30) -> SpiderExecutionResult:
    """
    Mock execution of spider code.
    
    Attempts to import the spider module and instantiate it without running Scrapy.
    This tests imports and basic structure without actual crawling.
    """
    start_time = time.time()
    
    try:
        # Load the module
        spec = importlib.util.spec_from_file_location("spider_module", spider_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {spider_path}")
        
        module = importlib.util.module_from_spec(spec)
        
        # Add to sys.modules temporarily
        sys.modules["spider_module"] = module
        
        try:
            # Execute the module (this will run imports and class definitions)
            spec.loader.exec_module(module)
            
            # Look for Spider classes
            spider_classes = [
                obj for name, obj in vars(module).items()
                if isinstance(obj, type) and "Spider" in name
            ]
            
            if not spider_classes:
                logger.warning(f"No Spider class found in {spider_path}")
            
            execution_time = time.time() - start_time
            
            return SpiderExecutionResult(
                success=True,
                execution_time_seconds=execution_time,
                records_fetched=0,  # Mock doesn't fetch
            )
            
        finally:
            # Clean up sys.modules
            if "spider_module" in sys.modules:
                del sys.modules["spider_module"]
    
    except Exception as e:
        execution_time = time.time() - start_time
        return SpiderExecutionResult(
            success=False,
            execution_time_seconds=execution_time,
            error=f"Mock execution failed: {e}",
            error_traceback=traceback.format_exc()
        )


def test_single_spider(
    target: str | int,
    test_type: str = "full",
    store_results: bool = True,
) -> dict[str, Any]:
    """
    Test a single spider.
    
    Args:
        target: Manifest ID (int) or spider file path (str)
        test_type: "full", "syntax_only", or "mock_execution"
        store_results: Whether to store results in database
    
    Returns:
        Test report dictionary
    """
    logger.info(f"Testing spider: {target} (type: {test_type})")
    
    # Load the spider
    if isinstance(target, int):
        load_result = load_spider_from_manifest(target)
    else:
        load_result = load_spider_from_file(target)
    
    if not load_result.success:
        logger.error(f"Failed to load spider: {load_result.error}")
        
        if store_results:
            # Store failure in database
            with get_session() as sess:
                test = SpiderTest(
                    manifest_id=target if isinstance(target, int) else None,
                    spider_path=load_result.spider_path,
                    test_type=test_type,
                    status="error",
                    error_message=load_result.error,
                    error_traceback=load_result.error_traceback,
                )
                sess.add(test)
                sess.commit()
                
                return create_validation_report(
                    test_id=str(test.id),
                    validation_result=ValidationResult(is_valid=False, manifest_name="unknown"),
                    execution_success=False,
                    execution_error=load_result.error,
                )
        
        return {
            "status": "error",
            "error": load_result.error,
        }
    
    # Validate manifest
    validation_result = validate_manifest_yaml(
        load_result.manifest_yaml,
        load_result.manifest_name or "unknown"
    )
    
    # Execute spider based on test_type
    execution_result = SpiderExecutionResult(success=True)
    
    if test_type in ["full", "mock_execution"]:
        if load_result.spider_path:
            if test_type == "syntax_only":
                execution_result = execute_spider_syntax_check(load_result.spider_path)
            else:
                execution_result = execute_spider_mock(load_result.spider_path)
        else:
            logger.warning("No spider.py file found, skipping execution")
    
    elif test_type == "syntax_only":
        if load_result.spider_path:
            execution_result = execute_spider_syntax_check(load_result.spider_path)
    
    # Create comprehensive report
    test_id = f"test_{int(time.time())}"
    report = create_validation_report(
        test_id=test_id,
        validation_result=validation_result,
        execution_success=execution_result.success,
        execution_error=execution_result.error,
        records_fetched=execution_result.records_fetched,
        execution_time_seconds=execution_result.execution_time_seconds,
    )
    
    # Add recommendations
    report["recommendations"] = generate_recommendations(report)
    
    # Store results in database
    if store_results:
        with get_session() as sess:
            test = SpiderTest(
                manifest_id=target if isinstance(target, int) else None,
                spider_path=load_result.spider_path,
                test_type=test_type,
                status="passed" if report["status"] == "pass" else "failed",
                error_message=execution_result.error,
                error_traceback=execution_result.error_traceback,
            )
            sess.add(test)
            sess.flush()  # Get test.id
            
            # Store validation result
            result = TestResult(
                test_id=test.id,
                is_valid=1 if validation_result.is_valid else 0,
                validation_report=json.dumps(report["validation"]),
                failure_count=len(validation_result.failures),
                warning_count=len(validation_result.warnings),
            )
            sess.add(result)
            
            # Store execution metrics
            metrics = ExecutionMetrics(
                test_id=test.id,
                execution_time_seconds=execution_result.execution_time_seconds,
                records_fetched=execution_result.records_fetched,
            )
            sess.add(metrics)
            
            sess.commit()
            report["test_id"] = str(test.id)
    
    return report


def test_all_spiders(
    limit: Optional[int] = None,
    parallel: int = 1,
    test_type: str = "full",
) -> dict[str, Any]:
    """
    Test all spiders in the database.
    
    Args:
        limit: Maximum number of spiders to test
        parallel: Number of parallel workers
        test_type: Test type to use
    
    Returns:
        Summary of all test results
    """
    logger.info(f"Testing all spiders (limit={limit}, parallel={parallel})")
    
    with get_session() as sess:
        query = sess.query(Manifest)
        if limit:
            query = query.limit(limit)
        
        manifests = query.all()
        manifest_ids = [m.id for m in manifests]
    
    logger.info(f"Found {len(manifest_ids)} manifests to test")
    
    results = []
    passed = 0
    failed = 0
    errors = 0
    
    if parallel > 1:
        # Parallel execution
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(test_single_spider, mid, test_type, True): mid
                for mid in manifest_ids
            }
            
            for future in as_completed(futures):
                manifest_id = futures[future]
                try:
                    report = future.result()
                    results.append(report)
                    
                    if report["status"] == "pass":
                        passed += 1
                    elif report["status"] == "fail":
                        failed += 1
                    else:
                        errors += 1
                    
                    logger.info(f"  [{manifest_id}] {report['status']}")
                    
                except Exception as e:
                    logger.error(f"  [{manifest_id}] Error: {e}")
                    errors += 1
    else:
        # Sequential execution
        for manifest_id in manifest_ids:
            try:
                report = test_single_spider(manifest_id, test_type, True)
                results.append(report)
                
                if report["status"] == "pass":
                    passed += 1
                elif report["status"] == "fail":
                    failed += 1
                else:
                    errors += 1
                
                logger.info(f"  [{manifest_id}] {report['status']}")
                
            except Exception as e:
                logger.error(f"  [{manifest_id}] Error: {e}")
                errors += 1
    
    summary = {
        "total": len(manifest_ids),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "pass_rate": passed / len(manifest_ids) if manifest_ids else 0,
        "results": results,
        "tested_at": datetime.utcnow().isoformat(),
    }
    
    return summary


def get_test_summary() -> dict[str, Any]:
    """Get summary of all test results from database."""
    with get_session() as sess:
        total_tests = sess.query(SpiderTest).count()
        passed_tests = sess.query(SpiderTest).filter_by(status="passed").count()
        failed_tests = sess.query(SpiderTest).filter_by(status="failed").count()
        error_tests = sess.query(SpiderTest).filter_by(status="error").count()
        
        # Get recent test results
        recent_tests = (
            sess.query(SpiderTest)
            .order_by(SpiderTest.created_at.desc())
            .limit(20)
            .all()
        )
        
        return {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "errors": error_tests,
            "pass_rate": passed_tests / total_tests if total_tests > 0 else 0,
            "recent_tests": [
                {
                    "id": t.id,
                    "manifest_id": t.manifest_id,
                    "spider_path": t.spider_path,
                    "status": t.status,
                    "error": t.error_message,
                    "tested_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in recent_tests
            ],
        }


def format_test_report(report: dict[str, Any], verbose: bool = False) -> str:
    """Format a test report for human-readable output."""
    lines = []
    
    # Header
    status_icon = "✅" if report["status"] == "pass" else "❌"
    lines.append(f"{status_icon} Test {report['test_id']} - {report['status'].upper()}")
    lines.append(f"Reason: {report['reason']}")
    lines.append("")
    
    # Execution details
    execution = report.get("execution", {})
    lines.append("Execution:")
    lines.append(f"  Success: {execution.get('success', False)}")
    lines.append(f"  Duration: {execution.get('duration_seconds', 0):.3f}s")
    lines.append(f"  Records: {execution.get('records_fetched', 0)}")
    
    if execution.get("error"):
        lines.append(f"  Error: {execution['error']}")
    
    lines.append("")
    
    # Validation details
    validation = report.get("validation", {})
    lines.append("Validation:")
    lines.append(f"  Valid: {validation.get('is_valid', False)}")
    lines.append(f"  Failures: {validation.get('failure_count', 0)}")
    lines.append(f"  Warnings: {validation.get('warning_count', 0)}")
    
    if verbose and validation.get("failures"):
        lines.append("\n  Failure Details:")
        for i, failure in enumerate(validation["failures"][:10], 1):
            lines.append(f"    {i}. [{failure['path']}] {failure['message']}")
    
    # Recommendations
    recommendations = report.get("recommendations", [])
    if recommendations:
        lines.append("\nRecommendations:")
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"  {i}. {rec}")
    
    return "\n".join(lines)


async def test_single_spider_async(
    target: str | int,
    test_type: str = "full",
    store_results: bool = True,
) -> dict[str, Any]:
    """Async version of test_single_spider using async DB sessions."""
    from sqlalchemy import select
    from .db import get_async_session

    logger.info(f"Testing spider (async): {target} (type: {test_type})")

    if isinstance(target, int):
        load_result = load_spider_from_manifest(target)
    else:
        load_result = load_spider_from_file(target)

    if not load_result.success:
        logger.error(f"Failed to load spider: {load_result.error}")

        if store_results:
            async with get_async_session() as sess:
                test = SpiderTest(
                    manifest_id=target if isinstance(target, int) else None,
                    spider_path=load_result.spider_path,
                    test_type=test_type,
                    status="error",
                    error_message=load_result.error,
                    error_traceback=load_result.error_traceback,
                )
                sess.add(test)
                await sess.commit()
                await sess.refresh(test)

                return create_validation_report(
                    test_id=str(test.id),
                    validation_result=ValidationResult(is_valid=False, manifest_name="unknown"),
                    execution_success=False,
                    execution_error=load_result.error,
                )

        return {"status": "error", "error": load_result.error}

    validation_result = validate_manifest_yaml(
        load_result.manifest_yaml,
        load_result.manifest_name or "unknown",
    )

    execution_result = SpiderExecutionResult(success=True)

    if test_type in ["full", "mock_execution"]:
        if load_result.spider_path:
            if test_type == "syntax_only":
                execution_result = execute_spider_syntax_check(load_result.spider_path)
            else:
                execution_result = execute_spider_mock(load_result.spider_path)
        else:
            logger.warning("No spider.py file found, skipping execution")
    elif test_type == "syntax_only":
        if load_result.spider_path:
            execution_result = execute_spider_syntax_check(load_result.spider_path)

    test_id = f"test_{int(time.time())}"
    report = create_validation_report(
        test_id=test_id,
        validation_result=validation_result,
        execution_success=execution_result.success,
        execution_error=execution_result.error,
        records_fetched=execution_result.records_fetched,
        execution_time_seconds=execution_result.execution_time_seconds,
    )
    report["recommendations"] = generate_recommendations(report)

    if store_results:
        async with get_async_session() as sess:
            test = SpiderTest(
                manifest_id=target if isinstance(target, int) else None,
                spider_path=load_result.spider_path,
                test_type=test_type,
                status="passed" if report["status"] == "pass" else "failed",
                error_message=execution_result.error,
                error_traceback=execution_result.error_traceback,
            )
            sess.add(test)
            await sess.flush()

            result = TestResult(
                test_id=test.id,
                is_valid=1 if validation_result.is_valid else 0,
                validation_report=json.dumps(report["validation"]),
                failure_count=len(validation_result.failures),
                warning_count=len(validation_result.warnings),
            )
            sess.add(result)

            metrics = ExecutionMetrics(
                test_id=test.id,
                execution_time_seconds=execution_result.execution_time_seconds,
                records_fetched=execution_result.records_fetched,
            )
            sess.add(metrics)

            await sess.commit()
            report["test_id"] = str(test.id)

    return report


async def test_all_spiders_async(
    limit: Optional[int] = None,
    parallel: int = 1,
    test_type: str = "full",
) -> dict[str, Any]:
    """Async version of test_all_spiders using asyncio.gather + semaphore."""
    from sqlalchemy import select
    from .db import get_async_session

    logger.info(f"Testing all spiders (async, limit={limit}, parallel={parallel})")

    async with get_async_session() as sess:
        query = select(Manifest)
        if limit:
            query = query.limit(limit)
        result = await sess.execute(query)
        manifests = result.scalars().all()
        manifest_ids = [m.id for m in manifests]

    logger.info(f"Found {len(manifest_ids)} manifests to test")

    sem = asyncio.Semaphore(max(1, parallel))

    async def _run_one(mid: int) -> dict[str, Any]:
        async with sem:
            return await test_single_spider_async(mid, test_type, True)

    tasks = [_run_one(mid) for mid in manifest_ids]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    passed = 0
    failed = 0
    errors = 0

    for i, item in enumerate(completed):
        mid = manifest_ids[i]
        if isinstance(item, Exception):
            logger.error(f"  [{mid}] Error: {item}")
            errors += 1
            continue
        report = item
        results.append(report)
        if report["status"] == "pass":
            passed += 1
        elif report["status"] == "fail":
            failed += 1
        else:
            errors += 1
        logger.info(f"  [{mid}] {report['status']}")

    return {
        "total": len(manifest_ids),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "pass_rate": passed / len(manifest_ids) if manifest_ids else 0,
        "results": results,
        "tested_at": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)

    # Test a manifest
    print("Testing manifest 1...")
    report = test_single_spider(1, test_type="syntax_only")
    print(format_test_report(report, verbose=True))
