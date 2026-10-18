"""Disposable target with atomically enforced, target-owned policy state.

Research model: an operator with trusted *local SQLite access* updates policy.
An untrusted HTTP caller cannot change policy through this service. Principal
identities on HTTP requests remain self-asserted, so this is NOT a complete
identity, network isolation, or production authorization system.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from pcs_bench.effect_boundary import Action, action_digest

MAX_BODY = 8192


def db_connect(database: Path) -> sqlite3.Connection:
    con = sqlite3.connect(database, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    return con


def initialize(database: Path) -> None:
    """Provision a fixed lab policy directly, never through untrusted HTTP."""
    with db_connect(database) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(
            "CREATE TABLE IF NOT EXISTS authority ("
            "singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
            "epoch INTEGER NOT NULL, revoked INTEGER NOT NULL, "
            "principal TEXT NOT NULL, tenant TEXT NOT NULL, resource TEXT NOT NULL, "
            "max_delta INTEGER NOT NULL)"
        )
        con.execute(
            "INSERT OR IGNORE INTO authority VALUES(1,1,0,'agent-1','tenant-a','account:a',10)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS staged ("
            "operation_id TEXT PRIMARY KEY, digest TEXT NOT NULL, "
            "principal TEXT NOT NULL, tenant TEXT NOT NULL, resource TEXT NOT NULL, "
            "delta INTEGER NOT NULL, stage_epoch INTEGER NOT NULL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS effects ("
            "operation_id TEXT PRIMARY KEY, digest TEXT NOT NULL, "
            "resource TEXT NOT NULL, delta INTEGER NOT NULL, "
            "commit_epoch INTEGER NOT NULL, committed_at TEXT NOT NULL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS balances ("
            "resource TEXT PRIMARY KEY, balance INTEGER NOT NULL)"
        )


def operator_update(
    database: Path,
    *,
    next_epoch: int,
    revoked: bool,
    max_delta: int = 10,
    resource: str = "account:a",
) -> None:
    """Test operator direct file access; no HTTP administrative endpoint.

    Policy writes serialize with effects using BEGIN IMMEDIATE, establishing
    a single database order for update and commit, not distributed consensus.
    """
    if type(next_epoch) is not int or next_epoch <= 0:
        raise ValueError("invalid epoch")
    if type(revoked) is not bool or type(max_delta) is not int or max_delta < 0:
        raise ValueError("invalid operator policy")
    if not isinstance(resource, str) or not resource:
        raise ValueError("invalid operator resource")
    with db_connect(database) as con:
        try:
            con.execute("BEGIN IMMEDIATE")
            state = con.execute("SELECT epoch FROM authority WHERE singleton=1").fetchone()
            if state is None or next_epoch <= state["epoch"]:
                raise ValueError("epoch must increase monotonically")
            con.execute(
                "UPDATE authority SET epoch=?, revoked=?, max_delta=?, resource=? "
                "WHERE singleton=1",
                (next_epoch, int(revoked), max_delta, resource),
            )
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise


def decode_action(body: object) -> Action:
    if not isinstance(body, dict) or set(body) != {
        "operation_id", "principal", "tenant", "resource", "delta"
    }:
        raise ValueError("invalid action fields")
    if any(type(body[k]) is not str or not body[k] for k in (
        "operation_id", "principal", "tenant", "resource"
    )):
        raise ValueError("invalid action identity")
    if type(body["delta"]) is not int or abs(body["delta"]) > 1_000_000:
        raise ValueError("invalid action delta")
    return Action(**body)


def allowed(action: Action, policy: sqlite3.Row) -> str | None:
    """Target-owned authorization rules; principal remains self-asserted."""
    if policy["revoked"]:
        return "revoked"
    if action.principal != policy["principal"]:
        return "principal_mismatch"
    if action.tenant != policy["tenant"]:
        return "tenant_mismatch"
    if action.resource != policy["resource"]:
        return "resource_mismatch"
    if action.delta < 0 or action.delta > policy["max_delta"]:
        return "amount_not_granted"
    return None


def _commit_in_tx(con: sqlite3.Connection, action: Action, epoch: int) -> dict[str, object]:
    digest = action_digest(action)
    con.execute(
        "INSERT INTO balances(resource,balance) VALUES(?,?) "
        "ON CONFLICT(resource) DO UPDATE SET balance=balance+excluded.balance",
        (action.resource, action.delta),
    )
    con.execute(
        "INSERT INTO effects VALUES(?,?,?,?,?,?)",
        (action.operation_id, digest, action.resource, action.delta,
         epoch, datetime.now(UTC).isoformat()),
    )
    return {"status": "committed", "operation_id": action.operation_id,
            "request_digest": digest, "commit_epoch": epoch}


def process(database: Path, route: str, payload: object) -> tuple[int, dict[str, object]]:
    """All effect decisions and writes are serialized under one transaction."""
    if route not in ("/stage", "/commit-staged", "/commit"):
        return 404, {"error": "unknown_route"}
    try:
        if route in ("/stage", "/commit"):
            action = decode_action(payload)
            digest = action_digest(action)
        else:
            if not isinstance(payload, dict) or set(payload) != {"operation_id", "request_digest"}:
                raise ValueError("invalid stage receipt")
            if any(type(payload[k]) is not str or not payload[k] for k in payload):
                raise ValueError("invalid stage receipt")
            if len(payload["request_digest"]) != 64 or any(
                c not in "0123456789abcdef" for c in payload["request_digest"]
            ):
                raise ValueError("invalid stage digest")
    except (ValueError, TypeError, KeyError):
        return 400, {"error": "invalid_request"}

    with db_connect(database) as con:
        try:
            con.execute("BEGIN IMMEDIATE")
            state = con.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
            if state is None:
                raise RuntimeError("target authority not initialized")
            if route == "/commit-staged":
                stage = con.execute("SELECT * FROM staged WHERE operation_id=?",
                                    (payload["operation_id"],)).fetchone()
                if stage is None:
                    return 404, {"error": "stage_not_found"}
                if stage["digest"] != payload["request_digest"]:
                    return 409, {"error": "stage_digest_mismatch"}
                action = Action(stage["operation_id"], stage["principal"],
                                stage["tenant"], stage["resource"], stage["delta"])
                digest = action_digest(action)
                if digest != stage["digest"]:
                    raise RuntimeError("corrupt stage record")
            previous = con.execute("SELECT * FROM effects WHERE operation_id=?",
                                   (action.operation_id,)).fetchone()
            if previous is not None:
                if previous["digest"] != digest:
                    return 409, {"error": "idempotency_collision"}
                return 200, {"status": "deduplicated", "operation_id": action.operation_id,
                             "request_digest": digest, "commit_epoch": previous["commit_epoch"]}
            reason = allowed(action, state)
            if reason:
                return 403, {"error": reason, "policy_epoch": state["epoch"]}
            if route == "/stage":
                prior = con.execute("SELECT * FROM staged WHERE operation_id=?",
                                    (action.operation_id,)).fetchone()
                if prior is not None:
                    if prior["digest"] != digest:
                        return 409, {"error": "staged_operation_collision"}
                    return 200, {"status": "staged_existing", "operation_id": action.operation_id,
                                 "request_digest": digest, "stage_epoch": prior["stage_epoch"]}
                con.execute("INSERT INTO staged VALUES(?,?,?,?,?,?,?)",
                            (action.operation_id, digest, action.principal,
                             action.tenant, action.resource, action.delta, state["epoch"]))
                con.execute("COMMIT")
                return 202, {"status": "staged", "operation_id": action.operation_id,
                             "request_digest": digest, "stage_epoch": state["epoch"]}
            if route == "/commit-staged" and stage["stage_epoch"] != state["epoch"]:
                return 409, {"error": "stage_policy_epoch_stale", "policy_epoch": state["epoch"]}
            receipt = _commit_in_tx(con, action, state["epoch"])
            con.execute("COMMIT")
            return 200, receipt
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise


def snapshot(database: Path, route: str) -> dict[str, object]:
    with db_connect(database) as con:
        if route == "/journal":
            rows = con.execute(
                "SELECT operation_id,digest,resource,delta,commit_epoch,committed_at "
                "FROM effects ORDER BY operation_id"
            ).fetchall()
            return {"effects": [dict(row) for row in rows]}
        rows = con.execute("SELECT resource,balance FROM balances ORDER BY resource").fetchall()
        return {"balances": {row["resource"]: row["balance"] for row in rows}}


def make_handler(database: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def reply(self, status: int, payload: dict[str, object]) -> None:
            encoded = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            route = urlsplit(self.path).path
            if route in ("/state", "/journal"):
                self.reply(200, snapshot(database, route))
            elif route == "/health":
                self.reply(200, {"status": "ready"})
            else:
                self.reply(404, {"error": "unknown_route"})

        def do_POST(self) -> None:
            route = urlsplit(self.path).path
            size = self.headers.get("Content-Length", "")
            if not size.isascii() or not size.isdecimal() or not 0 < int(size) <= MAX_BODY:
                self.reply(400, {"error": "invalid_body_size"})
                return
            try:
                body = json.loads(self.rfile.read(int(size)))
            except (ValueError, UnicodeError):
                self.reply(400, {"error": "invalid_json"})
                return
            status, receipt = process(database, route, body)
            self.reply(status, receipt)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Disposable target with commit-time policy")
    parser.add_argument("--database", required=True, type=Path)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    initialize(args.database)
    with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(args.database)) as server:
        print(json.dumps({"port": server.server_port}), flush=True)
        server.serve_forever(poll_interval=0.1)


if __name__ == "__main__":
    main()
