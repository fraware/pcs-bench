"""Real ACS policy and independently enforced target-commit laboratory.

Native ACS/Cedar/Agent Hooks makes the host decision. The target consults its
own SQLite policy inside the same transaction as the durable effect. Identity
and operator authority remain local fixtures, not production credentials.
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

from pcs_bench.acs_effect_host import AcsAuthorization, AcsEffectHost
from pcs_bench.effect_boundary import Action, action_digest, read_target
from pcs_bench.guarded_target import operator_update


@contextmanager
def guarded_server(database: Path) -> Iterator[str]:
    process = subprocess.Popen(
        [sys.executable, "-m", "pcs_bench.guarded_target", "--database", str(database)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy(),
    )
    try:
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 15)
        if not ready:
            raise RuntimeError("target startup deadline exceeded")
        info = process.stdout.readline()
        if not info:
            raise RuntimeError(f"guarded target exited: {process.poll()}")
        yield f"http://127.0.0.1:{json.loads(info)['port']}"
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def post(url: str, endpoint: str, data: dict[str, object]) -> tuple[int, dict[str, Any]]:
    req = Request(
        url.rstrip("/") + endpoint, method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(data, separators=(",", ":")).encode(),
    )
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read(32768))
    except HTTPError as error:
        return error.code, json.loads(error.read(32768))


class GuardedAcsHost(AcsEffectHost):
    """Real ACS enforcing adapter for staged protocol, not a production PEP."""

    async def stage(
        self, url: str, action: Action, authorization: AcsAuthorization
    ) -> tuple[int, dict[str, Any]]:
        if not authorization.permitted:
            return 403, {"error": "acs_denied"}
        if authorization.request_digest != action_digest(action):
            return 409, {"error": "action_changed_after_acs"}
        if authorization.policy_epoch != self.epoch:
            return 409, {"error": "host_policy_epoch_changed"}
        permitted, reason = await self._evaluate(action, attempt="stage")
        if not permitted:
            return 403, {"error": f"acs_{reason}"}
        return post(url, "/stage", action.to_dict())


async def run_study(manifest: Path, url: str, database: Path) -> dict[str, Any]:
    from agent_control_spec import __version__ as acs_version

    host = GuardedAcsHost(manifest, epoch=1, legacy_cedar_principal_bridge=True)
    cases: list[dict[str, Any]] = []

    def count() -> int:
        return len(read_target(url, "journal")["effects"])

    def record(case: str, before: int, code: int, response: dict[str, Any],
               expected_code: int, expected_effects: int, expected_status: str) -> None:
        effect_delta = count() - before
        actual_status = response.get("status", response.get("error"))
        cases.append({
            "case": case,
            "expected_http": expected_code,
            "actual_http": code,
            "expected_outcome": expected_status,
            "actual_outcome": actual_status,
            "expected_new_effects": expected_effects,
            "observed_new_effects": effect_delta,
            "pass": (code, actual_status, effect_delta) == (
                expected_code, expected_status, expected_effects
            ),
        })

    action1 = Action("guarded-allowed", "agent-1", "tenant-a", "account:a", 5)
    granted = await host.authorize(action1)
    if not granted.permitted:
        raise RuntimeError(f"native ACS denied permitted fixture: {granted.reason}")
    before = count()
    scode, stage = await host.stage(url, action1, granted)
    if scode != 202:
        raise RuntimeError(f"target could not stage permitted action: {stage}")
    code, result = post(url, "/commit-staged", {
        "operation_id": action1.operation_id, "request_digest": stage["request_digest"]
    })
    record("ACST-01-real-acs-commit", before, code, result, 200, 1, "committed")

    forbidden = replace(action1, operation_id="guarded-denied", delta=50)
    forbidden_decision = await host.authorize(forbidden)
    if forbidden_decision.permitted:
        raise RuntimeError("Cedar unexpectedly permitted prohibited action")
    before = count()
    code, result = await host.stage(url, forbidden, forbidden_decision)
    record("ACST-02-acs-denies", before, code, result, 403, 0, "acs_denied")

    action2 = replace(action1, operation_id="guarded-revoked", delta=4)
    approval2 = await host.authorize(action2)
    scode, stage2 = await host.stage(url, action2, approval2)
    if scode != 202:
        raise RuntimeError(f"could not stage revocation fixture: {stage2}")
    before = count()
    code, result = post(url, "/commit-staged", {
        "operation_id": action2.operation_id,
        "request_digest": action_digest(replace(action2, delta=7)),
    })
    record("ACST-03-stage-tampering", before, code, result, 409, 0, "stage_digest_mismatch")

    operator_update(database, next_epoch=2, revoked=True)
    before = count()
    code, result = post(url, "/commit-staged", {
        "operation_id": action2.operation_id, "request_digest": stage2["request_digest"]
    })
    record("ACST-04-revocation-before-commit", before, code, result, 403, 0, "revoked")

    operator_update(database, next_epoch=3, revoked=False)
    before = count()
    code, result = post(url, "/commit-staged", {
        "operation_id": action2.operation_id, "request_digest": stage2["request_digest"]
    })
    record("ACST-05-old-stage-after-regrant", before, code, result,
           409, 0, "stage_policy_epoch_stale")

    host.change_policy_state(epoch=3, revoked=False)
    action3 = replace(action1, operation_id="guarded-regrant", delta=4)
    approval3 = await host.authorize(action3)
    before = count()
    scode, s3 = await host.stage(url, action3, approval3)
    if scode != 202:
        raise RuntimeError(f"could not stage new policy epoch action: {s3}")
    code, result = post(url, "/commit-staged", {
        "operation_id": action3.operation_id, "request_digest": s3["request_digest"]
    })
    record("ACST-06-regrant-new-stage", before, code, result, 200, 1, "committed")

    operator_update(database, next_epoch=4, revoked=True)
    before = count()
    code, result = post(url, "/commit-staged", {
        "operation_id": action1.operation_id, "request_digest": stage["request_digest"]
    })
    record("ACST-07-historical-idempotent-replay", before, code, result,
           200, 0, "deduplicated")

    before = count()
    code, result = post(url, "/commit", replace(
        action1, operation_id="guarded-revoked-direct"
    ).to_dict())
    record("ACST-08-unmediated-revoked-request", before, code, result, 403, 0, "revoked")

    operator_update(database, next_epoch=5, revoked=False)
    before = count()
    code, result = post(url, "/commit", replace(
        action1, operation_id="guarded-forged-identity", delta=2
    ).to_dict())
    record("ACST-09-self-asserted-identity-gap", before, code, result, 200, 1, "committed")

    journal = read_target(url, "journal")["effects"]
    return {
        "protocol": "acs-guarded-effect-study-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "pass" if all(case["pass"] for case in cases) else "fail",
        "case_count": len(cases),
        "cases": cases,
        "acs": {"package_version": acs_version, "policy_backend": "Cedar",
                "manifest_sha256": host.manifest_sha256,
                "cedar_sha256": host.cedar_sha256,
                "legacy_principal_bridge": True},
        "target": {"effects": len(journal),
                   "balances": read_target(url, "state")["balances"],
                   "effect_epochs": [entry["commit_epoch"] for entry in journal]},
        "assurance_limit": (
            "SQLite-authoritative local operator and policy state, not a separately "
            "authenticated identity provider; agent identity is caller-asserted at HTTP "
            "boundary; direct authorized effects bypass ACS; no remote attestation, "
            "production enforcement guarantee or formal proof of complete mediation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ACS/target-owned commit-time policy study")
    parser.add_argument("--out", required=True, type=Path)
    options = parser.parse_args()
    manifest = Path(__file__).resolve().parents[2] / "tests/fixtures/acs_effect/manifest.yaml"
    if not manifest.is_file():
        raise SystemExit("ACS manifest unavailable; run from editable checkout")
    options.out.parent.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="acs-guarded-study-") as temp,
        guarded_server(Path(temp) / "authority.sqlite3") as url,
    ):
        report = asyncio.run(run_study(manifest, url, Path(temp) / "authority.sqlite3"))
    options.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{report['status']}: {report['case_count']} real ACS/target-policy cases -> {options.out}")
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
