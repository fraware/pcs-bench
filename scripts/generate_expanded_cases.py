#!/usr/bin/env python3
"""Generate expanded tool-use, computation, and scientific-memory benchmark cases."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_TOOL = "agent_tool_use.safety_v0"
WORKFLOW_COMP = "scientific_computation.reproducibility_v0"
WORKFLOW_MEMORY = "pcs.scientific_memory"

DIGEST_PLACEHOLDER = "sha256:0000000000000000000000000000000000000000000000000000000000000001"


def write_case_json(
    case_dir: Path,
    *,
    case_id: str,
    task_id: str,
    workflow_id: str,
    case_kind: str,
    expected_status: str,
    expected_failure_code: str | None = None,
    expected_responsible_component: str | None = None,
    expected_repair_hint_kind: str | None = None,
) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "v0",
        "case_id": case_id,
        "task_id": task_id,
        "workflow_id": workflow_id,
        "case_kind": case_kind,
        "input_artifacts": {"release_dir": "input_artifacts/"},
        "expected_status": expected_status,
        "expected_failure_code": expected_failure_code,
        "expected_responsible_component": expected_responsible_component,
        "expected_repair_hint_kind": expected_repair_hint_kind,
        "source_repo": "https://github.com/fraware/pcs-bench",
        "source_commit": "placeholder",
        "signature_or_digest": DIGEST_PLACEHOLDER,
    }
    (case_dir / "benchmark_case.v0.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def generate_tool_use_cases(
    write_bundle,
    write_expected,
    sections_full: list[str],
) -> list[tuple[str, str]]:
    """Returns (relative_path, case_id) for suite.yaml."""
    tool = ROOT / "benchmarks" / "tool_use_safety"
    specs = [
        ("valid/tool-use-valid-v0", "tool-use-valid-v0", "valid_tool_use", "Admitted", None),
        (
            "invalid/unauthorized_tool_call",
            "tool-use-unauthorized-tool-call-v0",
            "unauthorized_tool_call",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "unauthorized_tool_call",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "obtain_tool_authorization",
            },
        ),
        (
            "invalid/missing_policy_hash",
            "tool-use-missing-policy-hash-v0",
            "missing_policy_hash",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_policy_hash",
                "responsible_component": "certificate_producer",
                "repair_hint_kind": "attach_policy_hash",
            },
        ),
        (
            "invalid/unknown_authorization_status",
            "tool-use-unknown-authorization-status-v0",
            "unknown_authorization_status",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "unknown_authorization_status",
                "responsible_component": "verifier",
                "repair_hint_kind": "resolve_authorization_status",
            },
        ),
        (
            "invalid/policy_hash_mismatch",
            "tool-use-policy-hash-mismatch-v0",
            "policy_hash_mismatch",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "policy_hash_mismatch",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "regenerate_tool_trace",
            },
        ),
        (
            "invalid/tool_trace_hash_mismatch",
            "tool-use-tool-trace-hash-mismatch-v0",
            "tool_trace_hash_mismatch",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "tool_trace_hash_mismatch",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "regenerate_tool_trace",
            },
        ),
        (
            "invalid/rejected_tool_certificate",
            "tool-use-rejected-tool-certificate-v0",
            "rejected_tool_certificate",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "rejected_tool_certificate",
                "responsible_component": "certificate_producer",
                "repair_hint_kind": "regenerate_certificate",
            },
        ),
        (
            "invalid/wrong_admission_profile",
            "tool-use-wrong-admission-profile-v0",
            "wrong_admission_profile",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "wrong_admission_profile",
                "responsible_component": "provability_fabric",
                "repair_hint_kind": "select_correct_admission_profile",
            },
        ),
        (
            "invalid/missing_tool_use_certificate",
            "tool-use-missing-tool-use-certificate-v0",
            "missing_tool_use_certificate",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_tool_use_certificate",
                "responsible_component": "certificate_producer",
                "repair_hint_kind": "issue_tool_use_certificate",
            },
        ),
        (
            "invalid/missing_handoff",
            "tool-use-missing-handoff-v0",
            "missing_handoff",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_handoff",
                "responsible_component": "handoff",
                "repair_hint_kind": "provide_handoff_manifest",
            },
        ),
    ]
    refs: list[tuple[str, str]] = []
    for rel, case_id, kind, status, verification in specs:
        case_dir = tool / rel
        write_case_json(
            case_dir,
            case_id=case_id,
            task_id=f"{case_id}-task",
            workflow_id=WORKFLOW_TOOL,
            case_kind=kind,
            expected_status=status,
            expected_failure_code=verification["failure_code"] if verification else None,
            expected_responsible_component=verification["responsible_component"] if verification else None,
            expected_repair_hint_kind=verification.get("repair_hint_kind") if verification else None,
        )
        write_bundle(
            case_dir / "input_artifacts",
            release_id=case_id,
            workflow_id=WORKFLOW_TOOL,
            status=status,
            cert_status="Valid" if status == "Admitted" else "Rejected",
        )
        if verification:
            write_expected(case_dir, verification)
        else:
            write_expected(case_dir, {"status": "Admitted"}, sections_full)
        refs.append((f"{rel}/benchmark_case.v0.json", case_id))
    return refs


def generate_computation_cases(write_bundle, write_expected, sections_full: list[str]) -> list[tuple[str, str]]:
    comp = ROOT / "benchmarks" / "computation_reproducibility"
    specs = [
        ("valid/computation-valid-v0", "computation-valid-v0", "valid_computation", "Admitted", None),
        (
            "invalid/dataset_hash_mismatch",
            "computation-dataset-hash-mismatch-v0",
            "dataset_hash_mismatch",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "dataset_hash_mismatch",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "pin_dataset_version",
            },
        ),
        (
            "invalid/environment_digest_mismatch",
            "computation-environment-digest-mismatch-v0",
            "environment_digest_mismatch",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "environment_digest_mismatch",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "record_environment_digest",
            },
        ),
        (
            "invalid/result_hash_mismatch",
            "computation-result-hash-mismatch-v0",
            "result_hash_mismatch",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "result_hash_mismatch",
                "responsible_component": "verifier",
                "repair_hint_kind": "recompute_and_witness",
            },
        ),
        (
            "invalid/missing_code_commit",
            "computation-missing-code-commit-v0",
            "missing_code_commit",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_code_commit",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "pin_source_commit",
            },
        ),
        (
            "invalid/nonzero_exit_code",
            "computation-nonzero-exit-code-v0",
            "nonzero_exit_code",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "nonzero_exit_code",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "fix_computation_script",
            },
        ),
        (
            "invalid/missing_result_artifact",
            "computation-missing-result-artifact-v0",
            "missing_result_artifact",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_result_artifact",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "emit_result_artifact",
            },
        ),
        (
            "invalid/rejected_computation_witness",
            "computation-rejected-computation-witness-v0",
            "rejected_computation_witness",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "rejected_computation_witness",
                "responsible_component": "verifier",
                "repair_hint_kind": "recompute_and_witness",
            },
        ),
        (
            "invalid/wrong_admission_profile",
            "computation-wrong-admission-profile-v0",
            "wrong_admission_profile",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "wrong_admission_profile",
                "responsible_component": "provability_fabric",
                "repair_hint_kind": "select_correct_admission_profile",
            },
        ),
        (
            "invalid/missing_lean_check_result",
            "computation-missing-lean-check-result-v0",
            "missing_lean_check_result",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_lean_check_result",
                "responsible_component": "formal_kernel",
                "repair_hint_kind": "run_lean_check",
            },
        ),
    ]
    refs: list[tuple[str, str]] = []
    for rel, case_id, kind, status, verification in specs:
        case_dir = comp / rel
        write_case_json(
            case_dir,
            case_id=case_id,
            task_id=f"{case_id}-task",
            workflow_id=WORKFLOW_COMP,
            case_kind=kind,
            expected_status=status,
            expected_failure_code=verification["failure_code"] if verification else None,
            expected_responsible_component=verification["responsible_component"] if verification else None,
            expected_repair_hint_kind=verification.get("repair_hint_kind") if verification else None,
        )
        write_bundle(
            case_dir / "input_artifacts",
            release_id=case_id,
            workflow_id=WORKFLOW_COMP,
            status=status,
            cert_status="Valid" if status == "Admitted" else "Rejected",
        )
        if "lean" in rel:
            art = case_dir / "input_artifacts"
            (art / "proof_obligation.v0.json").write_text(
                json.dumps(
                    {
                        "schema_version": "v0",
                        "obligation_id": f"obligation-{case_id}",
                        "theorem": "computation_integrity",
                        "required": True,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        if verification:
            write_expected(case_dir, verification)
        else:
            write_expected(case_dir, {"status": "Admitted"}, sections_full)
        refs.append((f"{rel}/benchmark_case.v0.json", case_id))
    return refs


def generate_memory_cases(
    write_bundle,
    write_expected,
    sections_full: list[str],
) -> list[tuple[str, str]]:
    sm = ROOT / "benchmarks" / "scientific_memory_rendering"
    partial_no_formal = [s for s in sections_full if s != "Formal Trust Kernel"]
    partial_no_registry = [s for s in sections_full if s != "Artifact Registry"]
    partial_no_lineage = [s for s in sections_full if s != "Lineage"]
    partial_no_staleness = [s for s in sections_full if s != "Staleness"]

    specs = [
        ("valid/render-all-sections-v0", "render-all-sections-v0", "valid_render", "Admitted", None, sections_full),
        (
            "invalid/missing-formal-trust-kernel-section",
            "missing-formal-trust-kernel-section-v0",
            "missing_formal_section",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_rendered_section",
                "responsible_component": "scientific_memory",
            },
            partial_no_formal,
        ),
        (
            "invalid/missing-artifact-registry-section",
            "missing-artifact-registry-section-v0",
            "missing_registry_section",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_rendered_section",
                "responsible_component": "scientific_memory",
            },
            partial_no_registry,
        ),
        (
            "invalid/missing-lineage-section",
            "missing-lineage-section-v0",
            "missing_lineage_section",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_rendered_section",
                "responsible_component": "scientific_memory",
            },
            partial_no_lineage,
        ),
        (
            "invalid/missing-staleness-section",
            "missing-staleness-section-v0",
            "missing_staleness_section",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_rendered_section",
                "responsible_component": "scientific_memory",
            },
            partial_no_staleness,
        ),
        (
            "invalid/failed-release-rendering",
            "failed-release-rendering-v0",
            "failed_rendering",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "rendering_failed",
                "responsible_component": "scientific_memory",
            },
            partial_no_formal,
        ),
        (
            "invalid/release-comparison-changed-certificate",
            "release-comparison-changed-certificate-v0",
            "release_comparison_changed_certificate",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "release_comparison_changed_certificate",
                "responsible_component": "verifier",
            },
            partial_no_formal,
        ),
        (
            "invalid/release-comparison-changed-dataset",
            "release-comparison-changed-dataset-v0",
            "release_comparison_changed_dataset",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "release_comparison_changed_dataset",
                "responsible_component": "verifier",
            },
            partial_no_formal,
        ),
    ]
    refs: list[tuple[str, str]] = []
    for rel, case_id, kind, status, verification, sections in specs:
        case_dir = sm / rel
        write_case_json(
            case_dir,
            case_id=case_id,
            task_id=f"{case_id}-task",
            workflow_id=WORKFLOW_MEMORY,
            case_kind=kind,
            expected_status=status,
            expected_failure_code=verification["failure_code"] if verification else None,
            expected_responsible_component=verification["responsible_component"] if verification else None,
        )
        write_bundle(
            case_dir / "input_artifacts",
            release_id=case_id,
            workflow_id=WORKFLOW_MEMORY,
            status=status,
        )
        if verification:
            write_expected(case_dir, verification, sections)
        else:
            write_expected(case_dir, {"status": "Admitted"}, sections)
        refs.append((f"{rel}/benchmark_case.v0.json", case_id))
    return refs
