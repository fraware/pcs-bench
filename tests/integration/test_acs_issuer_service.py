"""Real ACS policy issuer process -> independently appraised signed target commit.

The target accepts only actor + policy-issuer signatures. The caller does not
possess the issuer's private key, and issuer HTTP exposes only /authorize.
The process still trusts its host/OS and cannot prove an uncompromised issuer.
"""
from __future__ import annotations

import asyncio
import json
import os
import select
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

if os.environ.get("ACS_EFFECT_INTEGRATION") != "1":
    pytest.skip("requires pinned, published native ACS SDK", allow_module_level=True)

from agent_control_spec import __version__ as ACS_VERSION

from pcs_bench.acs_effect_host import AcsEffectHost
from pcs_bench.authenticated_target import register_key, sign_request
from pcs_bench.dual_authority_target import (
    audience, initialize, register_policy_issuer,
)
from pcs_bench.effect_boundary import Action, action_digest, read_target
from pcs_bench.guarded_target import operator_update

SOURCE_POLICY = Path(__file__).resolve().parents[1] / "fixtures/acs_effect"


def request(base: str, path: str, body: object) -> tuple[int, dict]:
    data = json.dumps(body, separators=(",", ":")).encode()
    req = Request(
        base + path, method="POST", data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def get(base: str, path: str) -> dict:
    with urlopen(base + path, timeout=5) as response:
        return json.load(response)


def run_server(args: list[str]):
    return subprocess.Popen(
        [sys.executable, "-m", *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=os.environ.copy(),
    )


def endpoint(proc: subprocess.Popen) -> str:
    assert proc.stdout is not None
    ready, _, _ = select.select([proc.stdout], [], [], 15)
    assert ready, "server did not become ready"
    line = proc.stdout.readline()
    assert line, f"server exited before ready: {proc.poll()}"
    return f"http://127.0.0.1:{json.loads(line)['port']}"


def close(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=5)


@contextmanager
def laboratory(tmp_path: Path):
    assert ACS_VERSION == "0.4.0a4"
    directory = tmp_path / "policy"
    directory.mkdir()
    shutil.copy2(SOURCE_POLICY / "manifest.yaml", directory / "manifest.yaml")
    shutil.copy2(SOURCE_POLICY / "effect_guard.cedar", directory / "effect_guard.cedar")
    manifest = directory / "manifest.yaml"

    database = tmp_path / "target.sqlite3"
    initialize(database)
    actor = Ed25519PrivateKey.generate()
    register_key(
        database, key_id="issuer-lab-actor", principal="agent-1", tenant="tenant-a",
        public_key=actor.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        ),
    )
    target_audience = audience(database)
    public_file = tmp_path / "issuer-public.bin"
    issuer_proc = run_server([
        "pcs_bench.acs_issuer_service",
        "--manifest", str(manifest),
        "--target-audience", target_audience,
        "--issuer-id", "lab-issuer",
        "--actor-key-id", "issuer-lab-actor",
        "--public-key-file", str(public_file),
    ])
    target_proc = None
    try:
        issuer_url = endpoint(issuer_proc)
        public_key = public_file.read_bytes()
        assert len(public_key) == 32
        identity = get(issuer_url, "/identity")
        assert identity["issuer_id"] == "lab-issuer"
        assert identity["actor_key_id"] == "issuer-lab-actor"
        register_policy_issuer(
            database, issuer_id="lab-issuer", public_key=public_key,
            policy_sha256=identity["policy_sha256"],
        )
        target_proc = run_server([
            "pcs_bench.dual_authority_target", "--database", str(database),
        ])
        target_url = endpoint(target_proc)
        yield {
            "issuer": issuer_url, "target": target_url, "actor": actor,
            "audience": target_audience, "manifest": manifest, "database": database,
            "policy": directory / "effect_guard.cedar", "identity": identity,
        }
    finally:
        if target_proc is not None:
            close(target_proc)
        close(issuer_proc)


@pytest.fixture
def lab(tmp_path: Path):
    with laboratory(tmp_path) as ctx:
        yield ctx


def action(operation_id: str = "lab-valid", delta: int = 3) -> Action:
    return Action(operation_id, "agent-1", "tenant-a", "account:a", delta)


def ask(lab: dict, item: Action, **changes: object) -> tuple[int, dict]:
    request_body: dict[str, object] = {
        "action": item.to_dict(), "actor_key_id": "issuer-lab-actor",
    }
    request_body.update(changes)
    return request(lab["issuer"], "/authorize", request_body)


def commit(lab: dict, item: Action, token: dict | None) -> tuple[int, dict]:
    actor_packet = sign_request(
        lab["actor"], key_id="issuer-lab-actor",
        audience_id=lab["audience"], route="/commit", body=item.to_dict(),
    )
    packet = (
        {"actor": actor_packet, "authorization": token}
        if token is not None else actor_packet
    )
    return request(lab["target"], "/commit", packet)


def test_issuer_process_invokes_real_acs_before_signing(lab):
    item = action()
    status, issued = ask(lab, item)
    assert (status, issued["status"]) == (200, "issued")
    signed = issued["authorization"]
    assert signed["statement"]["action_digest"] == action_digest(item)
    assert signed["statement"]["actor_key_id"] == "issuer-lab-actor"
    assert signed["statement"]["policy_sha256"] == lab["identity"]["policy_sha256"]
    code, result = commit(lab, item, signed)
    assert (code, result["status"]) == (200, "committed")
    assert len(read_target(lab["target"], "journal")["effects"]) == 1

    # An external replay of the submitted facts agrees with the policy result;
    # it uses the SAME upstream ACS implementation, not an independent prover.
    checker = AcsEffectHost(lab["manifest"], legacy_cedar_principal_bridge=True)
    replay = asyncio.run(checker.authorize(item))
    assert replay.permitted is True
    assert replay.request_digest == signed["statement"]["action_digest"]
    audit = get(lab["issuer"], "/audit")
    assert audit["events"][0]["permitted"] is True
    assert audit["events"][0]["decision_id"] == signed["statement"]["decision_id"]


def test_denied_real_cedar_evaluation_never_mints_permission(lab):
    item = action("policy-forbidden", 25)
    code, response = ask(lab, item)
    assert (code, response["status"], response["reason"]) == (
        403, "denied", "effect_delta_excessive",
    )
    assert "authorization" not in response
    assert commit(lab, item, None)[1]["error"] == "policy_authorization_required"
    assert read_target(lab["target"], "journal")["effects"] == []
    audit = get(lab["issuer"], "/audit")
    assert audit["events"][0]["permitted"] is False


def test_caller_cannot_inject_verdict_policy_digest_or_issue_raw_signature(lab):
    item = action()
    assert ask(lab, item, verdict="allow")[1]["error"] == "invalid_issuer_request"
    assert ask(lab, item, policy_sha256="a" * 64)[1]["error"] == "invalid_issuer_request"
    assert ask(lab, item, actor_key_id="some-other-actor")[1]["error"] == (
        "actor_key_not_enrolled_in_issuer"
    )
    assert request(lab["issuer"], "/sign", {"payload": "allow"})[0] == 404
    assert "private_key" not in get(lab["issuer"], "/identity")
    assert get(lab["issuer"], "/audit")["events"] == []


def test_issuer_fails_closed_if_policy_file_changes_after_start(lab):
    original = lab["policy"].read_text(encoding="utf-8")
    lab["policy"].write_text(original + "\n// altered after process start\n", encoding="utf-8")
    code, result = ask(lab, action())
    assert (code, result["error"]) == (503, "pinned_policy_bytes_changed")
    assert get(lab["issuer"], "/audit")["events"] == []
    assert read_target(lab["target"], "journal")["effects"] == []


def test_target_policy_epoch_revocation_overrules_valid_issuer_token(lab):
    item = action()
    assert ask(lab, item)[0] == 200
    token = ask(lab, item)[1]["authorization"]
    operator_update(lab["database"], next_epoch=2, revoked=True)
    code, r = commit(lab, item, token)
    assert (code, r["error"]) == (409, "authorization_policy_epoch_stale")
    assert read_target(lab["target"], "journal")["effects"] == []


def test_issuer_cannot_authorize_an_altered_action_with_preexisting_token(lab):
    original = action()
    code, result = ask(lab, original)
    assert code == 200
    token = result["authorization"]
    altered = action("lab-valid", 4)
    code, result = commit(lab, altered, token)
    assert (code, result["error"]) == (403, "decision_action_mismatch")
    assert read_target(lab["target"], "journal")["effects"] == []
