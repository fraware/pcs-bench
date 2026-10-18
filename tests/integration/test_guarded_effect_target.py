"""Target-owned authorization and policy-update ordering tests."""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from pcs_bench.effect_boundary import Action, action_digest, read_target
from pcs_bench.guarded_target import operator_update


@contextmanager
def server(database: Path):
    process = subprocess.Popen(
        [sys.executable, "-m", "pcs_bench.guarded_target", "--database", str(database)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy(),
    )
    try:
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 10)
        assert ready
        line = process.stdout.readline()
        assert line
        yield f"http://127.0.0.1:{json.loads(line)['port']}"
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def post(url: str, route: str, data: dict[str, object]) -> tuple[int, dict]:
    request = Request(
        url + route, method="POST",
        headers={"Content-Type": "application/json"}, data=json.dumps(data).encode(),
    )
    try:
        with urlopen(request, timeout=5) as res:
            return res.status, json.loads(res.read())
    except HTTPError as err:
        return err.code, json.loads(err.read())


@pytest.fixture
def guarded(tmp_path: Path):
    database = tmp_path / "protected.sqlite"
    with server(database) as url:
        yield url, database


def example(ident: str = "op", **changes: object) -> Action:
    return replace(Action(ident, "agent-1", "tenant-a", "account:a", 5), **changes)


def stage(url: str, action: Action) -> dict:
    code, result = post(url, "/stage", action.to_dict())
    assert code == 202, result
    return result


def conclude(url: str, stage_record: dict) -> tuple[int, dict]:
    return post(url, "/commit-staged", {
        "operation_id": stage_record["operation_id"],
        "request_digest": stage_record["request_digest"],
    })


def test_staging_does_not_commit_until_separate_authorization_at_commit(guarded):
    url, _ = guarded
    rec = stage(url, example())
    assert rec["stage_epoch"] == 1
    assert read_target(url, "state")["balances"] == {}
    assert read_target(url, "journal")["effects"] == []
    code, result = conclude(url, rec)
    assert (code, result["status"]) == (200, "committed")
    assert result["commit_epoch"] == 1
    assert read_target(url, "state")["balances"] == {"account:a": 5}


def test_target_revocation_between_stage_and_commit_blocks_effect(guarded):
    url, database = guarded
    rec = stage(url, example())
    operator_update(database, next_epoch=2, revoked=True)
    code, result = conclude(url, rec)
    assert (code, result["error"]) == (403, "revoked")
    assert result["policy_epoch"] == 2
    assert read_target(url, "journal")["effects"] == []
    assert read_target(url, "state")["balances"] == {}
    operator_update(database, next_epoch=3, revoked=False)
    code, result = conclude(url, rec)
    assert (code, result["error"]) == (409, "stage_policy_epoch_stale")
    assert read_target(url, "journal")["effects"] == []
    newer = stage(url, example("newer"))
    assert newer["stage_epoch"] == 3
    assert conclude(url, newer)[1]["status"] == "committed"


def test_new_policy_epoch_requires_new_staging_even_if_policy_allows(guarded):
    url, database = guarded
    rec = stage(url, example())
    operator_update(database, next_epoch=2, revoked=False)
    code, data = conclude(url, rec)
    assert (code, data["error"]) == (409, "stage_policy_epoch_stale")
    assert read_target(url, "journal")["effects"] == []


def test_scope_contraction_between_stage_and_commit_blocks_effect(guarded):
    url, database = guarded
    rec = stage(url, example(delta=5))
    operator_update(database, next_epoch=2, revoked=False, max_delta=3)
    code, data = conclude(url, rec)
    assert (code, data["error"]) == (403, "amount_not_granted")
    assert read_target(url, "journal")["effects"] == []


def test_direct_unmediated_disallowed_call_is_rejected_by_target(guarded):
    url, _ = guarded
    invalid = (
        example("too-high", delta=25),
        example("out-of-scope", resource="account:b"),
        example("other-principal", principal="intruder"),
        example("other-tenant", tenant="tenant-b"),
    )
    for action in invalid:
        code, _ = post(url, "/commit", action.to_dict())
        assert code == 403
    assert read_target(url, "journal")["effects"] == []


