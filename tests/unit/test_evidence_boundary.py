"""Unit tests for three-valued cross-repository evidence boundary appraisal."""

from __future__ import annotations

from copy import deepcopy

from pcs_bench.evidence_boundary import (
    assess_evidence_boundary,
    authority_consistency,
    footprint_consistency,
    proof_claim_consistency,
    scope_consistency,
)

CATALOG = {"cap:file-write": "/data/*", "cap:file-read": "/data/*"}
GRANT = {
    "principal_id": "agent-1",
    "tenant_id": "tenant-a",
    "effective_capabilities": ["cap:file-write"],
}


def example_observation() -> dict:
    return {
        "schema_version": "pf-core.runtime_observation.v1",
        "decision": "allowed",
        "principal": {
            "id": "agent-1",
            "tenant_id": "tenant-a",
            "roles": ["file_admin"],
            "capabilities": ["cap:file-write"],
        },
        "action": {
            "principal": {
                "id": "agent-1",
                "tenant_id": "tenant-a",
                "roles": ["file_admin"],
                "capabilities": ["cap:file-write"],
            },
            "capability": {
                "id": "cap:file-write",
                "effect_kind": "file.write",
                "resource_pattern": "/data/*",
            },
            "effects": [{"kind": "file.write"}],
            "reads": [],
            "writes": [{"uri": "/data/results.json", "tenant_id": "tenant-a"}],
        },
    }


def test_auth_01_missing_independent_grant_is_insufficient():
    report = authority_consistency(example_observation(), None)
    assert (report.status, report.code) == ("insufficient", "AUTHORITY_NOT_SUPPLIED")


def test_auth_01_claimed_role_cannot_replace_independent_grant():
    external = {**GRANT, "effective_capabilities": []}
    result = authority_consistency(example_observation(), external)
    assert (result.status, result.code) == ("contradicted", "CAPABILITY_NOT_GRANTED")


def test_auth_01_matching_grant_is_only_conditional_consistency():
    result = authority_consistency(example_observation(), GRANT)
    assert result.status == "consistent"
    assert "unverified" in result.detail


def test_auth_01_principal_mismatch_is_refuted():
    result = authority_consistency(example_observation(), {**GRANT, "tenant_id": "other"})
    assert result.code == "GRANT_SUBJECT_MISMATCH"


def test_scope_02_resource_outside_granted_pattern_is_refuted():
    observation = example_observation()
    observation["action"]["writes"][0]["uri"] = "/secrets/passwords"
    result = scope_consistency(observation, CATALOG)
    assert (result.status, result.code) == ("contradicted", "RESOURCE_OUTSIDE_SCOPE")


def test_scope_02_source_cannot_expand_trusted_capability_catalog():
    observation = example_observation()
    observation["action"]["capability"]["resource_pattern"] = "*"
    result = scope_consistency(observation, CATALOG)
    assert (result.status, result.code) == ("contradicted", "CAPABILITY_SCOPE_MISMATCH")


def test_scope_02_missing_independent_catalog_is_insufficient():
    result = scope_consistency(example_observation(), None)
    assert result.code == "CAPABILITY_CATALOG_ABSENT"


def test_scope_02_matching_resource_and_catalog_is_consistent():
    assert scope_consistency(example_observation(), CATALOG).status == "consistent"


def test_effect_03_write_recorded_as_read_is_refuted():
    observation = example_observation()
    write = observation["action"]["writes"].pop()
    observation["action"]["reads"].append(write)
    result = footprint_consistency(
        observation, {"reads": [], "writes": ["/data/results.json"]}
    )
    assert (result.status, result.code) == ("contradicted", "EFFECT_FOOTPRINT_MISMATCH")


def test_effect_03_missing_independent_oracle_is_insufficient():
    assert footprint_consistency(example_observation(), None).code == "EFFECT_ORACLE_ABSENT"


def test_effect_03_matching_independent_footprint_is_consistent():
    result = footprint_consistency(
        example_observation(), {"reads": [], "writes": ["/data/results.json"]}
    )
    assert result.status == "consistent"


def test_proof_04_legacy_label_never_promotes_to_lean_kernel():
    result = proof_claim_consistency(
        {"claim_class": "Lean-proved", "checker": "lean4", "safe": True}
    )
    assert (result.status, result.code) == ("contradicted", "PROOF_CLASS_MISMATCH")


def test_proof_04_lean_label_alone_cannot_prove_lean_was_run():
    result = proof_claim_consistency(
        {"claim_class": "LeanKernelChecked", "lean_proof_checked": True}
    )
    assert (result.status, result.code) == (
        "insufficient", "INDEPENDENT_PROOF_CHECK_REQUIRED"
    )


def test_combined_evidence_never_automatically_mints_assurance():
    report = assess_evidence_boundary(
        example_observation(),
        independent_grant=GRANT,
        trusted_catalog=CATALOG,
        independent_footprint={"reads": [], "writes": ["/data/results.json"]},
        certificate={"claim_class": "LeanKernelChecked"},
    )
    assert report.authority.status == "consistent"
    assert report.scope.status == "consistent"
    assert report.footprint.status == "consistent"
    assert report.proof.status == "insufficient"
    assert report.status == "insufficient"
    assert "not established" in report.to_dict()["assurance_limit"]


def test_refutation_dominates_unknown_and_copy_is_unmodified():
    observation = example_observation()
    original = deepcopy(observation)
    observation["action"]["writes"][0]["uri"] = "/outside/data"
    report = assess_evidence_boundary(
        observation, independent_grant=GRANT, trusted_catalog=CATALOG
    )
    assert report.status == "contradicted"
    assert original["action"]["writes"][0]["uri"] == "/data/results.json"
