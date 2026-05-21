"""PCS benchmark vs system outcome vocabulary (aligned with pcs-core schemas)."""

from __future__ import annotations

# Harness benchmark result (BenchmarkCase.expected_status / BenchmarkRun observed benchmark)
BENCHMARK_PASSED = "passed"
BENCHMARK_FAILED = "failed"
BENCHMARK_SKIPPED = "skipped"
BENCHMARK_ERROR = "error"

# PCS system admission outcome (expected_system_outcome / sidecar verification)
SYSTEM_ADMITTED = "admitted"
SYSTEM_REJECTED = "rejected"
SYSTEM_STALE = "stale"
SYSTEM_IMPORT_FAILED = "import_failed"
SYSTEM_RENDER_FAILED = "render_failed"
SYSTEM_FORMAL_FAILED = "formal_failed"

LEGACY_ADMITTED = frozenset({"Admitted", "Accepted"})
LEGACY_REJECTED = frozenset({"Rejected"})

VALID_CASE_KINDS = frozenset(
    {
        "valid_release",
        "invalid_hash_mismatch",
        "invalid_certificate",
        "invalid_handoff",
        "invalid_registry",
        "invalid_formal_check",
        "invalid_import",
        "invalid_render",
        "stale_release",
    }
)

ALLOWED_INPUT_ARTIFACT_KEYS = frozenset(
    {
        "release_directory",
        "case_manifest_path",
        "artifacts",
        "conformance_suite",
    }
)

KNOWN_METRIC_IDS = frozenset(
    {
        "release_reproducibility_score",
        "failure_localization_accuracy",
        "certificate_completeness_score",
        "registry_coverage_score",
        "formal_check_coverage_score",
        "scientific_memory_interpretability_score",
        "repair_hint_quality_score",
        "cross_domain_portability_score",
    }
)

CASE_KIND_BY_KEY: dict[str, str] = {
    "valid": "valid_release",
    "valid_release": "valid_release",
    "valid_tool_use": "valid_release",
    "valid_computation": "valid_release",
    "valid_render": "valid_release",
    "policy_hash_mismatch": "invalid_hash_mismatch",
    "tool_trace_hash_mismatch": "invalid_hash_mismatch",
    "dataset_hash_mismatch": "invalid_hash_mismatch",
    "environment_digest_mismatch": "invalid_hash_mismatch",
    "result_hash_mismatch": "invalid_hash_mismatch",
    "trace_hash_tamper": "invalid_hash_mismatch",
    "certificate_id_tamper": "invalid_certificate",
    "rejected_tool_certificate": "invalid_certificate",
    "rejected_computation_witness": "invalid_certificate",
    "missing_tool_use_certificate": "invalid_certificate",
    "missing_handoff": "invalid_handoff",
    "legacy_handoff": "invalid_handoff",
    "missing_policy_hash": "invalid_certificate",
    "wrong_admission_profile": "invalid_registry",
    "missing_qc_result": "invalid_registry",
    "unauthorized_release": "invalid_registry",
    "unauthorized_tool_call": "invalid_registry",
    "unknown_authorization_status": "invalid_registry",
    "placeholder_commit": "invalid_hash_mismatch",
    "missing_code_commit": "invalid_hash_mismatch",
    "missing_result_artifact": "invalid_registry",
    "nonzero_exit_code": "invalid_registry",
    "lean_trust_kernel_failure": "invalid_formal_check",
    "missing_lean_check_result": "invalid_formal_check",
    "lean_unauthorized": "invalid_formal_check",
    "missing_formal_section": "invalid_render",
    "missing_formal_trust_kernel_section": "invalid_render",
    "missing_registry_section": "invalid_render",
    "missing_lineage_section": "invalid_render",
    "missing_staleness_section": "invalid_render",
    "failed_rendering": "invalid_render",
    "release_comparison_changed_certificate": "invalid_render",
    "release_comparison_changed_dataset": "invalid_render",
    "stale_trace": "stale_release",
    "stale_trace_after_certificate": "stale_release",
}

REPAIR_HINT_MAP: dict[str, str] = {
    "regenerate_trace_or_certificate": "align_hash",
    "regenerate_certificate": "align_certificate_id",
    "regenerate_tool_trace": "align_hash",
    "upgrade_handoff_manifest": "align_handoff",
    "pin_source_commit": "align_provenance",
    "complete_qc_before_release": "rerun_verification",
    "obtain_release_authorization": "rerun_verification",
    "obtain_tool_authorization": "rerun_verification",
    "attach_policy_hash": "align_hash",
    "resolve_authorization_status": "rerun_verification",
    "select_correct_admission_profile": "fix_registry_entry",
    "issue_tool_use_certificate": "align_certificate_id",
    "provide_handoff_manifest": "align_handoff",
    "pin_dataset_version": "align_provenance",
    "record_environment_digest": "align_provenance",
    "recompute_and_witness": "rerun_verification",
    "fix_computation_script": "rerun_verification",
    "emit_result_artifact": "rerun_verification",
    "run_lean_check": "rerun_formal_check",
    "fix_proof_obligation": "rerun_formal_check",
    "authorize_theorem_in_kernel": "rerun_formal_check",
    "none": "none",
    "unknown": "unknown",
}

