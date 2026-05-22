"""Strict validation for producer PcsBenchIngest.v0 payloads (pcs-core parity)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pcs_bench.report_export import PLACEHOLDER_COMMITS

KNOWN_PRODUCER_IDS = frozenset(
    {
        "certifyedge",
        "provability-fabric",
        "labtrust-gym",
        "scientific-memory",
        "pcs-core",
        "pcs-bench",
    }
)

_PRODUCER_ALIASES: dict[str, str] = {
    "certifyedge": "certifyedge",
    "provability-fabric": "provability-fabric",
    "provability_fabric": "provability-fabric",
    "pf": "provability-fabric",
    "scientific-memory": "scientific-memory",
    "scientific_memory": "scientific-memory",
    "scimem": "scientific-memory",
    "labtrust": "labtrust-gym",
    "labtrust-gym": "labtrust-gym",
}

INGEST_EMBEDDED_ARRAYS: dict[str, str] = {
    "BenchmarkRun.v0": "benchmark_runs",
    "CoverageReport.v0": "coverage_reports",
    "FailureLocalizationResult.v0": "failure_localization_reports",
    "ExplainQualityReport.v0": "explain_quality_reports",
    "ProfileCoverageReport.v0": "profile_coverage_reports",
}

# LabTrust reproducibility sidecars (provenance only; not embedded in PcsBenchIngest.v0).
LABTRUST_EXTENDED_ARTIFACT_TYPES = frozenset(
    {
        "BenchmarkReport.v0",
        "LabtrustBenchmarkRunSummary.v0",
        "LabtrustReproducibilityCoverage.v0",
        "ReproducibilityBenchmarkManifest.v0",
        "HashStabilityReport.v0",
        "RegenerationReport.v0",
        "PcsBenchIngest.v0",
    }
)
LABTRUST_EXTENDED_ARTIFACT_ROLES = frozenset(
    {
        "native_report",
        "reproducibility_evidence",
        "regeneration_report",
        "canonical_ingest",
    }
)

PRODUCER_EMBEDDED_REF_FIELDS: dict[str, tuple[str, ...]] = {
    "labtrust-gym": ("benchmark_runs",),
    "certifyedge": ("coverage_reports",),
    "provability-fabric": ("explain_quality_reports", "profile_coverage_reports"),
    "scientific-memory": ("explain_quality_reports",),
}

_REQUIRED_LIST_FIELDS = (
    "benchmark_runs",
    "coverage_reports",
    "failure_localization_reports",
    "explain_quality_reports",
    "profile_coverage_reports",
    "commands",
    "logs",
)

_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_ALL_ZERO_COMMIT_RE = re.compile(r"^0{40}$")

_RELEASE_PRODUCER_REQUIREMENTS: dict[str, dict[str, bool]] = {
    "labtrust-gym": {
        "benchmark_runs": True,
        "coverage_reports": False,
        "failure_localization_reports": False,
        "explain_quality_reports": False,
        "profile_coverage_reports": False,
    },
    "certifyedge": {
        "benchmark_runs": True,
        "coverage_reports": True,
        "failure_localization_reports": False,
        "explain_quality_reports": False,
        "profile_coverage_reports": True,
    },
    "provability-fabric": {
        "benchmark_runs": True,
        "coverage_reports": False,
        "failure_localization_reports": True,
        "explain_quality_reports": True,
        "profile_coverage_reports": False,
    },
    "scientific-memory": {
        "benchmark_runs": True,
        "coverage_reports": False,
        "failure_localization_reports": False,
        "explain_quality_reports": True,
        "profile_coverage_reports": False,
    },
}


def canonical_producer_id(producer: str) -> str:
    key = producer.lower().replace("_", "-")
    return _PRODUCER_ALIASES.get(key, key)


def load_ingest_document(input_path: Path) -> tuple[dict[str, Any], Path]:
    """Load pcs_bench_ingest.v0.json from a file or benchmark_runs directory."""
    resolved = input_path.resolve()
    if resolved.is_file():
        data = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Ingest document must be a JSON object")
        return data, resolved.parent

    if resolved.is_dir():
        for name in ("pcs_bench_ingest.v0.json", "PcsBenchIngest.v0.json"):
            candidate = resolved / name
            if candidate.is_file():
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Ingest document must be a JSON object")
                return data, resolved
        raise FileNotFoundError(f"No pcs_bench_ingest.v0.json found under {resolved}")

    raise FileNotFoundError(f"Ingest input not found: {resolved}")


def _embedded_objects(data: dict[str, Any], artifact_type: str) -> list[dict[str, Any]]:
    field = INGEST_EMBEDDED_ARRAYS.get(artifact_type)
    if not field:
        return []
    rows = data.get(field)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _is_labtrust_extended_artifact_ref(ref: dict[str, Any]) -> bool:
    atype = ref.get("artifact_type")
    if atype not in LABTRUST_EXTENDED_ARTIFACT_TYPES:
        return False
    role = ref.get("role")
    if role in LABTRUST_EXTENDED_ARTIFACT_ROLES:
        return True
    return atype in (
        "LabtrustReproducibilityCoverage.v0",
        "ReproducibilityBenchmarkManifest.v0",
    ) and role in ("producer_export", "ingest_bundle", "primary")


def _validate_artifact_ref_semantics(ref: dict[str, Any], index: int) -> list[str]:
    errors: list[str] = []
    artifact_type = ref.get("artifact_type")
    if artifact_type not in INGEST_EMBEDDED_ARRAYS and not _is_labtrust_extended_artifact_ref(ref):
        errors.append(f"artifact_refs[{index}]: unsupported artifact_type {artifact_type!r}")
    path = ref.get("path")
    if not isinstance(path, str) or not path.strip():
        errors.append(f"artifact_refs[{index}]: path must be non-empty")
    sha256 = ref.get("sha256")
    if isinstance(sha256, str) and not _DIGEST_RE.match(sha256):
        errors.append(f"artifact_refs[{index}]: sha256 must be sha256:<64 hex>")
    return errors


def validate_ingest_semantics(data: dict[str, Any]) -> list[str]:
    """pcs-core-aligned semantic checks for PcsBenchIngest.v0."""
    errors: list[str] = []

    if data.get("schema_version") != "v0":
        errors.append(f"schema_version must be 'v0', got {data.get('schema_version')!r}")

    producer_id = str(data.get("producer_id", ""))
    if producer_id not in KNOWN_PRODUCER_IDS:
        errors.append(f"Unknown producer_id: {producer_id!r}")

    commit = str(data.get("source_commit", ""))
    if commit in PLACEHOLDER_COMMITS or not _GIT_COMMIT_RE.match(commit):
        errors.append(f"source_commit must be 40-char lowercase hex, got {commit!r}")

    digest = str(data.get("signature_or_digest", ""))
    if not _DIGEST_RE.match(digest):
        errors.append("signature_or_digest must match sha256:<64 hex>")

    for field in _REQUIRED_LIST_FIELDS:
        if not isinstance(data.get(field), list):
            errors.append(f"PcsBenchIngest.v0 requires list {field}")

    producer_fields = PRODUCER_EMBEDDED_REF_FIELDS.get(producer_id, ())
    has_embedded = any(
        isinstance(data.get(field), list) and len(data.get(field)) > 0
        for field in producer_fields
    )
    refs = data.get("artifact_refs")
    if has_embedded and refs is None:
        errors.append(
            f"PcsBenchIngest.v0 producer {producer_id!r} requires artifact_refs "
            "when exporting embedded artifacts"
        )
        return errors

    if refs is None:
        return errors

    if not isinstance(refs, list):
        errors.append("PcsBenchIngest.v0 artifact_refs must be an array when present")
        return errors

    paths: list[str] = []
    ref_keys: set[tuple[str, str]] = set()
    for index, ref in enumerate(refs):
        if isinstance(ref, str):
            errors.append(
                f"artifact_refs[{index}] must be a BenchmarkArtifactRef object, not a path string"
            )
            continue
        if not isinstance(ref, dict):
            errors.append(f"artifact_refs[{index}] must be an object")
            continue
        errors.extend(_validate_artifact_ref_semantics(ref, index))
        artifact_type = str(ref.get("artifact_type", ""))
        sha256 = ref.get("sha256")
        path = ref.get("path")
        if isinstance(path, str):
            paths.append(path)
        if _is_labtrust_extended_artifact_ref(ref):
            if isinstance(sha256, str):
                ref_keys.add((artifact_type, sha256))
            continue
        embedded = _embedded_objects(data, artifact_type)
        if not embedded:
            errors.append(f"artifact_refs[{index}]: no embedded objects for {artifact_type!r}")
            continue
        if isinstance(sha256, str) and not any(
            row.get("signature_or_digest") == sha256 for row in embedded
        ):
            errors.append(
                f"artifact_refs[{index}]: sha256 does not match any embedded "
                f"{artifact_type} signature_or_digest"
            )
        elif isinstance(sha256, str):
            ref_keys.add((artifact_type, sha256))

    if len(paths) != len(set(paths)):
        errors.append("PcsBenchIngest.v0 artifact_refs contains duplicate path values")

    if has_embedded:
        for field in producer_fields:
            rows = data.get(field)
            if not isinstance(rows, list):
                continue
            artifact_type = next(
                (atype for atype, fname in INGEST_EMBEDDED_ARRAYS.items() if fname == field),
                None,
            )
            if not artifact_type:
                continue
            for row_index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                row_digest = row.get("signature_or_digest")
                if isinstance(row_digest, str) and (artifact_type, row_digest) not in ref_keys:
                    errors.append(
                        f"{field}[{row_index}]: missing artifact_refs entry for "
                        f"{artifact_type} digest {row_digest}"
                    )

    return errors


def _should_check_artifact_sidecars(search_roots: tuple[Path, ...]) -> bool:
    """Sidecars are enforced for producer repos, not embedded golden fixtures."""
    from pcs_bench.producer_fixtures import FIXTURE_ROOT

    fixture_root = FIXTURE_ROOT.resolve()
    for root in search_roots:
        if not root.is_dir():
            continue
        resolved = root.resolve()
        try:
            resolved.relative_to(fixture_root)
        except ValueError:
            return True
    return False


def _artifact_ref_sidecar_missing(
    ref: dict[str, Any],
    index: int,
    search_roots: tuple[Path, ...],
) -> str | None:
    path = ref.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    for root in search_roots:
        if not root.is_dir():
            continue
        if (root / path).is_file():
            return None
    return (
        f"artifact_refs[{index}]: sidecar file missing for path {path!r} "
        f"(searched under {', '.join(str(r) for r in search_roots)})"
    )


def validate_ingest_release_adequacy(
    data: dict[str, Any],
    *,
    search_roots: tuple[Path, ...] = (),
) -> list[str]:
    """Release-grade semantic adequacy beyond schema validity."""
    errors: list[str] = []
    producer_id = canonical_producer_id(str(data.get("producer_id", "")))
    requirements = _RELEASE_PRODUCER_REQUIREMENTS.get(producer_id, {})

    runs = data.get("benchmark_runs") or []
    coverage_rows = data.get("coverage_reports") or []
    profile_rows = data.get("profile_coverage_reports") or []
    coverage_only_ok = (
        producer_id == "certifyedge"
        and isinstance(coverage_rows, list)
        and len(coverage_rows) > 0
        and isinstance(profile_rows, list)
        and len(profile_rows) > 0
    )
    if requirements.get("benchmark_runs") and not runs and not coverage_only_ok:
        errors.append(f"release-grade: {producer_id} requires non-empty benchmark_runs")

    for field, required in requirements.items():
        if field == "benchmark_runs" or not required:
            continue
        rows = data.get(field)
        if not isinstance(rows, list) or len(rows) == 0:
            errors.append(f"release-grade: {producer_id} requires non-empty {field}")

    commit = str(data.get("source_commit", ""))
    if _ALL_ZERO_COMMIT_RE.match(commit):
        errors.append("release-grade: source_commit must not be all zeros")

    commands = data.get("commands")
    if not isinstance(commands, list) or len(commands) == 0:
        errors.append("release-grade: commands must be non-empty for live producer ingests")

    if isinstance(runs, list) and runs:
        all_weak = True
        for idx, run in enumerate(runs):
            if not isinstance(run, dict):
                continue
            kind = str(run.get("execution_kind", "live"))
            outcome = str(run.get("system_admission_outcome", ""))
            if kind == "simulate":
                errors.append(
                    f"benchmark_runs[{idx}]: execution_kind=simulate not allowed for release-grade"
                )
            if outcome not in ("", "not_evaluated"):
                all_weak = False
            elif outcome == "not_evaluated":
                pass
            else:
                all_weak = False
        if all_weak:
            errors.append(
                "release-grade: all benchmark_runs have system_admission_outcome=not_evaluated"
            )

    refs = data.get("artifact_refs")
    if isinstance(refs, list) and search_roots and _should_check_artifact_sidecars(search_roots):
        for index, ref in enumerate(refs):
            if not isinstance(ref, dict):
                continue
            artifact_type = str(ref.get("artifact_type", ""))
            if artifact_type not in INGEST_EMBEDDED_ARRAYS:
                continue
            missing = _artifact_ref_sidecar_missing(ref, index, search_roots)
            if missing:
                errors.append(f"release-grade: {missing}")

    return errors


def validate_ingest_developer_warnings(
    data: dict[str, Any],
    *,
    search_roots: tuple[Path, ...] = (),
) -> list[str]:
    """Same adequacy checks as release-grade, surfaced as warnings in developer mode."""
    return [f"warning: {msg}" for msg in validate_ingest_release_adequacy(data, search_roots=search_roots)]


def validate_ingest_via_pcs_cli(data_path: Path, pcs_core_repo: Path) -> list[str]:
    """Optional second opinion using pcs-core `pcs validate` when installed."""
    from pcs_bench.adapters.pcs_core import PcsCoreAdapter
    from pcs_bench.config import BenchConfig

    if not pcs_core_repo.is_dir():
        return []
    adapter = PcsCoreAdapter(pcs_core_repo, BenchConfig())
    from pcs_bench.adapters.base import AdapterStatus

    if adapter.run_smoke_check() != AdapterStatus.AVAILABLE:
        return []
    result = adapter.validate(data_path)
    if result.exit_code == 0:
        return []
    stderr = (result.stderr or result.stdout or "pcs validate failed").strip()
    return [f"pcs validate: {stderr[:500]}"]


def _pcs_core_ingest_body(data: dict[str, Any]) -> dict[str, Any]:
    """Ingest document with only pcs-core-compatible artifact_refs for schema validation."""
    refs = list(data.get("artifact_refs") or [])
    pcs_refs = [ref for ref in refs if isinstance(ref, dict) and not _is_labtrust_extended_artifact_ref(ref)]
    body = {k: v for k, v in data.items() if k != "artifact_refs"}
    if pcs_refs:
        body["artifact_refs"] = pcs_refs
    return body


def validate_ingest_data_strict(
    data: dict[str, Any],
    pcs_core_path: Path,
    *,
    ingest_file: Path | None = None,
    use_pcs_validate: bool = False,
    release_grade: bool = False,
    search_roots: tuple[Path, ...] = (),
) -> list[str]:
    """Validate ingest JSON against PcsBenchIngest.v0 and nested artifact schemas."""
    from pcs_bench.validation.schema_loader import validate_instance

    errors = validate_instance(_pcs_core_ingest_body(data), "PcsBenchIngest.v0", pcs_core_path)
    errors.extend(validate_ingest_semantics(data))
    if release_grade:
        errors.extend(validate_ingest_release_adequacy(data, search_roots=search_roots))

    for idx, run in enumerate(data.get("benchmark_runs") or []):
        if isinstance(run, dict):
            errors.extend(
                _prefix_errors(
                    validate_instance(run, "BenchmarkRun.v0", pcs_core_path),
                    f"benchmark_runs[{idx}]",
                )
            )

    for idx, report in enumerate(data.get("coverage_reports") or []):
        if isinstance(report, dict):
            errors.extend(
                _prefix_errors(
                    validate_instance(report, "CoverageReport.v0", pcs_core_path),
                    f"coverage_reports[{idx}]",
                )
            )

    for idx, report in enumerate(data.get("explain_quality_reports") or []):
        if isinstance(report, dict):
            errors.extend(
                _prefix_errors(
                    validate_instance(report, "ExplainQualityReport.v0", pcs_core_path),
                    f"explain_quality_reports[{idx}]",
                )
            )

    for idx, report in enumerate(data.get("profile_coverage_reports") or []):
        if isinstance(report, dict):
            errors.extend(
                _prefix_errors(
                    validate_instance(report, "ProfileCoverageReport.v0", pcs_core_path),
                    f"profile_coverage_reports[{idx}]",
                )
            )

    for idx, report in enumerate(data.get("failure_localization_reports") or []):
        if isinstance(report, dict):
            errors.extend(
                _prefix_errors(
                    validate_instance(report, "FailureLocalizationResult.v0", pcs_core_path),
                    f"failure_localization_reports[{idx}]",
                )
            )

    for idx, ref in enumerate(data.get("artifact_refs") or []):
        if isinstance(ref, dict) and not _is_labtrust_extended_artifact_ref(ref):
            errors.extend(
                _prefix_errors(
                    validate_instance(ref, "BenchmarkArtifactRef.v0", pcs_core_path),
                    f"artifact_refs[{idx}]",
                )
            )

    for idx, cmd in enumerate(data.get("commands") or []):
        if isinstance(cmd, dict):
            errors.extend(
                _prefix_errors(
                    validate_instance(cmd, "benchmark_command_entry", pcs_core_path),
                    f"commands[{idx}]",
                )
            )

    if use_pcs_validate and ingest_file and ingest_file.is_file():
        pcs_repo = pcs_core_path if (pcs_core_path / "python").is_dir() else pcs_core_path.parent
        errors.extend(validate_ingest_via_pcs_cli(ingest_file, pcs_repo))

    return errors


def validate_ingest_json(
    input_path: Path,
    pcs_core_path: Path,
    *,
    use_pcs_validate: bool = False,
    release_grade: bool = False,
    producer_repo: Path | None = None,
) -> list[str]:
    data, base = load_ingest_document(input_path)
    ingest_file = input_path if input_path.is_file() else base / "pcs_bench_ingest.v0.json"
    roots: list[Path] = []
    if producer_repo and producer_repo.is_dir():
        roots.append(producer_repo.resolve())
    roots.append(base.resolve())
    return validate_ingest_data_strict(
        data,
        pcs_core_path,
        ingest_file=ingest_file,
        use_pcs_validate=use_pcs_validate,
        release_grade=release_grade,
        search_roots=tuple(roots),
    )


def _prefix_errors(errors: list[str], prefix: str) -> list[str]:
    return [f"{prefix}: {err}" for err in errors]
