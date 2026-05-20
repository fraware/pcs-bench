#!/usr/bin/env python3
"""Generate expanded tool-use, computation, and scientific-memory benchmark cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from case_fixture_writer import write_from_verification, write_valid_case  # noqa: E402

WORKFLOW_TOOL = "agent_tool_use.safety_v0"
WORKFLOW_COMP = "scientific_computation.reproducibility_v0"
WORKFLOW_MEMORY = "pcs.scientific_memory"


def generate_tool_use_cases(
    write_bundle,
    write_expected,
    sections_full: list[str],
) -> list[tuple[str, str]]:
    """Returns (relative_path, case_id) for suite.yaml."""
    tool = ROOT / "benchmarks" / "tool_use_safety"
    specs = [
        ("valid/tool-use-valid-v0", "tool-use-valid-v0", "valid", None),
        (
            "invalid/unauthorized_tool_call",
            "tool-use-unauthorized-tool-call-v0",
            "unauthorized_tool_call",
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
            {
                "status": "Rejected",
                "failure_code": "missing_handoff",
                "responsible_component": "handoff",
                "repair_hint_kind": "provide_handoff_manifest",
            },
        ),
    ]
    refs: list[tuple[str, str]] = []
    for rel, case_id, kind, verification in specs:
        case_dir = tool / rel
        task_id = f"{case_id}-task"
        if verification:
            write_from_verification(
                case_dir,
                case_id=case_id,
                task_id=task_id,
                workflow_id=WORKFLOW_TOOL,
                case_kind=kind,
                verification=verification,
            )
        else:
            write_valid_case(
                case_dir,
                case_id=case_id,
                task_id=task_id,
                workflow_id=WORKFLOW_TOOL,
                case_kind=kind,
            )
        write_bundle(
            case_dir / "input_artifacts",
            release_id=case_id,
            workflow_id=WORKFLOW_TOOL,
            status="Admitted" if not verification else "Rejected",
            cert_status="Valid" if not verification else "Rejected",
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
        ("valid/computation-valid-v0", "computation-valid-v0", "valid", None),
        (
            "invalid/dataset_hash_mismatch",
            "computation-dataset-hash-mismatch-v0",
            "dataset_hash_mismatch",
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
            {
                "status": "Rejected",
                "failure_code": "missing_lean_check_result",
                "responsible_component": "formal_kernel",
                "repair_hint_kind": "run_lean_check",
            },
        ),
    ]
    refs: list[tuple[str, str]] = []
    for rel, case_id, kind, verification in specs:
        case_dir = comp / rel
        task_id = f"{case_id}-task"
        if verification:
            write_from_verification(
                case_dir,
                case_id=case_id,
                task_id=task_id,
                workflow_id=WORKFLOW_COMP,
                case_kind=kind,
                verification=verification,
            )
        else:
            write_valid_case(
                case_dir,
                case_id=case_id,
                task_id=task_id,
                workflow_id=WORKFLOW_COMP,
                case_kind=kind,
            )
        write_bundle(
            case_dir / "input_artifacts",
            release_id=case_id,
            workflow_id=WORKFLOW_COMP,
            status="Admitted" if not verification else "Rejected",
            cert_status="Valid" if not verification else "Rejected",
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
        ("valid/render-all-sections-v0", "render-all-sections-v0", "valid", None, sections_full),
        (
            "invalid/missing-formal-trust-kernel-section",
            "missing-formal-trust-kernel-section-v0",
            "missing_formal_section",
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
            {
                "status": "Rejected",
                "failure_code": "release_comparison_changed_dataset",
                "responsible_component": "verifier",
            },
            partial_no_formal,
        ),
    ]
    refs: list[tuple[str, str]] = []
    for rel, case_id, kind, verification, sections in specs:
        case_dir = sm / rel
        task_id = f"{case_id}-task"
        if verification:
            write_from_verification(
                case_dir,
                case_id=case_id,
                task_id=task_id,
                workflow_id=WORKFLOW_MEMORY,
                case_kind=kind,
                verification=verification,
            )
        else:
            write_valid_case(
                case_dir,
                case_id=case_id,
                task_id=task_id,
                workflow_id=WORKFLOW_MEMORY,
                case_kind=kind,
            )
        write_bundle(
            case_dir / "input_artifacts",
            release_id=case_id,
            workflow_id=WORKFLOW_MEMORY,
            status="Admitted" if not verification else "Rejected",
        )
        if verification:
            write_expected(case_dir, verification, sections)
        else:
            write_expected(case_dir, {"status": "Admitted"}, sections)
        refs.append((f"{rel}/benchmark_case.v0.json", case_id))
    return refs