RESPONSIBLE_COMPONENT_MAP: dict[str, str] = {
    "provability_fabric": "verifier",
    "pf": "verifier",
    "formal_kernel": "formal_kernel",
    "scientific_memory": "scientific_memory",
    "runtime_producer": "runtime_producer",
    "certificate_producer": "certificate_producer",
    "verifier": "verifier",
    "handoff": "handoff",
    "registry": "registry",
    "unknown": "unknown",
}


def normalize_legacy_case_payload(data: dict) -> dict:
    """Map legacy Admitted/Rejected fixtures to pcs-core benchmark + system fields."""
    out = dict(data)
    if "release_dir" in out.get("input_artifacts", {}):
        out["input_artifacts"] = {
            "release_directory": out["input_artifacts"]["release_dir"],
        }
    status = out.get("expected_status")
    if status in LEGACY_ADMITTED:
        out["expected_status"] = BENCHMARK_PASSED
        out.setdefault("expected_system_outcome", SYSTEM_ADMITTED)
        out.setdefault("expected_failure_code", "")
        out.setdefault("expected_responsible_component", "unknown")
        out.setdefault("expected_repair_hint_kind", "none")
    elif status in LEGACY_REJECTED:
        out["expected_status"] = BENCHMARK_FAILED
        out.setdefault("expected_system_outcome", SYSTEM_REJECTED)
    if out.get("expected_failure_code") is None:
        out["expected_failure_code"] = ""
    if out.get("expected_responsible_component") is None:
        out["expected_responsible_component"] = "unknown"
    if out.get("expected_repair_hint_kind") is None:
        out["expected_repair_hint_kind"] = "unknown"
    kind = out.get("case_kind", "")
    if kind not in {
        "valid_release",
        "invalid_hash_mismatch",
        "invalid_certificate",
        "invalid_handoff",
        "invalid_registry",
        "invalid_formal_check",
        "invalid_import",
        "invalid_render",
        "stale_release",
    }:
        out["case_kind"] = CASE_KIND_BY_KEY.get(kind, "invalid_registry")
    comp = out.get("expected_responsible_component")
    if comp:
        out["expected_responsible_component"] = RESPONSIBLE_COMPONENT_MAP.get(comp, comp)
    rh = out.get("expected_repair_hint_kind")
    if rh:
        out["expected_repair_hint_kind"] = REPAIR_HINT_MAP.get(rh, rh)
    return out


def is_benchmark_pass_expected(expected_status: str) -> bool:
    return expected_status in (BENCHMARK_PASSED, *LEGACY_ADMITTED)


def is_system_rejection_expected(expected_system_outcome: str | None) -> bool:
    return expected_system_outcome in (
        SYSTEM_REJECTED,
        SYSTEM_STALE,
        SYSTEM_IMPORT_FAILED,
        SYSTEM_RENDER_FAILED,
        SYSTEM_FORMAL_FAILED,
    )


def is_valid_release_case(expected_status: str, expected_system_outcome: str | None) -> bool:
    return is_benchmark_pass_expected(expected_status) or expected_system_outcome == SYSTEM_ADMITTED


def is_invalid_release_case(expected_status: str, expected_system_outcome: str | None) -> bool:
    return expected_status == BENCHMARK_FAILED or is_system_rejection_expected(expected_system_outcome)


def system_outcome_from_sidecar(verification: dict) -> str:
    status = verification.get("status") or verification.get("admission_status") or ""
    if status in LEGACY_ADMITTED:
        return SYSTEM_ADMITTED
    if status in LEGACY_REJECTED:
        return SYSTEM_REJECTED
    code = (verification.get("failure_code") or "").lower()
    if "stale" in code:
        return SYSTEM_STALE
    if "import" in code:
        return SYSTEM_IMPORT_FAILED
    if "render" in code:
        return SYSTEM_RENDER_FAILED
    if "lean" in code or "formal" in code or "theorem" in code:
        return SYSTEM_FORMAL_FAILED
    return SYSTEM_REJECTED


def benchmark_status_for_run(passed: bool, *, error: bool = False) -> str:
    if error:
        return BENCHMARK_ERROR
    return BENCHMARK_PASSED if passed else BENCHMARK_FAILED
