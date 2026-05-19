#!/usr/bin/env python3
"""Materialize rich PCS release bundles for benchmark cases from templates."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = json.loads((ROOT / "benchmarks" / "_fixtures" / "release_bundle.json").read_text())


def write_bundle(
    dest: Path,
    *,
    release_id: str,
    workflow_id: str,
    status: str,
    cert_status: str = "Valid",
) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {**TEMPLATE["manifest"], "release_id": release_id, "workflow_id": workflow_id, "status": status}
    handoff = {**TEMPLATE["handoff"], "handoff_id": f"handoff-{release_id}", "workflow_id": workflow_id}
    cert = {
        **TEMPLATE["certificate"],
        "certificate_id": f"cert-{release_id}",
        "status": cert_status,
    }
    bundle = {**TEMPLATE["bundle"], "claim_id": release_id, "workflow_id": workflow_id, "status": status}
    profile = {**TEMPLATE["admission_profile"]}

    (dest / "release_manifest.v0.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (dest / "artifact_registry.v0.json").write_text(json.dumps(TEMPLATE["registry"], indent=2), encoding="utf-8")
    (dest / "handoff_manifest.v0.json").write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    (dest / "trace_certificate.v0.json").write_text(json.dumps(cert, indent=2), encoding="utf-8")
    (dest / "science_claim_bundle.v0.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    (dest / "admission_profile.v0.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    if "computation" in workflow_id or "reproducibility" in workflow_id:
        witness = {
            "schema_version": "v0",
            "witness_id": f"witness-{release_id}",
            "result_hashes": ["sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"],
            "property_id": workflow_id,
            "checker": "certifyedge",
            "checker_version": "0.1.0",
            "status": cert_status,
            "source_repo": "https://github.com/fraware/CertifyEdge",
            "source_commit": "deadbeef",
            "signature_or_digest": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        }
        (dest / "computation_witness.v0.json").write_text(json.dumps(witness, indent=2), encoding="utf-8")


def write_expected(case_dir: Path, verification: dict, sections: list[str] | None = None) -> None:
    exp = case_dir / "expected"
    exp.mkdir(parents=True, exist_ok=True)
    (exp / "verification_result.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    if sections:
        (exp / "rendered_sections.json").write_text(
            json.dumps({"sections": sections}, indent=2),
            encoding="utf-8",
        )


SECTIONS_FULL = [
    "Claim",
    "Workflow Profile",
    "Runtime Evidence",
    "Certificate or Witness",
    "Verification Result",
    "Formal Trust Kernel",
    "Release Manifest",
    "Release Chain Validation",
    "Artifact Registry",
    "Handoff Manifests",
    "Artifact Dependency Graph",
    "Lineage",
    "Staleness",
    "Artifact Hashes",
    "Source Repositories",
    "Reproduce / Verify",
    "Limitations",
]


def main() -> None:
    labtrust = ROOT / "benchmarks" / "labtrust_qc_release"
    cases = [
        ("valid/labtrust-valid-release-v0", "labtrust-valid-release-v0", "Admitted", None),
        (
            "invalid/trace_hash_tamper",
            "labtrust-trace-hash-tamper-v0",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "trace_hash_mismatch",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "regenerate_trace_or_certificate",
                "repair_hint": {
                    "responsible_component": "runtime_producer",
                    "failure_code": "trace_hash_mismatch",
                    "artifact_path": "runtime_trace.json",
                    "repair_kind": "regenerate_trace_or_certificate",
                    "action": "labtrust regenerate-release-protocol",
                },
            },
        ),
        (
            "invalid/certificate_id_tamper",
            "labtrust-certificate-id-tamper-v0",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "certificate_id_mismatch",
                "responsible_component": "certificate_producer",
                "repair_hint_kind": "regenerate_certificate",
            },
        ),
        (
            "invalid/legacy_handoff_file",
            "labtrust-legacy-handoff-v0",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "handoff_schema_mismatch",
                "responsible_component": "handoff",
                "repair_hint_kind": "upgrade_handoff_manifest",
            },
        ),
        (
            "invalid/placeholder_commit",
            "labtrust-placeholder-commit-v0",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "placeholder_commit_detected",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "pin_source_commit",
            },
        ),
        (
            "invalid/missing_qc_result",
            "labtrust-missing-qc-result-v0",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "missing_qc_result",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "complete_qc_before_release",
            },
        ),
        (
            "invalid/unauthorized_release",
            "labtrust-unauthorized-release-v0",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "unauthorized_release",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "obtain_release_authorization",
            },
        ),
        (
            "invalid/stale_trace_after_certificate",
            "labtrust-stale-trace-v0",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "stale_trace_after_certificate",
                "responsible_component": "runtime_producer",
                "repair_hint_kind": "regenerate_trace_or_certificate",
            },
        ),
        (
            "invalid/lean_trust_kernel_failure",
            "labtrust-lean-kernel-failure-v0",
            "Rejected",
            {
                "status": "Rejected",
                "failure_code": "lean_theorem_failed",
                "responsible_component": "formal_kernel",
                "repair_hint_kind": "fix_proof_obligation",
            },
        ),
    ]
    for rel, rid, status, verification in cases:
        case_dir = labtrust / rel
        write_bundle(
            case_dir / "input_artifacts",
            release_id=rid,
            workflow_id="hospital_lab.qc_release",
            status=status,
            cert_status="Valid" if status == "Admitted" else "Rejected",
        )
        if "lean" in rel:
            art = case_dir / "input_artifacts"
            (art / "proof_obligation.v0.json").write_text(
                json.dumps(
                    {
                        "schema_version": "v0",
                        "obligation_id": f"obligation-{rid}",
                        "theorem": "release_integrity",
                        "required": True,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (art / "lean_check_result.v0.json").write_text(
                json.dumps(
                    {
                        "schema_version": "v0",
                        "status": "failed",
                        "theorem": "release_integrity",
                        "failure_code": "lean_theorem_failed",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        if verification:
            write_expected(case_dir, verification)
        else:
            write_expected(
                case_dir,
                {"status": "Admitted", "admission_status": "Admitted"},
                SECTIONS_FULL,
            )

    # Tool-use suite
    tool = ROOT / "benchmarks" / "tool_use_safety"
    write_bundle(
        tool / "valid/tool-use-valid-v0/input_artifacts",
        release_id="tool-use-valid-v0",
        workflow_id="agent_tool_use.safety_v0",
        status="Admitted",
    )
    write_expected(
        tool / "valid/tool-use-valid-v0",
        {"status": "Admitted"},
        SECTIONS_FULL,
    )
    write_bundle(
        tool / "invalid/policy_hash_mismatch/input_artifacts",
        release_id="tool-use-policy-hash-mismatch-v0",
        workflow_id="agent_tool_use.safety_v0",
        status="Rejected",
        cert_status="Rejected",
    )
    write_expected(
        tool / "invalid/policy_hash_mismatch",
        {
            "status": "Rejected",
            "failure_code": "policy_hash_mismatch",
            "responsible_component": "runtime_producer",
            "repair_hint_kind": "regenerate_tool_trace",
        },
    )

    # Computation suite
    comp = ROOT / "benchmarks" / "computation_reproducibility"
    write_bundle(
        comp / "valid/computation-valid-v0/input_artifacts",
        release_id="computation-valid-v0",
        workflow_id="scientific_computation.reproducibility_v0",
        status="Admitted",
    )
    write_expected(comp / "valid/computation-valid-v0", {"status": "Admitted"}, SECTIONS_FULL)
    write_bundle(
        comp / "invalid/result_hash_mismatch/input_artifacts",
        release_id="computation-result-hash-mismatch-v0",
        workflow_id="scientific_computation.reproducibility_v0",
        status="Rejected",
        cert_status="Rejected",
    )
    write_expected(
        comp / "invalid/result_hash_mismatch",
        {
            "status": "Rejected",
            "failure_code": "result_hash_mismatch",
            "responsible_component": "verifier",
            "repair_hint_kind": "recompute_and_witness",
        },
    )

    formal = ROOT / "benchmarks" / "formal_trust_kernel"
    write_bundle(
        formal / "valid/lean-obligations-met-v0/input_artifacts",
        release_id="lean-obligations-met-v0",
        workflow_id="pcs.formal_trust_kernel",
        status="Admitted",
    )
    (formal / "valid/lean-obligations-met-v0/input_artifacts/proof_obligation.v0.json").write_text(
        json.dumps(
            {
                "schema_version": "v0",
                "obligation_id": "trust-envelope-v0",
                "theorem": "release_integrity",
                "required": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (formal / "valid/lean-obligations-met-v0/input_artifacts/lean_check_result.v0.json").write_text(
        json.dumps({"schema_version": "v0", "status": "passed", "theorem": "release_integrity"}, indent=2),
        encoding="utf-8",
    )
    write_expected(formal / "valid/lean-obligations-met-v0", {"status": "Admitted"}, SECTIONS_FULL)

    write_bundle(
        formal / "invalid/lean-unauthorized-theorem-v0/input_artifacts",
        release_id="lean-unauthorized-theorem-v0",
        workflow_id="pcs.formal_trust_kernel",
        status="Rejected",
    )
    (formal / "invalid/lean-unauthorized-theorem-v0/input_artifacts/proof_obligation.v0.json").write_text(
        json.dumps(
            {"schema_version": "v0", "obligation_id": "bad-theorem", "theorem": "unauthorized", "required": True},
            indent=2,
        ),
        encoding="utf-8",
    )
    write_expected(
        formal / "invalid/lean-unauthorized-theorem-v0",
        {
            "status": "Rejected",
            "failure_code": "unauthorized_theorem",
            "responsible_component": "formal_kernel",
            "repair_hint_kind": "authorize_theorem_in_kernel",
        },
    )

    sm = ROOT / "benchmarks" / "scientific_memory_rendering"
    write_bundle(
        sm / "valid/render-all-sections-v0/input_artifacts",
        release_id="render-all-sections-v0",
        workflow_id="pcs.scientific_memory",
        status="Admitted",
    )
    write_expected(sm / "valid/render-all-sections-v0", {"status": "Admitted"}, SECTIONS_FULL)

    write_bundle(
        sm / "invalid/missing-formal-section-v0/input_artifacts",
        release_id="missing-formal-section-v0",
        workflow_id="pcs.scientific_memory",
        status="Rejected",
    )
    partial = [s for s in SECTIONS_FULL if s != "Formal Trust Kernel"]
    write_expected(
        sm / "invalid/missing-formal-section-v0",
        {"status": "Rejected", "failure_code": "missing_rendered_section", "responsible_component": "scientific_memory"},
        partial,
    )

    cross = ROOT / "benchmarks" / "cross_domain"
    write_bundle(
        cross / "valid/cross-domain-protocol-v0/input_artifacts",
        release_id="cross-domain-protocol-v0",
        workflow_id="hospital_lab.qc_release",
        status="Admitted",
    )
    write_expected(cross / "valid/cross-domain-protocol-v0", {"status": "Admitted"}, SECTIONS_FULL)

    write_bundle(
        cross / "valid/cross-domain-tool-use-v0/input_artifacts",
        release_id="cross-domain-tool-use-v0",
        workflow_id="agent_tool_use.safety_v0",
        status="Admitted",
    )
    write_expected(cross / "valid/cross-domain-tool-use-v0", {"status": "Admitted"}, SECTIONS_FULL)

    write_bundle(
        cross / "valid/cross-domain-computation-v0/input_artifacts",
        release_id="cross-domain-computation-v0",
        workflow_id="scientific_computation.reproducibility_v0",
        status="Admitted",
    )
    write_expected(cross / "valid/cross-domain-computation-v0", {"status": "Admitted"}, SECTIONS_FULL)

    print("Fixtures materialized.")


if __name__ == "__main__":
    main()