def test_target_cannot_authenticate_forged_declared_principal(guarded):
    url, _ = guarded
    # Caller-supplied principal is NOT a real credential.
    code, result = post(url, "/commit", example("forgeable").to_dict())
    assert (code, result["status"]) == (200, "committed")
    assert len(read_target(url, "journal")["effects"]) == 1


def test_http_cannot_mutate_policy_using_untrusted_admin_route(guarded):
    url, _ = guarded
    code, _ = post(url, "/operator", {"next_epoch": 2, "revoked": True})
    assert code == 404
    code, result = post(url, "/commit", example().to_dict())
    assert (code, result["status"]) == (200, "committed")


def test_staged_receipt_binding_cannot_change_payload(guarded):
    url, _ = guarded
    rec = stage(url, example())
    code, data = post(url, "/commit-staged", {
        "operation_id": rec["operation_id"],
        "request_digest": action_digest(example(delta=7)),
    })
    assert (code, data["error"]) == (409, "stage_digest_mismatch")
    code, data = post(url, "/stage", example(delta=6).to_dict())
    assert (code, data["error"]) == (409, "staged_operation_collision")
    assert read_target(url, "journal")["effects"] == []


def test_committed_operation_replay_after_revocation_is_not_new_effect(guarded):
    url, database = guarded
    rec = stage(url, example())
    assert conclude(url, rec)[1]["status"] == "committed"
    operator_update(database, next_epoch=2, revoked=True)
    code, result = conclude(url, rec)
    assert (code, result["status"]) == (200, "deduplicated")
    assert result["commit_epoch"] == 1
    assert read_target(url, "state")["balances"] == {"account:a": 5}
    assert len(read_target(url, "journal")["effects"]) == 1


def test_revoked_direct_commit_never_creates_effect(guarded):
    url, database = guarded
    operator_update(database, next_epoch=2, revoked=True)
    code, result = post(url, "/commit", example().to_dict())
    assert (code, result["error"]) == (403, "revoked")
    assert read_target(url, "journal")["effects"] == []


def test_concurrent_same_key_staged_commits_are_linearizable(guarded):
    url, _ = guarded
    rec = stage(url, example())
    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(lambda _: conclude(url, rec), range(20)))
    assert all(code == 200 for code, _ in responses)
    assert sum(data["status"] == "committed" for _, data in responses) == 1
    assert sum(data["status"] == "deduplicated" for _, data in responses) == 19
    assert len(read_target(url, "journal")["effects"]) == 1


def test_concurrent_commit_and_revocation_obey_sqlite_order(guarded):
    url, database = guarded
    staged = [stage(url, example(f"concurrent-{j}")) for j in range(24)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(conclude, url, receipt) for receipt in staged]
        revocation = pool.submit(operator_update, database, next_epoch=2, revoked=True)
        results = [f.result() for f in futures]
        revocation.result()
    assert all(code in (200, 403) for code, _ in results)
    assert all(r.get("commit_epoch", 1) == 1 for _, r in results if r.get("status") == "committed")
    assert all(e["commit_epoch"] == 1 for e in read_target(url, "journal")["effects"])
    assert len(read_target(url, "journal")["effects"]) == sum(
        r.get("status") == "committed" for _, r in results
    )
    code, payload = post(url, "/commit", example("post-revocation").to_dict())
    assert (code, payload["error"]) == (403, "revoked")


def test_invalid_action_schema_and_boolean_amount_rejected(guarded):
    url, _ = guarded
    for malformed in (
        {**example().to_dict(), "delta": True},
        {**example().to_dict(), "operation_id": ""},
        {**example().to_dict(), "unexpected": "value"},
    ):
        code, data = post(url, "/commit", malformed)
        assert (code, data["error"]) == (400, "invalid_request")
    assert read_target(url, "journal")["effects"] == []


def test_nonmonotone_operator_epoch_is_rejected(guarded):
    url, database = guarded
    with pytest.raises(ValueError, match="monotonically"):
        operator_update(database, next_epoch=1, revoked=True)
    with pytest.raises(ValueError, match="epoch"):
        operator_update(database, next_epoch=True, revoked=True)
    assert post(url, "/commit", example().to_dict())[1]["status"] == "committed"
