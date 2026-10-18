"""Pinned-source probes: compare PF-Core behavior with independent boundary criteria.

The cases intentionally document where a *reference* adapter makes a weaker
claim than a release-grade relying party would need. They are not exploitation
tests, production security findings, or proofs of full-stack execution.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from pcs_bench.evidence_boundary import (
    assess_evidence_boundary,
    authority_consistency,
    footprint_consistency,
    proof_claim_consistency,
    scope_consistency,
)

_EXTERNAL = os.environ.get("PF_CORE_REPO")
if not _EXTERNAL:
    pytest.skip(
        "PF_CORE_REPO not provided: pinned-source integration is run in a dedicated CI job",
        allow_module_level=True,
    )

ROOT = Path(_EXTERNAL).resolve()
assert (ROOT / "pf-core/validator/pf_core/deciders.py").is_file(), "PF-Core checkout missing"
sys.path.insert(0, str(ROOT / "pf-core/validator"))

from pf_core.compile import compile_observation
from pf_core.deciders import action_allowed
from pf_core.emitter import build_trace, emit_certificate

NORMALIZE_PATH = ROOT / "adapters/provability-fabric/mcp_sidecar/normalize.py"
spec = importlib.util.spec_from_file_location("pinned_pf_core_normalize", NORMALIZE_PATH)
assert spec and spec.loader
normalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalizer)

FIXTURES = ROOT / "adapters/provability-fabric/tests/fixtures"


def _sidecar() -> dict:
    return json.loads((FIXTURES / "sidecar_audit_line.json").read_text(encoding="utf-8"))


def test_auth_01_reference_adapter_self_populates_capability():
    """Directly observe the source-level distinction without declaring an exploit."""
    line = _sidecar()
    assert "effective_capabilities" not in line
    observation = normalizer.normalize_sidecar_line(line)
    cap = observation["action"]["capability"]["id"]
    assert cap in observation["principal"]["capabilities"]
    assert authority_consistency(observation, None).code == "AUTHORITY_NOT_SUPPLIED"
    denied_grant = {
        "principal_id": observation["principal"]["id"],
        "tenant_id": observation["principal"]["tenant_id"],
        "effective_capabilities": [],
    }
    assert authority_consistency(observation, denied_grant).code == "CAPABILITY_NOT_GRANTED"


def test_scope_02_base_action_decider_omits_resource_pattern():
    """A same-tenant out-of-pattern action can satisfy the narrower PF-Core decider."""
    action = {
        "schema_version": "pf-core.action.v1",
        "id": "outside-scope",
        "principal": {
            "schema_version": "pf-core.principal.v1",
            "id": "actor",
            "tenant_id": "tenant-a",
            "roles": ["file_reader"],
            "capabilities": ["cap:file-read"],
        },
        "capability": {
            "schema_version": "pf-core.capability.v0",
            "id": "cap:file-read",
            "effect_kind": "file.read",
            "resource_pattern": "/data/*",
        },
        "effects": [{"schema_version": "pf-core.effect.v0", "kind": "file.read"}],
        "reads": [{
            "schema_version": "pf-core.resource.v0",
            "uri": "/secrets/outside.txt",
            "tenant_id": "tenant-a",
        }],
        "writes": [],
    }
    assert action_allowed(action) is True
    observation = {"action": action, "principal": action["principal"]}
    scope = scope_consistency(observation, {"cap:file-read": "/data/*"})
    assert (scope.status, scope.code) == ("contradicted", "RESOURCE_OUTSIDE_SCOPE")


def test_effect_03_write_is_recorded_as_read_in_reference_adapter():
    """The current source adapter loses file.write read/write classification."""
    line = _sidecar()
    line["tool_effect"] = "file.write"
    line["capability_hint"] = "cap:file-write"
    line["resource"] = "/data/results.json"
    observation = normalizer.normalize_sidecar_line(line)
    assert observation["action"]["reads"][0]["uri"] == "/data/results.json"
    assert observation["action"]["writes"] == []
    report = footprint_consistency(
        observation, {"reads": [], "writes": ["/data/results.json"]}
    )
    assert report.code == "EFFECT_FOOTPRINT_MISMATCH"


def test_scope_02_capability_pattern_may_drift_in_reference_adapter():
    """Reference sidecar normalizer broadens non-MCP capability pattern to mcp:*."""
    line = _sidecar()
    line["tool_effect"] = "file.write"
    line["capability_hint"] = "cap:file-write"
    line["resource"] = "/data/results.json"
    observation = normalizer.normalize_sidecar_line(line)
    assert observation["action"]["capability"]["resource_pattern"] == "mcp:*"
    report = scope_consistency(observation, {"cap:file-write": "/data/*"})
    assert report.code == "CAPABILITY_SCOPE_MISMATCH"


def test_proof_04_legacy_emitter_cannot_mint_kernel_checked_assurance():
    """Real PF-Core emitter output is a legacy label, not a concrete proof replay."""
    line = _sidecar()
    observation = normalizer.normalize_sidecar_line(line)
    event = compile_observation(observation)
    trace = build_trace([event])
    contract = {
        "schema_version": "pf-core.contract.v0",
        "name": "conformance-fixture",
        "pre": {},
        "post": {"require_event_safe": True},
        "invariant": {"require_trace_safe": True},
    }
    cert = emit_certificate(trace, contract)
    assert cert["checker"] == "lean4"
    assert cert["claim_class"] == "Lean-proved"
    assert cert["safe"] is True
    assert proof_claim_consistency(cert).code == "PROOF_CLASS_MISMATCH"
    appraisal = assess_evidence_boundary(
        observation, certificate=cert, trusted_catalog={"cap:mcp-invoke": "mcp:*"}
    )
    assert appraisal.status == "contradicted"
