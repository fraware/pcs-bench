"""JSON Schema contract for externally inspectable temporal reference cases."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[2] / "benchmarks/temporal_transport/v1"
SCHEMA = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
CASES = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def test_schema_is_valid_json_schema_draft_2020_12():
    Draft202012Validator.check_schema(SCHEMA)


def test_curated_reference_dataset_matches_portable_schema():
    VALIDATOR.validate(CASES)
    assert CASES["curation"].startswith("author-labeled")
    assert len(CASES["cases"]) == 32


def test_all_case_identifiers_are_unique_without_schema_unevaluated_fields():
    ids = [c["id"] for c in CASES["cases"]]
    assert len(ids) == len(set(ids))
    assert set(CASES) == {"schema", "curation", "semantics", "cases"}


@pytest.mark.parametrize("mutation", [
    ("event_at", True),
    ("appraisal_at", "now"),
    ("id", "forged"),
    ("proposition", "historical_truth"),
    ("expected", "safe"),
    ("rationale", "too short"),
])
def test_invalid_or_ambiguous_case_schema_field_is_rejected(mutation):
    copy_case = copy.deepcopy(CASES)
    field, replacement = mutation
    copy_case["cases"][0][field] = replacement
    with pytest.raises(ValidationError):
        VALIDATOR.validate(copy_case)


def test_unknown_case_fields_fail_closed():
    c = copy.deepcopy(CASES)
    c["cases"][0]["accepted_by_issuer"] = True
    with pytest.raises(ValidationError, match="Additional properties"):
        VALIDATOR.validate(c)


def test_unknown_change_fields_fail_closed():
    c = copy.deepcopy(CASES)
    c["cases"][0]["change"]["trusted_claim"] = True
    with pytest.raises(ValidationError, match="Additional properties"):
        VALIDATOR.validate(c)


def test_mutually_exclusive_verified_bridge_and_refutation_flags():
    c = copy.deepcopy(CASES)
    c["cases"][0]["change"] = {
        "dependency": "actor_key",
        "mode": "updated",
        "effective_at": 100,
        "verified_bridge": True,
        "verified_refutation": True,
    }
    with pytest.raises(ValidationError):
        VALIDATOR.validate(c)


def test_cannot_label_verified_refutation_for_merely_unavailable_evidence():
    c = copy.deepcopy(CASES)
    c["cases"][0]["change"] = {
        "dependency": "effect_observation",
        "mode": "unavailable",
        "effective_at": 120,
        "verified_refutation": True,
    }
    with pytest.raises(ValidationError):
        VALIDATOR.validate(c)
