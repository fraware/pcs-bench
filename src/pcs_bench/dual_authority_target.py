"""Two-root experimental authorization at the final target commit boundary.

Only locally enrolled actor keys authenticate requests. An independently
enrolled policy-issuer key authenticates an *allow* decision. The target checks
both signatures, the action digest, key IDs, target audience, pinned policy
digest, current policy epoch, and policy/issuer/key revocation before inserting
an effect in one SQLite write transaction.

Important: a signature from a trusted issuer is NOT cryptographic evidence
that ACS actually ran. Issuer conduct, keys, local database and clock remain
trusted assumptions; this is a local research target, not production authn.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from pcs_bench.authenticated_target import (
    CLOCK_SKEW,
    MAX_BODY,
    _bytes as actor_bytes,
    _preflight as actor_preflight,
    _reject_constant,
    _strict_object,
    audience,
    authenticated_process,
    initialize as initialize_actor,
)
from pcs_bench.effect_boundary import Action, action_digest
from pcs_bench.guarded_target import _commit_in_tx, allowed, db_connect, snapshot

DECISION_VERSION = "pcs-bench-issuer-decision-v1"
DECISION_DOMAIN = b"pcs-bench-issuer-decision-v1\x00"


def decision_bytes(statement: dict[str, Any]) -> bytes:
    """Version-local canonical bytes, NOT generic JSON/JCS canonicalization."""
    return DECISION_DOMAIN + json.dumps(
        statement, sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")


def initialize(database: Path) -> None:
    initialize_actor(database)
    with db_connect(database) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS policy_issuers ("
            "issuer_id TEXT PRIMARY KEY, public_key BLOB NOT NULL, "
            "policy_hash TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS committed_decisions ("
            "issuer_id TEXT NOT NULL, decision_id TEXT NOT NULL, "
            "operation_id TEXT NOT NULL, request_digest TEXT NOT NULL, "
            "PRIMARY KEY(issuer_id, decision_id))"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS decision_effects ("
            "operation_id TEXT PRIMARY KEY, issuer_id TEXT NOT NULL, "
            "decision_id TEXT NOT NULL, actor_key_id TEXT NOT NULL)"
        )


def register_policy_issuer(
    database: Path, *, issuer_id: str, public_key: bytes, policy_sha256: str,
) -> None:
    """Trusted operator action, absent from HTTP; fails on duplicate issuer ID."""
    if not isinstance(issuer_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", issuer_id):
        raise ValueError("invalid issuer ID")
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise ValueError("invalid issuer public key")
    Ed25519PublicKey.from_public_bytes(public_key)
    if not isinstance(policy_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", policy_sha256):
        raise ValueError("invalid policy digest")
    with db_connect(database) as con:
        con.execute(
            "INSERT INTO policy_issuers VALUES(?,?,?,0)",
            (issuer_id, public_key, policy_sha256),
        )


def revoke_policy_issuer(database: Path, issuer_id: str) -> None:
    with db_connect(database) as con:
        con.execute("BEGIN IMMEDIATE")
        result = con.execute(
            "UPDATE policy_issuers SET revoked=1 WHERE issuer_id=?", (issuer_id,)
        )
        if result.rowcount != 1:
            raise ValueError("unknown policy issuer")
        con.execute("COMMIT")


def sign_decision(
    private_key: Ed25519PrivateKey, *,
    issuer_id: str,
    target_audience: str,
    actor_key_id: str,
    action: Action,
    policy_sha256: str,
    policy_epoch: int,
    issued_at: int | None = None,
    expires_at: int | None = None,
    decision_id: str | None = None,
) -> dict[str, object]:
    """Laboratory issuer constructor; caller must check actual ACS policy first."""
    now = int(time.time()) if issued_at is None else issued_at
    statement: dict[str, object] = {
        "version": DECISION_VERSION,
        "issuer_id": issuer_id,
        "audience": target_audience,
        "actor_key_id": actor_key_id,
        "principal": action.principal,
        "tenant": action.tenant,
        "action_digest": action_digest(action),
        "policy_sha256": policy_sha256,
        "policy_epoch": policy_epoch,
        "decision_id": decision_id or secrets.token_hex(16),
        "issued_at": now,
        "expires_at": now + 30 if expires_at is None else expires_at,
        "verdict": "allow",
    }
    signature = private_key.sign(decision_bytes(statement))
    return {
        "statement": statement,
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }


def _signature(value: object) -> bytes | None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{86}", value):
        return None
    try:
        signature = base64.b64decode(value + "==", altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        return None
    return signature if len(signature) == 64 else None


def _decision_preflight(value: object) -> tuple[dict[str, Any], bytes] | None:
    if not isinstance(value, dict) or set(value) != {"statement", "signature"}:
        return None
    stmt = value["statement"]
    if not isinstance(stmt, dict) or set(stmt) != {
        "version", "issuer_id", "audience", "actor_key_id", "principal", "tenant",
        "action_digest", "policy_sha256", "policy_epoch", "decision_id",
        "issued_at", "expires_at", "verdict",
    }:
        return None
    if stmt["version"] != DECISION_VERSION or stmt["verdict"] != "allow":
        return None
    for key in ("issuer_id", "actor_key_id"):
        if not isinstance(stmt[key], str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", stmt[key]):
            return None
    for key in ("audience", "principal", "tenant"):
        if not isinstance(stmt[key], str) or not stmt[key]:
            return None
    for key in ("action_digest", "policy_sha256"):
        if not isinstance(stmt[key], str) or not re.fullmatch(r"[0-9a-f]{64}", stmt[key]):
            return None
    if not isinstance(stmt["decision_id"], str) or not re.fullmatch(
        r"[0-9a-f]{32}", stmt["decision_id"]
    ):
        return None
    if type(stmt["policy_epoch"]) is not int or stmt["policy_epoch"] < 1:
        return None
    if type(stmt["issued_at"]) is not int or type(stmt["expires_at"]) is not int:
        return None
    if not 0 < stmt["expires_at"] - stmt["issued_at"] <= 60:
        return None
    decoded = _signature(value["signature"])
    if decoded is None:
        return None
    try:
        decision_bytes(stmt)
    except (TypeError, ValueError, OverflowError):
        return None
    return stmt, decoded


def appraise_and_commit(
    database: Path, route: str, packet: object
) -> tuple[int, dict[str, object]]:
    """Require independent actor and policy issuer at the same commit boundary."""
    if route not in ("/commit", "/commit-staged"):
        return 404, {"error": "unsupported_effect_route"}
    if not isinstance(packet, dict) or set(packet) != {"actor", "authorization"}:
        return 403, {"error": "policy_authorization_required"}
    actor = actor_preflight(route, packet["actor"])
    authorization = _decision_preflight(packet["authorization"])
    if actor is None or authorization is None:
        return 400, {"error": "invalid_dual_signature_envelope"}
    actor_stmt, actor_sig = actor
    decision, issuer_sig = authorization
    with db_connect(database) as con:
        con.execute("BEGIN IMMEDIATE")
        now = int(time.time())
        if (actor_stmt["issued_at"] > now + CLOCK_SKEW
                or actor_stmt["expires_at"] < now
                or decision["issued_at"] > now + CLOCK_SKEW
                or decision["expires_at"] < now):
            return 401, {"error": "expired_or_future_authority"}
        target = con.execute(
            "SELECT audience FROM auth_metadata WHERE singleton=1"
        ).fetchone()
        if (target is None or actor_stmt["audience"] != target["audience"]
                or decision["audience"] != target["audience"]):
            return 401, {"error": "wrong_target_audience"}
        actor_key = con.execute(
            "SELECT * FROM auth_keys WHERE key_id=?", (actor_stmt["key_id"],)
        ).fetchone()
        issuer = con.execute(
            "SELECT * FROM policy_issuers WHERE issuer_id=?", (decision["issuer_id"],)
        ).fetchone()
        if actor_key is None or issuer is None:
            return 401, {"error": "untrusted_actor_or_issuer"}
        if actor_key["revoked"] or issuer["revoked"]:
            return 403, {"error": "actor_or_issuer_revoked"}
        if actor_key["public_key"] == issuer["public_key"]:
            return 403, {"error": "independent_signer_required"}
        try:
            Ed25519PublicKey.from_public_bytes(actor_key["public_key"]).verify(
                actor_sig, actor_bytes(actor_stmt)
            )
            Ed25519PublicKey.from_public_bytes(issuer["public_key"]).verify(
                issuer_sig, decision_bytes(decision)
            )
        except (InvalidSignature, ValueError, TypeError):
            return 401, {"error": "invalid_actor_or_issuer_signature"}
        if decision["policy_sha256"] != issuer["policy_hash"]:
            return 403, {"error": "policy_digest_not_trusted"}
        if actor_stmt["key_id"] != decision["actor_key_id"]:
            return 403, {"error": "decision_actor_key_mismatch"}
        current = con.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        if current is None:
            raise RuntimeError("target policy was not initialized")
        if decision["policy_epoch"] != current["epoch"]:
            return 409, {"error": "authorization_policy_epoch_stale"}
        actor_nonce = con.execute(
            "SELECT 1 FROM auth_nonces WHERE key_id=? AND nonce=?",
            (actor_stmt["key_id"], actor_stmt["nonce"]),
        ).fetchone()
        if actor_nonce is not None:
            return 409, {"error": "actor_nonce_replayed"}
        body = actor_stmt["body"]
        if route == "/commit":
            try:
                from pcs_bench.guarded_target import decode_action

                action = decode_action(body)
            except (ValueError, TypeError, KeyError):
                return 400, {"error": "invalid_action"}
        else:
            if not isinstance(body, dict) or set(body) != {"operation_id", "request_digest"}:
                return 400, {"error": "invalid_stage_receipt"}
            if not isinstance(body["operation_id"], str) or not isinstance(
                body["request_digest"], str
            ):
                return 400, {"error": "invalid_stage_receipt"}
            stage = con.execute(
                "SELECT * FROM staged WHERE operation_id=?", (body["operation_id"],)
            ).fetchone()
            owner = con.execute(
                "SELECT * FROM auth_stages WHERE operation_id=?", (body["operation_id"],)
            ).fetchone()
            if stage is None or owner is None:
                return 404, {"error": "stage_not_found"}
            if owner["key_id"] != actor_stmt["key_id"]:
                return 403, {"error": "stage_actor_key_mismatch"}
            if stage["digest"] != body["request_digest"]:
                return 409, {"error": "stage_digest_mismatch"}
            action = Action(stage["operation_id"], stage["principal"], stage["tenant"],
                            stage["resource"], stage["delta"])
            if stage["stage_epoch"] != current["epoch"]:
                return 409, {"error": "staged_policy_epoch_stale"}
        digest = action_digest(action)
        if digest != decision["action_digest"]:
            return 403, {"error": "decision_action_mismatch"}
        if (action.principal != actor_key["principal"]
                or action.tenant != actor_key["tenant"]
                or decision["principal"] != action.principal
                or decision["tenant"] != action.tenant):
            return 403, {"error": "decision_identity_mismatch"}
        denied = allowed(action, current)
        if denied is not None:
            return 403, {"error": denied}
        prior_decision = con.execute(
            "SELECT * FROM committed_decisions WHERE issuer_id=? AND decision_id=?",
            (decision["issuer_id"], decision["decision_id"]),
        ).fetchone()
        if prior_decision is not None and (
            prior_decision["operation_id"] != action.operation_id
            or prior_decision["request_digest"] != digest
        ):
            return 409, {"error": "decision_id_reused"}
        previous = con.execute(
            "SELECT * FROM effects WHERE operation_id=?", (action.operation_id,)
        ).fetchone()
        if previous is not None and previous["digest"] != digest:
            return 409, {"error": "idempotency_collision"}
        # A committed logical effect is replayable only as a zero-effect
        # deduplication; the new actor nonce is still consumed below.
        con.execute(
            "INSERT INTO auth_nonces VALUES(?,?,?)",
            (actor_stmt["key_id"], actor_stmt["nonce"], actor_stmt["expires_at"]),
        )
        if prior_decision is None:
            con.execute(
                "INSERT INTO committed_decisions VALUES(?,?,?,?)",
                (decision["issuer_id"], decision["decision_id"], action.operation_id, digest),
            )
        if previous is None:
            result = _commit_in_tx(con, action, current["epoch"])
            con.execute(
                "INSERT INTO auth_effects VALUES(?,?,?,?)",
                (action.operation_id, actor_stmt["key_id"],
                 actor_stmt["nonce"], current["epoch"]),
            )
            con.execute(
                "INSERT INTO decision_effects VALUES(?,?,?,?)",
                (action.operation_id, decision["issuer_id"],
                 decision["decision_id"], actor_stmt["key_id"]),
            )
        else:
            result = {
                "status": "deduplicated", "operation_id": action.operation_id,
                "request_digest": digest, "commit_epoch": previous["commit_epoch"],
            }
        con.execute("COMMIT")
        return 200, result


def decision_snapshot(database: Path) -> dict[str, object]:
    with db_connect(database) as con:
        rows = con.execute(
            "SELECT e.operation_id,e.commit_epoch,d.issuer_id,d.decision_id,d.actor_key_id "
            "FROM effects e JOIN decision_effects d ON d.operation_id=e.operation_id "
            "ORDER BY e.operation_id"
        ).fetchall()
    return {"commits": [dict(row) for row in rows]}


def make_handler(database: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def respond(self, code: int, data: dict[str, object]) -> None:
            raw = json.dumps(data, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            route = urlsplit(self.path).path
            if route == "/identity":
                self.respond(200, {"audience": audience(database), "version": DECISION_VERSION})
            elif route == "/decision-journal":
                self.respond(200, decision_snapshot(database))
            elif route in ("/journal", "/state"):
                self.respond(200, snapshot(database, route))
            else:
                self.respond(404, {"error": "unknown_route"})

        def do_POST(self) -> None:
            route = urlsplit(self.path).path
            length = self.headers.get("Content-Length", "")
            if not length.isascii() or not length.isdecimal() or not (0 < int(length) <= MAX_BODY):
                self.respond(400, {"error": "invalid_body_size"})
                return
            try:
                packet = json.loads(
                    self.rfile.read(int(length)),
                    object_pairs_hook=_strict_object, parse_constant=_reject_constant,
                )
            except (ValueError, UnicodeError):
                self.respond(400, {"error": "invalid_json"})
                return
            if route == "/stage":
                # Staging is non-effecting. Existing actor-only route is safe
                # here because this server NEVER exposes actor-only /commit.
                code, response = authenticated_process(database, route, packet)
            else:
                code, response = appraise_and_commit(database, route, packet)
            self.respond(code, response)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local two-root agent policy target")
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    initialize(args.database)
    with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(args.database)) as server:
        print(json.dumps({"port": server.server_port}), flush=True)
        server.serve_forever(poll_interval=0.1)


if __name__ == "__main__":
    main()
