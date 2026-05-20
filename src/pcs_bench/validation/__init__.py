"""Benchmark case and report validation against pcs-core schemas."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pcs_bench.adapters.pcs_core import PcsCoreAdapter
from pcs_bench.benchmark_vocabulary import normalize_legacy_case_payload
from pcs_bench.cases import load_case
from pcs_bench.config import BenchConfig
from pcs_bench.report_export import PLACEHOLDER_COMMITS, validate_report_policy
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


_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


def validate_case_policy(data: dict) -> list[str]:
    errors: list[str] = []
    commit = data.get("source_commit", "")
    if commit in PLACEHOLDER_COMMITS or not _GIT_COMMIT_RE.match(str(commit)):
        errors.append(f"source_commit must be 40-char lowercase hex, got {commit!r}")

    digest = data.get("signature_or_digest", "")
    if not _DIGEST_RE.match(str(digest)):
        errors.append("signature_or_digest must match sha256:<64 hex>")

    artifacts = data.get("input_artifacts") or {}
    if not artifacts.get("release_directory") and not artifacts.get("case_manifest_path"):
        errors.append("input_artifacts requires release_directory or case_manifest_path")

    if "release_dir" in artifacts:
        errors.append("input_artifacts.release_dir is deprecated; use release_directory")

    if data.get("expected_status") in ("Admitted", "Accepted", "Rejected"):
        errors.append(
            "expected_status must be benchmark vocabulary (passed/failed/skipped/error), "
            "not system outcome (Admitted/Rejected)"
        )
    if "expected_system_outcome" not in data:
        errors.append("expected_system_outcome is required")

    return errors


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
        ("expected_system_outcome", case.expected_system_outcome),
    ]
    for name, value in required:
        if not value:
            errors.append(f"Missing required field: {name}")

    if case.schema_version != "v0":
        errors.append(f"Unsupported schema_version: {case.schema_version}")

    return errors


def _validate_with_jsonschema(case_path: Path, config: BenchConfig) -> list[str]:
    pcs_core = config.repos.pcs_core
    with case_path.open(encoding="utf-8") as f:
        data = normalize_legacy_case_payload(json.load(f))

    from pcs_bench.validation.schema_loader import validate_instance

    return validate_instance(data, "BenchmarkCase.v0", pcs_core)


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
        with case_path.open(encoding="utf-8") as f:
            raw = normalize_legacy_case_payload(json.load(f))
        errors = validate_case_structure(case_path)
        errors.extend(validate_case_policy(raw))
        errors.extend(_validate_with_jsonschema(case_path, config))
        pcs_exit: int | None = None

        if use_pcs_validate and not dry_run and not errors:
            result = pcs.validate(case_path)
            pcs_exit = result.exit_code
            if result.exit_code != 0:
                errors.append(f"pcs validate failed (exit {result.exit_code}): {result.stderr[:500]}")

        case = load_case(case_path)
        for key in ("release_directory", "release_dir"):
            rel = case.input_artifacts.get(key)
            if rel:
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


def validate_report_data_strict(data: dict, pcs_core_path: Path) -> list[str]:
    from pcs_bench.validation.schema_loader import validate_instance

    errors = validate_instance(data, "BenchmarkReport.v0", pcs_core_path)
    errors.extend(validate_report_policy(data))
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
    runs_dir = report_path.parent / f"{report_path.stem}-runs"
    data = to_benchmark_report_v0_dict(report, runs_output_dir=runs_dir)
    pcs_core = schema_source or config.repos.pcs_core
    return validate_report_data_strict(data, pcs_core)
