"""Adversarial tests for a distinct cryptographically authenticated target.

All keys are generated at runtime, never committed. The trusted operator is
local SQLite access; the HTTP server only handles signed data-plane requests.
"""
from __future__ import annotations

import json
import os
import select
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pcs_bench.authenticated_target import (
    audience,
    initialize,
    register_key,
    revoke_key,
    sign_request,
)
from pcs_bench.effect_boundary import Action, action_digest, read_target
from pcs_bench.guarded_target import operator_update


@contextmanager
def local_target(tmp_path: Path):
    database = tmp_path / "signed-target.sqlite3"
    initialize(database)
    key = Ed25519PrivateKey.generate()
    register_key(
        database,
        key_id="alice-1",
        principal="agent-1",
        tenant="tenant-a",
        public_key=key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "pcs_bench.authenticated_target",
         "--database", str(database)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy(),
    )
    try:
        assert proc.stdout is not None
        r, _, _ = select.select([proc.stdout], [], [], 15)
        assert r, "target failed to start"
        line = proc.stdout.readline()
        assert line, "target exited before readiness"
        base = f"http://127.0.0.1:{json.loads(line)['port']}"
        with urlopen(base + "/identity", timeout=5) as response:
            aud = json.load(response)["audience"]
        assert aud == audience(database)
        yield base, database, key, aud
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)


@pytest.fixture
def target(tmp_path: Path):
    with local_target(tmp_path) as instance:
        yield instance


def action(operation_id: str = "op-1", **changes) -> Action:
    return Action(
        changes.get("operation_id", operation_id),
        changes.get("principal", "agent-1"),
        changes.get("tenant", "tenant-a"),
        changes.get("resource", "account:a"),
        changes.get("delta", 4),
    )


def send(url: str, path: str, packet: object) -> tuple[int, dict]:
    req = Request(url + path, method="POST", data=json.dumps(packet).encode(),
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=6) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def signed(target, path: str, body: dict, **kwargs) -> tuple[int, dict]:
    url, _, key, aud = target
    packet = sign_request(key, key_id="alice-1", audience_id=aud,
                          route=path, body=body, **kwargs)
    return send(url, path, packet)


def stage(target, act: Action) -> dict:
    code, response = signed(target, "/stage", act.to_dict())
    assert (code, response["status"]) == (202, "staged")
    return response


def finish(target, receipt: dict) -> tuple[int, dict]:
    return signed(target, "/commit-staged", {
        "operation_id": receipt["operation_id"],
        "request_digest": receipt["request_digest"],
    })


def journal(target) -> list[dict]:
    return read_target(target[0], "journal")["effects"]


def test_authenticated_commit_has_target_owned_key_attribution(target):
    code, receipt = signed(target, "/commit", action().to_dict())
    assert code == 200 and receipt["status"] == "committed"
    assert len(journal(target)) == 1
    with urlopen(target[0] + "/auth-journal") as result:
        attested = json.load(result)["commits"]
    assert len(attested) == 1
    assert attested[0]["key_id"] == "alice-1"
    assert len(attested[0]["nonce"]) == 32
    assert read_target(target[0], "state")["balances"] == {"account:a": 4}


def test_unsigned_direct_call_no_longer_bypasses_target(target):
    code, response = send(target[0], "/commit", action().to_dict())
    assert (code, response["error"]) == (400, "invalid_signed_request")
    assert journal(target) == []


def test_attacker_with_own_key_cannot_claim_another_identity(target):
    url, database, _, aud = target
    attacker = Ed25519PrivateKey.generate()
    register_key(
        database, key_id="mallory", principal="agent-2", tenant="tenant-b",
        public_key=attacker.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
    )
    forged = sign_request(attacker, key_id="mallory", audience_id=aud,
                          route="/commit", body=action().to_dict())
    code, reply = send(url, "/commit", forged)
    assert (code, reply["error"]) == (403, "authenticated_identity_mismatch")
    assert journal(target) == []


