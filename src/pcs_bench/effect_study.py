"""Reproducible disposable effect-boundary experiment and JSON report.

This study uses a test broker and test target, not AGT, OpenShell, or PF runtime.
The target journal is authoritative for this particular disposable service; it
is not an independently authenticated or exhaustive real-world effect oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from pcs_bench.effect_boundary import Action, Policy, decide, dispatch, post_commit, read_target


@contextmanager
def disposable_target(database: Path) -> Iterator[str]:
    env = os.environ.copy()
    with subprocess.Popen(
        [sys.executable, "-m", "pcs_bench.effect_target", "--database", str(database)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    ) as proc:
        try:
            assert proc.stdout is not None
            ready, _, _ = select.select([proc.stdout], [], [], 15)
            if not ready:
                raise RuntimeError("disposable target startup timeout")
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError(f"disposable target terminated: {proc.poll()}")
            port = json.loads(line)["port"]
            yield f"http://127.0.0.1:{port}"
        finally:
            proc.terminate()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_study(database: Path) -> dict[str, object]:
    baseline = Action("baseline-allowed", "agent-1", "tenant-a", "account:a", 5)
    policy = Policy("agent-1", "tenant-a", ("account:a",), 10, 7)
    cases: list[dict[str, object]] = []

    with disposable_target(database) as url:
        def record(
            case: str,
            *,
            authorized: bool,
            outcome: str,
            count_delta: int,
            notes: str,
            before: int,
            expected_outcome: str,
        ) -> None:
            journal = read_target(url, "journal")["effects"]
            observed_delta = len(journal) - before
            cases.append({
                "case": case,
                "authorized_at_policy": authorized,
                "gateway_or_target_outcome": outcome,
                "expected_new_commits": count_delta,
                "expected_outcome": expected_outcome,
                "observed_new_commits": observed_delta,
                "matches_expected": observed_delta == count_delta and outcome == expected_outcome,
                "interpretation": notes,
            })

        def count() -> int:
            return len(read_target(url, "journal")["effects"])

        before = count()
        allowed = decide(baseline, policy)
        completed = dispatch(url, baseline, allowed, policy)
        record("EFFECT-01-authorized-commit", authorized=True, outcome=completed.status,
               count_delta=1, before=before, expected_outcome="committed",
               notes="Target ledger records permitted write")

        before = count()
        denied_action = replace(baseline, operation_id="policy-denied", delta=100)
        denied_decision = decide(denied_action, policy)
        denied = dispatch(url, denied_action, denied_decision, policy)
        record("EFFECT-02-denied-no-commit", authorized=False, outcome=denied.status,
               count_delta=0, before=before, expected_outcome="blocked",
               notes="Cooperative broker does not dispatch denial")

        before = count()
        mutated_action = replace(baseline, operation_id="mutated", delta=7)
        mutated_approval = decide(replace(mutated_action, delta=5), policy)
        mutated = dispatch(url, mutated_action, mutated_approval, policy)
        record("EFFECT-03-argument-binding", authorized=False, outcome=mutated.status,
               count_delta=0, before=before, expected_outcome="blocked",
               notes="Modified request not bound to original verdict")

        before = count()
        revoked_action = replace(baseline, operation_id="revoked")
        revoked_approval = decide(revoked_action, policy)
        revoked = dispatch(
            url, revoked_action, revoked_approval, replace(policy, epoch=8, revoked=True)
        )
        record("EFFECT-04-revocation-recheck", authorized=False, outcome=revoked.status,
               count_delta=0, before=before, expected_outcome="blocked",
               notes="Current policy epoch blocks stale approval")

        before = count()
        ambiguous_action = replace(baseline, operation_id="response-lost")
        ambiguous_approval = decide(ambiguous_action, policy)
        ambiguous = dispatch(
            url, ambiguous_action, ambiguous_approval, policy, drop_reply_after_commit=True
        )
        record("EFFECT-05-commit-response-lost", authorized=True, outcome=ambiguous.status,
               count_delta=1, before=before, expected_outcome="unknown",
               notes="Client outcome unknown although target ledger contains commit")

        before = count()
        retry = dispatch(url, ambiguous_action, ambiguous_approval, policy)
        record("EFFECT-06-idempotent-retry", authorized=True, outcome=retry.status,
               count_delta=0, before=before, expected_outcome="deduplicated",
               notes="Same operation identity is deduplicated")

        before = count()
        collision_action = replace(ambiguous_action, delta=9)
        code, receipt = post_commit(url, collision_action)
        record("EFFECT-07-idempotency-collision", authorized=False,
               outcome=f"http_{code}:{receipt.get('error')}", count_delta=0, before=before,
               expected_outcome="http_409:idempotency_collision",
               notes="Target rejects same key with changed payload")

        before = count()
        unmediated_action = replace(baseline, operation_id="bypass", delta=100)
        code, receipt = post_commit(url, unmediated_action)
        record("EFFECT-08-unmediated-bypass", authorized=False,
               outcome=f"http_{code}:{receipt.get('status')}", count_delta=1, before=before,
               expected_outcome="http_200:committed",
               notes="Deliberately open target allows direct call past cooperative broker")

        before = count()
        different_key = replace(baseline, operation_id="fresh-key-repeat")
        fresh_result = dispatch(url, different_key, decide(different_key, policy), policy)
        record("EFFECT-09-new-key-duplicate-effect", authorized=True,
               outcome=fresh_result.status, count_delta=1, before=before,
               expected_outcome="committed",
               notes="Fresh idempotency key permits another identical effect")

        journal = read_target(url, "journal")["effects"]
        state = read_target(url, "state")["balances"]
        observed = {
            "number_of_commits": len(journal),
            "final_balances": state,
            "operation_ids": [entry["operation_id"] for entry in journal],
        }

    base = Path(__file__).resolve().parent
    result = {
        "protocol": "agent-effect-boundary-study-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_digests": {
            "effect_boundary.py": _digest_file(base / "effect_boundary.py"),
            "effect_target.py": _digest_file(base / "effect_target.py"),
            "effect_study.py": _digest_file(Path(__file__).resolve()),
        },
        "environment": {"python": sys.version.split()[0], "target": "local SQLite HTTP process"},
        "status": "pass" if all(item["matches_expected"] for item in cases) else "fail",
        "case_count": len(cases),
        "cases": cases,
        "target_side_state": observed,
        "assurance_limit": (
            "This is a local controlled study with a deliberately unguarded target. "
            "It does not demonstrate a PF/AGT/OpenShell vulnerability, authentic "
            "real-world evidence, complete mediation, or Lean theorem verification."
        ),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run disposable effect-boundary study")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agent-effect-study-") as temp:
        result = run_study(Path(temp) / "target.sqlite3")
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"{result['status']}: {result['case_count']} source-grounded cases -> {args.out}")
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
