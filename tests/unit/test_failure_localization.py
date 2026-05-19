"""Tests for failure localization parsing."""

from pcs_bench.failure_localization import parse_verification_result


def test_parse_structured_repair_hint():
    data = {
        "status": "Rejected",
        "failure_code": "trace_hash_mismatch",
        "responsible_component": "runtime_producer",
        "repair_hint": {
            "responsible_component": "runtime_producer",
            "failure_code": "trace_hash_mismatch",
            "repair_kind": "regenerate_trace_or_certificate",
            "action": "labtrust regenerate-release-protocol",
        },
    }
    fl = parse_verification_result(data, case_id="c1")
    assert fl.failure_code == "trace_hash_mismatch"
    assert fl.responsible_component == "runtime_producer"
    assert fl.repair_command == "labtrust regenerate-release-protocol"