def test_missing_registry_key_and_bad_signature_fail_closed(target):
    url, _, _, aud = target
    untrusted = Ed25519PrivateKey.generate()
    packet = sign_request(untrusted, key_id="unknown", audience_id=aud,
                          route="/commit", body=action().to_dict())
    assert send(url, "/commit", packet)[1]["error"] == "unregistered_key"
    packet["signed"]["key_id"] = "alice-1"
    assert send(url, "/commit", packet)[1]["error"] == "signature_invalid"
    assert journal(target) == []


def test_tampered_request_body_is_not_authorized(target):
    url, _, key, aud = target
    packet = sign_request(key, key_id="alice-1", audience_id=aud,
                          route="/commit", body=action().to_dict())
    packet["signed"]["body"]["delta"] = 50
    assert send(url, "/commit", packet)[1]["error"] == "signature_invalid"
    assert journal(target) == []


def test_signed_path_method_and_audience_binding(target, tmp_path: Path):
    url, _, key, aud = target
    packet = sign_request(key, key_id="alice-1", audience_id=aud,
                          route="/stage", body=action().to_dict())
    assert send(url, "/commit", packet)[1]["error"] == "invalid_signed_request"
    packet["signed"]["path"] = "/commit"
    assert send(url, "/commit", packet)[1]["error"] == "signature_invalid"
    other_db = tmp_path / "other.sqlite3"
    initialize(other_db)
    assert audience(other_db) != aud
    packet = sign_request(key, key_id="alice-1", audience_id=audience(other_db),
                          route="/commit", body=action().to_dict())
    assert send(url, "/commit", packet)[1]["error"] == "wrong_target_audience"
    assert journal(target) == []


def test_signature_replay_is_rejected_but_new_nonce_can_deduplicate(target):
    url, _, key, aud = target
    packet = sign_request(key, key_id="alice-1", audience_id=aud,
                          route="/commit", body=action().to_dict())
    assert send(url, "/commit", packet)[1]["status"] == "committed"
    code, response = send(url, "/commit", packet)
    assert (code, response["error"]) == (409, "nonce_replay")
    assert signed(target, "/commit", action().to_dict())[1]["status"] == "deduplicated"
    assert len(journal(target)) == 1


def test_same_operation_id_with_altered_payload_is_collision(target):
    assert signed(target, "/commit", action().to_dict())[1]["status"] == "committed"
    code, response = signed(target, "/commit", action(delta=7).to_dict())
    assert (code, response["error"]) == (409, "idempotency_collision")
    assert len(journal(target)) == 1


def test_expired_and_future_requests_fail_without_effect(target):
    now = int(time.time())
    assert signed(target, "/commit", action().to_dict(),
                  issued_at=now - 50, expires_at=now - 20)[1]["error"] == "credential_time_invalid"
    assert signed(target, "/commit", action().to_dict(),
                  issued_at=now + 100, expires_at=now + 110)[1]["error"] == "credential_time_invalid"
    assert signed(target, "/commit", action().to_dict(),
                  issued_at=now, expires_at=now + 100)[1]["error"] == "invalid_signed_request"
    assert journal(target) == []


def test_revoke_key_after_stage_blocks_commit(target):
    receipt = stage(target, action())
    revoke_key(target[1], key_id="alice-1")
    code, data = finish(target, receipt)
    assert (code, data["error"]) == (403, "key_revoked")
    assert journal(target) == []


def test_policy_revoked_between_stage_and_commit_rejects_even_valid_signature(target):
    receipt = stage(target, action())
    operator_update(target[1], next_epoch=2, revoked=True)
    code, data = finish(target, receipt)
    assert (code, data["error"]) == (403, "revoked")
    assert journal(target) == []
    operator_update(target[1], next_epoch=3, revoked=False)
    code, data = finish(target, receipt)
    assert (code, data["error"]) == (409, "stage_policy_epoch_stale")
    assert journal(target) == []


