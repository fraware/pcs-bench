"""Actual loopback HTTP -> separate process -> persisted SQLite target effects."""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pcs_bench.effect_boundary import (
    Action,
    Policy,
    action_digest,
    decide,
    dispatch,
    post_commit,
    read_target,
)


@pytest.fixture
def target(tmp_path: Path):
    database = tmp_path / "target.sqlite3"
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "-m", "pcs_bench.effect_target", "--database", str(database)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    try:
        assert proc.stdout is not None
        ready, _, _ = select.select([proc.stdout], [], [], 15)
        assert ready, f"disposable target did not start: {proc.poll()}"
        line = proc.stdout.readline()
        assert line, f"disposable target exited before ready: {proc.poll()}"
        port = json.loads(line)["port"]
        yield f"http://127.0.0.1:{port}", database
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)


def a(operation_id: str, **changes: object) -> Action:
    return replace(Action(operation_id, "agent-1", "tenant-a", "account:a", 5), **changes)


def p(**changes: object) -> Policy:
    return replace(Policy("agent-1", "tenant-a", ("account:a",), 10, 1), **changes)


def effect_count(url: str) -> int:
    return len(read_target(url, "journal")["effects"])


def test_authorized_commit_visible_only_in_target_journal(target):
    url, _ = target
    action = a("authorized-1")
    decision = decide(action, p())
    response = dispatch(url, action, decision, p())
    assert response.status == "committed"
    assert response.target_receipt["request_digest"] == action_digest(action)
    assert read_target(url, "state")["balances"] == {"account:a": 5}
    assert effect_count(url) == 1


def test_denied_action_causes_no_target_effect(target):
    url, _ = target
    bad = a("denied-1", delta=50)
    response = dispatch(url, bad, decide(bad, p()), p())
    assert response.status == "blocked"
    assert read_target(url, "state")["balances"] == {}
    assert effect_count(url) == 0


def test_approval_exactly_binds_action_arguments(target):
    url, _ = target
    authorized = a("mutate-1")
    changed = replace(authorized, delta=7)
    response = dispatch(url, changed, decide(authorized, p()), p())
    assert response.reason == "action_changed_after_approval"
    assert effect_count(url) == 0


def test_revocation_and_epoch_changes_prevent_dispatch(target):
    url, _ = target
    operation = a("revoked-1")
    old = decide(operation, p())
    assert dispatch(url, operation, old, p(revoked=True)).reason == "dispatch_revoked"
    assert dispatch(url, operation, old, p(epoch=2)).reason == "policy_epoch_changed"
    assert effect_count(url) == 0


def test_commit_then_lost_response_is_unknown_not_failure(target):
    url, _ = target
    operation = a("unknown-1")
    decision = decide(operation, p())
    first = dispatch(url, operation, decision, p(), drop_reply_after_commit=True)
    assert first.status == "unknown"
    # An oracle query made AFTER transport failure finds the effect.
    assert effect_count(url) == 1
    assert read_target(url, "state")["balances"] == {"account:a": 5}
    retry = dispatch(url, operation, decision, p())
    assert retry.status == "deduplicated"
    assert effect_count(url) == 1
    assert read_target(url, "state")["balances"] == {"account:a": 5}


def test_idempotency_key_reuse_with_changed_payload_is_rejected(target):
    url, _ = target
    operation = a("collision-1")
    assert dispatch(url, operation, decide(operation, p()), p()).status == "committed"
    code, result = post_commit(url, replace(operation, delta=9))
    assert code == 409 and result["error"] == "idempotency_collision"
    assert effect_count(url) == 1
    assert read_target(url, "state")["balances"] == {"account:a": 5}


def test_unmediated_target_path_demonstrates_bypass_boundary(target):
    url, _ = target
    prohibited = a("bypass-1", delta=50)
    assert decide(prohibited, p()).permitted is False
    # Intentionally bypass cooperative broker. NOT a claim of PF/AGT exploitability.
    code, receipt = post_commit(url, prohibited)
    assert code == 200 and receipt["status"] == "committed"
    assert effect_count(url) == 1
    assert read_target(url, "state")["balances"] == {"account:a": 50}


def test_fresh_idempotency_key_can_duplicate_external_effect(target):
    url, _ = target
    first = a("first-key")
    second = a("second-key")
    for operation in (first, second):
        assert dispatch(url, operation, decide(operation, p()), p()).status == "committed"
    assert effect_count(url) == 2
    assert read_target(url, "state")["balances"] == {"account:a": 10}


def test_disposable_target_commit_is_sqlite_durable(target):
    url, database = target
    operation = a("persist-1")
    assert dispatch(url, operation, decide(operation, p()), p()).status == "committed"
    assert database.exists()
    import sqlite3

    with sqlite3.connect(database) as con:
        row = con.execute("SELECT operation_id, request_digest FROM effects").fetchone()
        assert row == ("persist-1", action_digest(operation))


def test_invalid_target_input_rejected_without_mutation(target):
    url, _ = target
    # Integer bounds and types are checked independently by target, not broker.
    code, result = post_commit(url, a("bad-target", delta=1000001))
    assert code == 400 and result["error"] == "invalid_delta"
    assert effect_count(url) == 0


def test_concurrent_same_key_requests_commit_once(target):
    from concurrent.futures import ThreadPoolExecutor

    url, _ = target
    operation = a("concurrent-idempotent")
    with ThreadPoolExecutor(max_workers=12) as pool:
        replies = list(pool.map(lambda _: post_commit(url, operation), range(20)))
    assert all(code == 200 for code, _ in replies)
    assert sum(body["status"] == "committed" for _, body in replies) == 1
    assert sum(body["status"] == "deduplicated" for _, body in replies) == 19
    assert effect_count(url) == 1
    assert read_target(url, "state")["balances"] == {"account:a": 5}
