"""Benchmark case validation against pcs-core schemas."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pcs_bench.adapters.pcs_core import PcsCoreAdapter
from pcs_bench.cases import load_case
from pcs_bench.config import BenchConfig
from pcs_bench.suites import load_suite, load_suite_cases


@dataclass
class ValidationResult:
    case_id: str
    path: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    pcs_validate_exit_code: int | None = None


@dataclass
class SuiteValidationReport:
    suite_id: str
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def all_valid(self) -> bool:
        return all(r.valid for r in self.results)


def validate_case_structure(case_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        case = load_case(case_path)
    except Exception as exc:
        return [str(exc)]

    required = [
        ("schema_version", case.schema_version),
        ("case_id", case.case_id),
        ("task_id", case.task_id),
        ("workflow_id", case.workflow_id),
        ("expected_status", case.expected_status),
    ]
    for name, value in required:
        if not value:
            errors.append(f"Missing required field: {name}")

    if case.schema_version != "v0":
        errors.append(f"Unsupported schema_version: {case.schema_version}")

    return errors


def _validate_with_jsonschema(case_path: Path, config: BenchConfig) -> list[str]:
    try:
        import jsonschema
    except ImportError:
        return []

    schema = try_load_json_schema(config.repos.pcs_core, "BenchmarkCase.v0")
    if not schema:
        return []
    with case_path.open(encoding="utf-8") as f:
        data = json.load(f)
    try:
        jsonschema.validate(instance=data, schema=schema)
        return []
    except jsonschema.ValidationError as exc:
        return [f"jsonschema: {exc.message}"]


def validate_cases_for_suite(
    config: BenchConfig,
    suite_dir: Path,
    *,
    use_pcs_validate: bool = True,
    dry_run: bool = False,
) -> SuiteValidationReport:
    suite = load_suite(suite_dir)
    report = SuiteValidationReport(suite_id=suite.suite_id)
    pcs = PcsCoreAdapter(config.repos.pcs_core, config)

    for case_id, case_path, _case in load_suite_cases(suite_dir, suite):
        errors = validate_case_structure(case_path)
        errors.extend(_validate_with_jsonschema(case_path, config))
        pcs_exit: int | None = None

        if use_pcs_validate and not dry_run and not errors:
            result = pcs.validate(case_path)
            pcs_exit = result.exit_code
            if result.exit_code != 0:
                errors.append(f"pcs validate failed (exit {result.exit_code}): {result.stderr[:500]}")

        # Validate input artifact paths exist (relative to case directory)
        case = load_case(case_path)
        for _key, rel in case.input_artifacts.items():
            artifact_path = (case_path.parent / rel).resolve()
            if not artifact_path.exists():
                errors.append(f"Missing input artifact path: {artifact_path}")

        report.results.append(
            ValidationResult(
                case_id=case_id,
                path=str(case_path),
                valid=len(errors) == 0,
                errors=errors,
                pcs_validate_exit_code=pcs_exit,
            )
        )

    return report


def _embedded_schema_path(schema_name: str) -> Path:
    return Path(__file__).resolve().parent / "schemas" / "json" / f"{schema_name}.json"


def try_load_json_schema(pcs_core_path: Path, schema_name: str) -> dict | None:
    candidates = [
        pcs_core_path / "schemas" / f"{schema_name}.json",
        pcs_core_path / "schema" / f"{schema_name}.json",
        _embedded_schema_path(schema_name),
    ]
    for path in candidates:
        if path.exists():
            with path.open(encoding="utf-8") as f:
                return json.load(f)
    return None


def validate_report_data_strict(data: dict, pcs_core_path: Path) -> list[str]:
    """Validate report dict against BenchmarkReport.v0 (embedded or pcs-core)."""
    errors: list[str] = []
    for field in (
        "schema_version",
        "report_id",
        "benchmark_suite_id",
        "runs",
        "metrics",
        "summary",
        "coverage",
        "failures",
        "source_repo",
        "source_commit",
        "signature_or_digest",
    ):
        if field not in data or data[field] in (None, ""):
            errors.append(f"Missing required field: {field}")

    digest = data.get("signature_or_digest")
    if digest and not str(digest).startswith("sha256:"):
        errors.append("signature_or_digest must be sha256:<hex>")

    metrics = data.get("metrics")
    if metrics is not None and not isinstance(metrics, dict):
        errors.append("metrics must be an object")

    schema = try_load_json_schema(pcs_core_path, "BenchmarkReport.v0")
    if schema:
        try:
            import jsonschema
        except ImportError:
            errors.append("jsonschema package required for strict report validation")
            return errors
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as exc:
            errors.append(f"jsonschema: {exc.message}")
    return errors


def validate_report_json(
    report_path: Path,
    config: BenchConfig,
    *,
    schema_source: Path | None = None,
) -> list[str]:
    from pcs_bench.report_export import to_benchmark_report_v0_dict
    from pcs_bench.reports import load_report

    report = load_report(report_path)
    data = to_benchmark_report_v0_dict(report)
    pcs_core = schema_source or config.repos.pcs_core
    return validate_report_data_strict(data, pcs_core)