def test_key_id_cannot_take_over_another_key_stage(target):
    receipt = stage(target, action())
    url, database, _, aud = target
    another = Ed25519PrivateKey.generate()
    register_key(
        database, key_id="alice-2", principal="agent-1", tenant="tenant-a",
        public_key=another.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
    )
    packet = sign_request(
        another, key_id="alice-2", audience_id=aud, route="/commit-staged",
        body={"operation_id": receipt["operation_id"],
              "request_digest": receipt["request_digest"]},
    )
    code, response = send(url, "/commit-staged", packet)
    assert (code, response["error"]) == (403, "stage_signer_mismatch")
    assert finish(target, receipt)[1]["status"] == "committed"


def test_stage_receipt_digest_mismatch_is_refused(target):
    receipt = stage(target, action())
    code, response = signed(target, "/commit-staged", {
        "operation_id": receipt["operation_id"],
        "request_digest": action_digest(action(delta=8)),
    })
    assert (code, response["error"]) == (409, "stage_digest_mismatch")
    assert journal(target) == []


def test_direct_signed_permitted_call_still_bypasses_host_acs(target):
    # A valid credential and current target grant permit this direct request.
    # ACS itself has not been consulted: no claim of complete mediation.
    code, result = signed(target, "/commit", action("direct-approved").to_dict())
    assert (code, result["status"]) == (200, "committed")
    assert len(journal(target)) == 1


def test_revoked_policy_rejects_direct_signed_call(target):
    operator_update(target[1], next_epoch=2, revoked=True)
    code, result = signed(target, "/commit", action().to_dict())
    assert (code, result["error"]) == (403, "revoked")
    assert journal(target) == []


def test_replayed_signature_under_concurrency_creates_one_effect(target):
    url, _, key, aud = target
    packet = sign_request(key, key_id="alice-1", audience_id=aud,
                          route="/commit", body=action().to_dict())
    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(lambda _: send(url, "/commit", packet), range(20)))
    assert sum(r.get("status") == "committed" for _, r in responses) == 1
    assert sum(r.get("error") == "nonce_replay" for _, r in responses) == 19
    assert len(journal(target)) == 1


def test_concurrent_fresh_nonces_same_action_are_deduplicated(target):
    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(lambda _: signed(target, "/commit", action().to_dict()), range(20)))
    assert sum(r.get("status") == "committed" for _, r in responses) == 1
    assert sum(r.get("status") == "deduplicated" for _, r in responses) == 19
    assert len(journal(target)) == 1


def test_http_operator_route_is_absent(target):
    code, response = send(target[0], "/operator", {"revoked": True})
    assert (code, response["error"]) == (400, "invalid_signed_request")
    assert journal(target) == []


def test_duplicate_json_fields_are_rejected(target):
    url = target[0]
    raw = b'{"signed":{},"signed":{},"signature":"x"}'
    req = Request(url + "/commit", data=raw, method="POST",
                  headers={"Content-Type": "application/json"})
    with pytest.raises(HTTPError) as caught:
        urlopen(req, timeout=5)
    assert caught.value.code == 400
    assert json.loads(caught.value.read())["error"] == "invalid_json"


def test_duplicate_key_registration_fails_without_replacement(target):
    with pytest.raises(sqlite3.IntegrityError):
        register_key(target[1], key_id="alice-1", principal="intruder",
                     tenant="tenant-a", public_key=b"\x01" * 32)
    assert signed(target, "/commit", action().to_dict())[1]["status"] == "committed"


def test_second_key_cannot_reuse_existing_stage_by_same_principal(target):
    receipt = stage(target, action())
    url, database, _, aud = target
    second = Ed25519PrivateKey.generate()
    register_key(
        database, key_id="alice-2", principal="agent-1", tenant="tenant-a",
        public_key=second.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
    )
    envelope = sign_request(
        second, key_id="alice-2", audience_id=aud,
        route="/stage", body=action().to_dict(),
    )
    code, result = send(url, "/stage", envelope)
    assert (code, result["error"]) == (403, "stage_signer_mismatch")
    assert finish(target, receipt)[1]["status"] == "committed"
    assert len(journal(target)) == 1
