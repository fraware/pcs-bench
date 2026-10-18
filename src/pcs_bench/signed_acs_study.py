"""Real ACS/Cedar policy + Ed25519-authenticated target commit-time study.

The host holds an ephemeral signing key for the test, while the separate
target process holds only its operator-enrolled public key. All raw HTTP
requests are directly observed in a target-owned SQLite journal.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import select
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pcs_bench.acs_effect_host import AcsEffectHost
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
def signed_target(database: Path) -> Iterator[tuple[str, Ed25519PrivateKey, str]]:
    """Start a separate target process, with no private key stored server-side."""
    initialize(database)
    key = Ed25519PrivateKey.generate()
    register_key(
        database, key_id="acs-lab-key", principal="agent-1", tenant="tenant-a",
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
        ready, _, _ = select.select([proc.stdout], [], [], 15)
        if not ready:
            raise RuntimeError("authenticated target startup timed out")
        announced = proc.stdout.readline()
        if not announced:
            raise RuntimeError(f"authenticated target exited: {proc.poll()}")
        url = f"http://127.0.0.1:{json.loads(announced)['port']}"
        yield url, key, audience(database)
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)


def send(url: str, route: str, envelope: object) -> tuple[int, dict[str, Any]]:
    req = Request(url + route, data=json.dumps(envelope).encode(), method="POST",
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as result:
            return result.status, json.loads(result.read(32768))
    except HTTPError as error:
        return error.code, json.loads(error.read(32768))


async def run_study(
    manifest: Path, url: str, database: Path, signer: Ed25519PrivateKey, aud: str,
) -> dict[str, Any]:
    from agent_control_spec import __version__ as acs_version

    host = AcsEffectHost(manifest, epoch=1, legacy_cedar_principal_bridge=True)
    cases: list[dict[str, Any]] = []

    def count() -> int:
        return len(read_target(url, "journal")["effects"])

    def call(route: str, body: dict[str, object]) -> tuple[int, dict[str, Any]]:
        request = sign_request(signer, key_id="acs-lab-key", audience_id=aud,
                               route=route, body=body)
        return send(url, route, request)

    def record(
        case: str, before: int, code: int, payload: dict[str, Any],
        expected_code: int, expected_status: str, expected_commits: int,
    ) -> None:
        outcome = payload.get("status", payload.get("error"))
        observed = count() - before
        cases.append({
            "case": case, "expected_http": expected_code, "actual_http": code,
            "expected_outcome": expected_status, "actual_outcome": outcome,
            "expected_new_commits": expected_commits, "observed_new_commits": observed,
            "pass": (code, outcome, observed) == (
                expected_code, expected_status, expected_commits
            ),
        })

    initial = Action("signed-acs-allowed", "agent-1", "tenant-a", "account:a", 5)
    granted = await host.authorize(initial)
    if not granted.permitted:
        raise RuntimeError(f"real ACS denied permitted action: {granted.reason}")
    permitted, reason = await host._evaluate(initial, attempt="authenticated-stage")
    if not permitted or granted.request_digest != action_digest(initial):
        raise RuntimeError(f"host action binding rejected: {reason}")
    before = count()
    stage_code, staged = call("/stage", initial.to_dict())
    if stage_code != 202:
        raise RuntimeError(f"authenticated stage refused: {staged}")
    code, receipt = call("/commit-staged", {
        "operation_id": initial.operation_id, "request_digest": staged["request_digest"]
    })
    record("ACSS-01-signed-acs-commit", before, code, receipt, 200, "committed", 1)

    forbidden = replace(initial, operation_id="signed-acs-denied", delta=50)
    verdict = await host.authorize(forbidden)
    if verdict.permitted or verdict.reason != "effect_delta_excessive":
        raise RuntimeError("unexpected Cedar denial semantics")
    before = count()
    record("ACSS-02-real-cedar-denial", before, 403, {"error": "acs_denied"},
           403, "acs_denied", 0)

    before = count()
    code, reply = send(url, "/commit", replace(initial, operation_id="unsigned").to_dict())
    record("ACSS-03-unsigned-forgery", before, code, reply,
           400, "invalid_signed_request", 0)

    before = count()
    code, reply = call("/commit", replace(
        initial, operation_id="forged-identity", principal="intruder"
    ).to_dict())
    record("ACSS-04-signed-subject-mismatch", before, code, reply,
           403, "authenticated_identity_mismatch", 0)

    before = count()
    packet = sign_request(
        signer, key_id="acs-lab-key", audience_id=aud, route="/commit",
        body=replace(initial, operation_id="nonce-replay", delta=1).to_dict(),
    )
    first_code, first_payload = send(url, "/commit", packet)
    if first_code != 200 or first_payload.get("status") != "committed":
        raise RuntimeError(f"initial signed nonce request failed: {first_payload}")
    second_code, second_payload = send(url, "/commit", packet)
    record("ACSS-05-replay-same-signed-packet", before, second_code, second_payload,
           409, "nonce_replay", 1)

    next_action = replace(initial, operation_id="staged-then-revoked", delta=4)
    if not (await host.authorize(next_action)).permitted:
        raise RuntimeError("real ACS stage authorization failed")
    stage_code, later_stage = call("/stage", next_action.to_dict())
    if stage_code != 202:
        raise RuntimeError(f"second stage failed: {later_stage}")
    operator_update(database, next_epoch=2, revoked=True)
    before = count()
    code, reply = call("/commit-staged", {
        "operation_id": next_action.operation_id,
        "request_digest": later_stage["request_digest"],
    })
    record("ACSS-06-key-valid-policy-revoked", before, code, reply, 403, "revoked", 0)

    operator_update(database, next_epoch=3, revoked=False)
    before = count()
    code, reply = call("/commit-staged", {
        "operation_id": next_action.operation_id,
        "request_digest": later_stage["request_digest"],
    })
    record("ACSS-07-old-stage-after-regrant", before, code, reply,
           409, "stage_policy_epoch_stale", 0)

    host.change_policy_state(epoch=3, revoked=False)
    fresh = replace(initial, operation_id="fresh-stage-epoch", delta=2)
    approved = await host.authorize(fresh)
    if not approved.permitted:
        raise RuntimeError("unexpected ACS denial after regrant")
    before = count()
    scode, stage3 = call("/stage", fresh.to_dict())
    if scode != 202:
        raise RuntimeError(f"fresh stage failed: {stage3}")
    code, reply = call("/commit-staged", {
        "operation_id": fresh.operation_id, "request_digest": stage3["request_digest"],
    })
    record("ACSS-08-signed-regrant-commit", before, code, reply, 200, "committed", 1)

    # Even a valid, authorized credential does not imply ACS interception.
    before = count()
    code, reply = call("/commit", replace(
        initial, operation_id="direct-valid-credential", delta=3
    ).to_dict())
    record("ACSS-09-valid-key-bypasses-cooperative-acs", before, code, reply,
           200, "committed", 1)

    staged_key = replace(initial, operation_id="key-revoked-before-commit", delta=2)
    scode, stage4 = call("/stage", staged_key.to_dict())
    if scode != 202:
        raise RuntimeError(f"key revocation stage failed: {stage4}")
    revoke_key(database, key_id="acs-lab-key")
    before = count()
    code, reply = call("/commit-staged", {
        "operation_id": staged_key.operation_id,
        "request_digest": stage4["request_digest"],
    })
    record("ACSS-10-key-revocation-before-commit", before, code, reply,
           403, "key_revoked", 0)

    with urlopen(url + "/auth-journal", timeout=5) as response:
        auth_journal = json.load(response)["commits"]
    return {
        "protocol": "acs-signed-target-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "pass" if all(row["pass"] for row in cases) else "fail",
        "case_count": len(cases),
        "cases": cases,
        "acs": {
            "package_version": acs_version, "cedar_manifest_sha256": host.manifest_sha256,
            "cedar_policy_sha256": host.cedar_sha256,
            "legacy_alpha4_principal_projection": True,
        },
        "target": {
            "audience": aud, "authenticated_effects": len(auth_journal),
            "key_ids": sorted({entry["key_id"] for entry in auth_journal}),
            "balances": read_target(url, "state")["balances"],
        },
        "assurance_limit": (
            "Ed25519 signature verifies possession of an ephemeral test key under "
            "a locally provisioned public-key registry. No PKI, mTLS, attestation, "
            "independent operator trust, complete ACS mediation, or compromise-resistant "
            "server and state; direct correctly signed requests can bypass ACS."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Real ACS with Ed25519 target-bound commit study")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = Path(__file__).resolve().parents[2] / "tests/fixtures/acs_effect/manifest.yaml"
    if not manifest.is_file():
        raise SystemExit("requires editable repository with ACS test fixtures")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="acs-signed-target-") as temp:
        database = Path(temp) / "authenticated.sqlite3"
        with signed_target(database) as (url, signer, aud):
            report = asyncio.run(run_study(manifest, url, database, signer, aud))
    args.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: {report['case_count']} actual ACS + Ed25519 target cases")
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
