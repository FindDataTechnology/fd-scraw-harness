"""Schema validation for spider output against fd-open-data-protocol."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from pydantic import ValidationError

from fd_open_data_protocol.schema import (
    ColumnSpec,
    ConceptHint,
    DatasourceManifest,
    FetchRef,
    FunctionSpec,
    ParamSpec,
)


@dataclass
class ValidationFailure:
    """Represents a single validation failure."""
    path: str  # e.g., "functions[0].columns[1].name"
    message: str  # Human-readable error
    expected: Optional[str] = None  # Expected value/type
    actual: Optional[Any] = None  # Actual value/type
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "message": self.message,
            "expected": self.expected,
            "actual": str(self.actual) if self.actual is not None else None,
        }


@dataclass
class ValidationResult:
    """Complete validation result with metadata."""
    is_valid: bool
    manifest_name: str
    failures: list[ValidationFailure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validated_at: datetime = field(default_factory=datetime.utcnow)
    
    def add_failure(self, path: str, message: str, 
                    expected: Optional[str] = None, 
                    actual: Optional[Any] = None):
        self.failures.append(ValidationFailure(path, message, expected, actual))
        self.is_valid = False
    
    def add_warning(self, message: str):
        self.warnings.append(message)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "manifest_name": self.manifest_name,
            "validation_timestamp": self.validated_at.isoformat(),
            "failure_count": len(self.failures),
            "warning_count": len(self.warnings),
            "failures": [f.to_dict() for f in self.failures],
            "warnings": self.warnings,
        }
    
    def summary(self) -> str:
        """Human-readable summary."""
        status = "✅ VALID" if self.is_valid else "❌ INVALID"
        lines = [
            f"{status} - Manifest: {self.manifest_name}",
            f"Validated: {self.validated_at.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        
        if self.failures:
            lines.append(f"\nFailures ({len(self.failures)}):")
            for i, f in enumerate(self.failures[:10], 1):  # Show first 10
                lines.append(f"  {i}. [{f.path}] {f.message}")
                if f.expected and f.actual:
                    lines.append(f"      Expected: {f.expected}, Got: {f.actual}")
            if len(self.failures) > 10:
                lines.append(f"  ... and {len(self.failures) - 10} more")
        
        if self.warnings:
            lines.append(f"\nWarnings ({len(self.warnings)}):")
            for w in self.warnings[:5]:
                lines.append(f"  • {w}")
            if len(self.warnings) > 5:
                lines.append(f"  ... and {len(self.warnings) - 5} more")
        
        return "\n".join(lines)


def validate_manifest_yaml(yaml_content: str, manifest_name: str = "unknown") -> ValidationResult:
    """Validate a DatasourceManifest from YAML string."""
    result = ValidationResult(is_valid=True, manifest_name=manifest_name)
    
    try:
        import yaml
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        result.add_failure("yaml", f"Invalid YAML syntax: {e}")
        return result
    
    if not isinstance(data, dict):
        result.add_failure("root", "Root must be a mapping/object", actual=type(data).__name__)
        return result
    
    # Validate using Pydantic model (deep validation)
    try:
        manifest = DatasourceManifest.model_validate(data)
        
        # Additional custom validations
        _validate_manifest_structure(manifest, result)
        
    except ValidationError as e:
        _process_pydantic_errors(e, result)
    
    return result


def validate_fetch_reference(fetch: Optional[FetchRef], result: ValidationResult):
    """Validate fetch reference configuration."""
    if fetch is None:
        result.add_warning("No fetch reference defined - no execution method specified")
        return
    
    if not fetch.module and not fetch.runner:
        result.add_failure(
            "fetch",
            "Must specify either 'module' or 'runner'",
            expected="module=<path> or runner=<builtin>"
        )
    
    if fetch.module and ":" not in fetch.module:
        result.add_warning(
            f"fetch.module '{fetch.module}' may need format 'package.module:func'"
        )


def _validate_manifest_structure(manifest: DatasourceManifest, result: ValidationResult):
    """Additional structural validations beyond Pydantic."""
    
    # Check for at least one function
    if not manifest.functions:
        result.add_failure(
            "functions",
            "At least one function must be defined",
            expected="non-empty list"
        )
    
    # Validate each function
    for i, func in enumerate(manifest.functions):
        func_path = f"functions[{i}]"
        
        # Required fields
        if not func.command:
            result.add_failure(f"{func_path}.command", "Command is required")
        
        # Check columns match parameters or have names
        if func.columns:
            column_names = [c.name for c in func.columns]
            if len(column_names) != len(set(column_names)):
                result.add_warning(f"{func_path} has duplicate column names")
        
        # Validate frequency consistency
        if func.frequency:
            valid_frequencies = ["realtime", "daily", "weekly", "monthly", "quarterly", "yearly"]
            if func.frequency.lower() not in valid_frequencies:
                result.add_warning(
                    f"{func_path}.frequency '{func.frequency}' should be one of: {', '.join(valid_frequencies)}"
                )
        
        # Validate concept hints reference existing columns
        for j, concept in enumerate(manifest.concepts):
            concept_path = f"concepts[{j}]"
            
            # Check if column exists in any function
            column_exists = False
            for func in manifest.functions:
                if any(col.name == concept.column for col in func.columns):
                    column_exists = True
                    break
            
            if not column_exists:
                result.add_warning(
                    f"{concept_path}.column '{concept.column}' not found in any function's columns"
                )
    
    # Validate fetch reference
    validate_fetch_reference(manifest.fetch, result)


def _process_pydantic_errors(error: ValidationError, result: ValidationResult):
    """Convert Pydantic validation errors to ValidationResult failures."""
    for err in error.errors():
        path = ".".join(str(p) for p in err["loc"])
        message = err["msg"]
        input_value = err.get("input")
        
        result.add_failure(
            path=path,
            message=message,
            expected=err.get("type"),
            actual=str(input_value)[:100] if input_value else None
        )


def validate_sample_data(data: list[dict], 
                         manifest: DatasourceManifest,
                         sample_size: int = 10) -> ValidationResult:
    """
    Validate sample scraped data against manifest schema.
    
    This checks if actual crawled data conforms to the declared column structure.
    """
    result = ValidationResult(
        is_valid=True,
        manifest_name=manifest.name
    )
    
    if not data:
        result.add_warning("No sample data provided for validation")
        return result
    
    # Limit to sample_size
    sample = data[:sample_size]
    
    # Find functions that might produce this data
    all_columns = {}
    for func in manifest.functions:
        for col in func.columns:
            all_columns[col.name] = {
                "type": col.type,
                "description": col.description,
                "function": func.command,
            }
    
    # Check first record for required fields
    if sample:
        first_record = sample[0]
        missing_fields = set(all_columns.keys()) - set(first_record.keys())
        
        if missing_fields:
            result.add_failure(
                "sample_data",
                f"Sample data missing expected columns: {', '.join(sorted(missing_fields))}",
                expected=f"all declared columns from manifest",
                actual=", ".join(sorted(missing_fields))
            )
    
    # Type validation (basic)
    for i, record in enumerate(sample[:3]):  # Check first 3 records
        for col_name, col_info in all_columns.items():
            if col_name not in record:
                continue
            
            value = record[col_name]
            expected_type = col_info["type"]
            
            if expected_type:
                type_valid = _check_type(value, expected_type)
                if not type_valid:
                    result.add_failure(
                        f"data.records[{i}].{col_name}",
                        f"Type mismatch: expected {expected_type}, got {type(value).__name__}",
                        expected=expected_type,
                        actual=f"{value!r}"
                    )
    
    # Check for null values in potentially required fields
    for col_name in all_columns:
        null_count = sum(1 for r in sample if r.get(col_name) is None)
        null_ratio = null_count / len(sample)
        
        if null_ratio > 0.5:  # More than 50% nulls is suspicious
            result.add_warning(
                f"Column '{col_name}' has {null_count}/{len(sample)} null values ({null_ratio:.1%})"
            )
    
    return result


def _check_type(value: Any, expected_type: str) -> bool:
    """Basic type checking for common types."""
    type_map = {
        "string": str,
        "str": str,
        "int": int,
        "integer": int,
        "float": float,
        "number": (int, float),
        "bool": bool,
        "boolean": bool,
        "list": list,
        "array": list,
        "dict": dict,
        "object": dict,
        "null": type(None),
        "none": type(None),
    }
    
    python_type = type_map.get(expected_type.lower())
    if python_type is None:
        # Unknown type, skip validation
        return True
    
    return isinstance(value, python_type)


def create_validation_report(test_id: str,
                             validation_result: ValidationResult,
                             execution_success: bool = True,
                             execution_error: Optional[str] = None,
                             records_fetched: int = 0,
                             execution_time_seconds: float = 0.0) -> dict[str, Any]:
    """Create a comprehensive test report combining execution and validation."""
    
    overall_status = "pass"
    if not execution_success:
        overall_status = "fail"
        reason = f"Execution failed: {execution_error}" if execution_error else "Execution failed"
    elif not validation_result.is_valid:
        overall_status = "fail"
        reason = f"Schema validation failed with {len(validation_result.failures)} errors"
    else:
        reason = "All checks passed"
    
    report = {
        "test_id": test_id,
        "status": overall_status,
        "reason": reason,
        "execution": {
            "success": execution_success,
            "error": execution_error,
            "records_fetched": records_fetched,
            "duration_seconds": round(execution_time_seconds, 3),
        },
        "validation": validation_result.to_dict(),
        "generated_at": datetime.utcnow().isoformat(),
    }
    
    return report


def generate_recommendations(report: dict[str, Any]) -> list[str]:
    """Generate actionable recommendations based on test results."""
    recommendations = []
    
    execution = report.get("execution", {})
    validation = report.get("validation", {})
    
    # Execution-based recommendations
    if not execution.get("success"):
        error = execution.get("error", "")
        if "import" in error.lower():
            recommendations.append(
                "Missing dependencies: Verify all imports are available and packages are installed."
            )
        elif "syntax" in error.lower():
            recommendations.append(
                "Spider code has syntax errors: Review Python syntax and indentation."
            )
        elif "scrapy" in error.lower() and "not defined" in error.lower():
            recommendations.append(
                "Scrapy component issues: Verify Scrapy installation and Spider class inheritance."
            )
        else:
            recommendations.append(
                f"Fix execution errors: {error[:200]}"
            )
    
    # Validation-based recommendations
    failures = validation.get("failures", [])
    if failures:
        missing_commands = [
            f for f in failures 
            if "command" in f.get("path", "") and "required" in f.get("message", "").lower()
        ]
        if missing_commands:
            recommendations.append(
                "Add function commands: Each function must have a 'command' field defining how to fetch data."
            )
        
        missing_columns = [
            f for f in failures
            if "columns" in f.get("path", "") and "name" in f.get("path", "")
        ]
        if missing_columns:
            recommendations.append(
                "Define output columns: Specify 'columns' array with 'name' for each output field."
            )
        
        missing_manifest_fields = [
            f for f in failures
            if f.get("path") in ["name", "label", "version"]
        ]
        if missing_manifest_fields:
            recommendations.append(
                "Complete manifest metadata: Ensure 'name', 'label', and 'version' are defined."
            )
    
    # Warning-based recommendations
    warnings = validation.get("warnings", [])
    high_null_columns = [
        w for w in warnings 
        if "null values" in w.lower()
    ]
    if high_null_columns:
        recommendations.append(
            "Investigate empty fields: High null ratios may indicate data extraction issues."
        )
    
    no_fetch_ref = [
        w for w in warnings
        if "fetch" in w.lower() and "reference" in w.lower()
    ]
    if no_fetch_ref:
        recommendations.append(
            "Specify fetch method: Add 'fetch' section with module path or runner name."
        )
    
    # Success recommendations
    if report["status"] == "pass":
        if execution.get("records_fetched", 0) == 0:
            recommendations.append(
                "Spider executed but fetched no records: Verify URL and selectors are correct."
            )
        else:
            recommendations.append(
                f"✓ Spider successfully fetched {execution['records_fetched']} records"
            )
    
    return recommendations


if __name__ == "__main__":
    # Quick test
    test_yaml = """
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
    
    result = validate_manifest_yaml(test_yaml, "test")
    print(result.summary())
