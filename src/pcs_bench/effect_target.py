"""Disposable target-side effect oracle for local agent-governance experiments.

A process-local HTTP server persists committed actions in a separate SQLite
file. It intentionally does NOT enforce agent policy: direct callers can bypass
an application-level broker, which is the phenomenon under evaluation.
Never expose this research server beyond the loopback interface.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from pcs_bench.effect_boundary import Action, action_digest

MAX_BODY = 8192


def _db(database: Path) -> sqlite3.Connection:
    con = sqlite3.connect(database, timeout=5, isolation_level=None)
    con.row_factory = sqlite3.Row
    return con


def initialize(database: Path) -> None:
    with _db(database) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(
            "CREATE TABLE IF NOT EXISTS effects ("
            "operation_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, "
            "principal TEXT NOT NULL, tenant TEXT NOT NULL, resource TEXT NOT NULL, "
            "delta INTEGER NOT NULL, committed_at TEXT NOT NULL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS balances ("
            "resource TEXT PRIMARY KEY, balance INTEGER NOT NULL)"
        )


def commit(database: Path, action: Action) -> tuple[int, dict[str, object]]:
    """Atomically bind an idempotency key and update a durable target resource."""
    if not all((action.operation_id, action.principal, action.tenant, action.resource)):
        return 400, {"error": "missing_action_identity"}
    if (
        not isinstance(action.delta, int)
        or isinstance(action.delta, bool)
        or abs(action.delta) > 1_000_000
    ):
        return 400, {"error": "invalid_delta"}
    digest = action_digest(action)
    with _db(database) as con:
        try:
            con.execute("BEGIN IMMEDIATE")
            old = con.execute(
                "SELECT request_digest FROM effects WHERE operation_id=?", (action.operation_id,)
            ).fetchone()
            if old:
                if old["request_digest"] != digest:
                    con.execute("ROLLBACK")
                    return 409, {"error": "idempotency_collision"}
                balance = con.execute(
                    "SELECT balance FROM balances WHERE resource=?", (action.resource,)
                ).fetchone()
                con.execute("COMMIT")
                return 200, {
                    "status": "deduplicated",
                    "operation_id": action.operation_id,
                    "request_digest": digest,
                    "balance": balance["balance"] if balance else None,
                }
            con.execute(
                "INSERT INTO balances(resource,balance) VALUES(?,?) "
                "ON CONFLICT(resource) DO UPDATE SET balance=balance+excluded.balance",
                (action.resource, action.delta),
            )
            con.execute(
                "INSERT INTO effects VALUES(?,?,?,?,?,?,?)",
                (
                    action.operation_id,
                    digest,
                    action.principal,
                    action.tenant,
                    action.resource,
                    action.delta,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            con.execute("COMMIT")
            balance = con.execute(
                "SELECT balance FROM balances WHERE resource=?", (action.resource,)
            ).fetchone()
            return 200, {
                "status": "committed",
                "operation_id": action.operation_id,
                "request_digest": digest,
                "balance": balance["balance"],
            }
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise


def snapshot(database: Path, kind: str) -> dict[str, object]:
    with _db(database) as con:
        if kind == "journal":
            rows = con.execute(
                "SELECT operation_id,request_digest,principal,tenant,resource,delta,committed_at "
                "FROM effects ORDER BY operation_id"
            ).fetchall()
            return {"effects": [dict(row) for row in rows]}
        rows = con.execute("SELECT resource,balance FROM balances ORDER BY resource").fetchall()
        return {"balances": {row["resource"]: row["balance"] for row in rows}}


def make_handler(database: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return  # Avoid leaking test action inputs to stdout.

        def _reply(self, code: int, payload: dict[str, object]) -> None:
            raw = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            route = urlsplit(self.path).path
            if route in ("/journal", "/state"):
                self._reply(200, snapshot(database, route[1:]))
            elif route == "/health":
                self._reply(200, {"status": "ready"})
            else:
                self._reply(404, {"error": "unknown_route"})

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/commit":
                self._reply(404, {"error": "unknown_route"})
                return
            size = self.headers.get("Content-Length", "")
            if not size.isascii() or not size.isdecimal() or not 0 < int(size) <= MAX_BODY:
                self._reply(400, {"error": "invalid_body_size"})
                return
            try:
                data = json.loads(self.rfile.read(int(size)))
                if not isinstance(data, dict):
                    raise ValueError("expected object")
                expected = {
                    "operation_id", "principal", "tenant", "resource", "delta",
                    "drop_reply_after_commit",
                }
                if set(data) - expected:
                    raise ValueError("unexpected properties")
                action = Action(**{key: data[key] for key in expected - {"drop_reply_after_commit"}})
                if any(not isinstance(value, str) for value in (
                    action.operation_id, action.principal, action.tenant, action.resource
                )):
                    raise ValueError("invalid action identity types")
                drop = data.get("drop_reply_after_commit", False)
                if not isinstance(drop, bool):
                    raise ValueError("invalid fault flag")
                status, receipt = commit(database, action)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                self._reply(400, {"error": "invalid_action"})
                return
            if drop and status == 200:
                # Simulates a transport failure AFTER a durable commit.
                self.close_connection = True
                self.connection.shutdown(2)
                return
            self._reply(status, receipt)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-only disposable effect target")
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    initialize(args.database)
    with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(args.database)) as server:
        print(json.dumps({"port": server.server_port}), flush=True)
        server.serve_forever(poll_interval=0.1)


if __name__ == "__main__":
    main()
