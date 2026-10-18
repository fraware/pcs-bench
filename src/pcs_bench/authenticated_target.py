"""Experimental Ed25519-authenticated target with atomic policy and key checks.

This is a distinct localhost-only target. Private keys are never stored in the
server, and signing keys are ephemeral test fixtures. Trusted local operator
functions provision/revoke public keys; HTTP cannot administer authorities.

Signature verification, nonce consumption, principal/tenant binding, current
target policy, and any effect commit are checked under one SQLite write
transaction. This models a small trustworthy commit boundary, NOT TLS/mTLS,
PKI, attestation, secure time, OS access controls, or a production identity
system. A valid credential still allows direct calls bypassing ACS.
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

from pcs_bench.effect_boundary import Action, action_digest
from pcs_bench.guarded_target import (
    MAX_BODY,
    _commit_in_tx,
    allowed,
    db_connect,
    decode_action,
    snapshot,
)
from pcs_bench.guarded_target import initialize as initialize_guarded

VERSION = "pcs-bench-ed25519-target-v1"
DOMAIN = b"pcs-bench-ed25519-target-v1\x00"
ROUTES = frozenset({"/stage", "/commit-staged", "/commit"})
MAX_LIFETIME = 60
CLOCK_SKEW = 5


def _bytes(value: dict[str, Any]) -> bytes:
    """Version-local deterministic serialization, NOT RFC 8785 JCS."""
    return DOMAIN + json.dumps(value, sort_keys=True, ensure_ascii=True,
                               separators=(",", ":"), allow_nan=False).encode("ascii")


def initialize(database: Path) -> None:
    initialize_guarded(database)
    with db_connect(database) as con:
        con.execute("CREATE TABLE IF NOT EXISTS auth_metadata("
                    "singleton INTEGER PRIMARY KEY CHECK(singleton=1), audience TEXT NOT NULL)")
        con.execute("INSERT OR IGNORE INTO auth_metadata VALUES(1,?)",
                    ("pcs-effect-target:" + secrets.token_hex(16),))
        con.execute("CREATE TABLE IF NOT EXISTS auth_keys("
                    "key_id TEXT PRIMARY KEY, principal TEXT NOT NULL, tenant TEXT NOT NULL, "
                    "public_key BLOB NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)")
        con.execute("CREATE TABLE IF NOT EXISTS auth_nonces("
                    "key_id TEXT NOT NULL, nonce TEXT NOT NULL, expires_at INTEGER NOT NULL, "
                    "PRIMARY KEY(key_id,nonce))")
        con.execute("CREATE TABLE IF NOT EXISTS auth_stages("
                    "operation_id TEXT PRIMARY KEY, key_id TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS auth_effects("
                    "operation_id TEXT PRIMARY KEY, key_id TEXT NOT NULL, "
                    "nonce TEXT NOT NULL, commit_epoch INTEGER NOT NULL)")


def audience(database: Path) -> str:
    with db_connect(database) as con:
        row = con.execute("SELECT audience FROM auth_metadata WHERE singleton=1").fetchone()
    if row is None:
        raise RuntimeError("target has no initialized audience")
    return str(row["audience"])


def register_key(
    database: Path, *, key_id: str, principal: str, tenant: str, public_key: bytes
) -> None:
    """Direct trusted-operator enrollment, with no HTTP equivalent."""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", key_id):
        raise ValueError("invalid key identifier")
    if not isinstance(principal, str) or not principal or not isinstance(tenant, str) or not tenant:
        raise ValueError("invalid identity")
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise ValueError("invalid Ed25519 public key")
    Ed25519PublicKey.from_public_bytes(public_key)
    with db_connect(database) as con:
        con.execute("INSERT INTO auth_keys VALUES(?,?,?,?,0)",
                    (key_id, principal, tenant, public_key))


def revoke_key(database: Path, *, key_id: str) -> None:
    """Trusted operator revocation ordered with commit transactions."""
    with db_connect(database) as con:
        con.execute("BEGIN IMMEDIATE")
        found = con.execute("UPDATE auth_keys SET revoked=1 WHERE key_id=?", (key_id,))
        if found.rowcount != 1:
            raise ValueError("key not found")
        con.execute("COMMIT")


def sign_request(
    private_key: Ed25519PrivateKey, *,
    key_id: str,
    audience_id: str,
    route: str,
    body: dict[str, object],
    nonce: str | None = None,
    issued_at: int | None = None,
    expires_at: int | None = None,
) -> dict[str, object]:
    """Test-client signature constructor; never ship a key in repository files."""
    now = int(time.time()) if issued_at is None else issued_at
    signed: dict[str, object] = {
        "version": VERSION,
        "audience": audience_id,
        "method": "POST",
        "path": route,
        "key_id": key_id,
        "nonce": nonce if nonce is not None else secrets.token_hex(16),
        "issued_at": now,
        "expires_at": now + 30 if expires_at is None else expires_at,
        "body": body,
    }
    signature = private_key.sign(_bytes(signed))
    return {"signed": signed, "signature": base64.urlsafe_b64encode(signature).decode().rstrip("=")}


def _preflight(route: str, envelope: object) -> tuple[dict[str, Any], bytes] | None:
    if route not in ROUTES or not isinstance(envelope, dict) or set(envelope) != {
        "signed", "signature"
    }:
        return None
    signed = envelope["signed"]
    signature = envelope["signature"]
    if not isinstance(signed, dict) or set(signed) != {
        "version", "audience", "method", "path", "key_id", "nonce",
        "issued_at", "expires_at", "body"
    }:
        return None
    if signed["version"] != VERSION or signed["method"] != "POST" or signed["path"] != route:
        return None
    if not isinstance(signed["audience"], str) or not signed["audience"]:
        return None
    if not isinstance(signed["key_id"], str) or not re.fullmatch(
        r"[A-Za-z0-9._-]{1,64}", signed["key_id"]
    ):
        return None
    if not isinstance(signed["nonce"], str) or not re.fullmatch(
        r"[0-9a-f]{32}", signed["nonce"]
    ):
        return None
    issued, expires = signed["issued_at"], signed["expires_at"]
    if type(issued) is not int or type(expires) is not int:
        return None
    if not (0 < expires - issued <= MAX_LIFETIME):
        return None
    if not isinstance(signed["body"], dict):
        return None
    if not isinstance(signature, str) or not re.fullmatch(r"[A-Za-z0-9_-]{86}", signature):
        return None
    try:
        decoded = base64.b64decode(signature + "==", altchars=b"-_", validate=True)
        if len(decoded) != 64:
            return None
        _bytes(signed)
    except (ValueError, TypeError, OverflowError, binascii.Error):
        return None
    return signed, decoded


def authenticated_process(
    database: Path, route: str, envelope: object
) -> tuple[int, dict[str, object]]:
    """Authenticate the exact requested route and enforce at target commit.

    Expected negative outcomes are returned explicitly. Nonces are consumed
    only after authentication, with any resulting effect in the same TX.
    """
    checked = _preflight(route, envelope)
    if checked is None:
        return 400, {"error": "invalid_signed_request"}
    signed, signature = checked
    with db_connect(database) as con:
        con.execute("BEGIN IMMEDIATE")
        now = int(time.time())
        if signed["issued_at"] > now + CLOCK_SKEW or signed["expires_at"] < now:
            return 401, {"error": "credential_time_invalid"}
        meta = con.execute("SELECT audience FROM auth_metadata WHERE singleton=1").fetchone()
        if meta is None or signed["audience"] != meta["audience"]:
            return 401, {"error": "wrong_target_audience"}
        key = con.execute("SELECT * FROM auth_keys WHERE key_id=?", (signed["key_id"],)).fetchone()
        if key is None:
            return 401, {"error": "unregistered_key"}
        if key["revoked"]:
            return 403, {"error": "key_revoked"}
        try:
            Ed25519PublicKey.from_public_bytes(key["public_key"]).verify(
                signature, _bytes(signed)
            )
        except (ValueError, TypeError, InvalidSignature):
            return 401, {"error": "signature_invalid"}
        existing_nonce = con.execute(
            "SELECT 1 FROM auth_nonces WHERE key_id=? AND nonce=?",
            (signed["key_id"], signed["nonce"]),
        ).fetchone()
        if existing_nonce:
            return 409, {"error": "nonce_replay"}
        body = signed["body"]
        if route in ("/stage", "/commit"):
            try:
                action = decode_action(body)
            except (ValueError, TypeError, KeyError):
                return 400, {"error": "invalid_action"}
        else:
            if set(body) != {"operation_id", "request_digest"} or not all(
                isinstance(body[k], str) for k in body
            ):
                return 400, {"error": "invalid_stage_receipt"}
            if not re.fullmatch(r"[0-9a-f]{64}", body["request_digest"]):
                return 400, {"error": "invalid_stage_receipt"}
            stage = con.execute(
                "SELECT * FROM staged WHERE operation_id=?", (body["operation_id"],)
            ).fetchone()
            owner = con.execute(
                "SELECT key_id FROM auth_stages WHERE operation_id=?", (body["operation_id"],)
            ).fetchone()
            if stage is None or owner is None:
                return 404, {"error": "stage_not_found"}
            if owner["key_id"] != signed["key_id"]:
                return 403, {"error": "stage_signer_mismatch"}
            if stage["digest"] != body["request_digest"]:
                return 409, {"error": "stage_digest_mismatch"}
            action = Action(stage["operation_id"], stage["principal"], stage["tenant"],
                            stage["resource"], stage["delta"])
        if action.principal != key["principal"] or action.tenant != key["tenant"]:
            return 403, {"error": "authenticated_identity_mismatch"}
        digest = action_digest(action)
        if route == "/commit-staged" and stage["digest"] != digest:
            return 409, {"error": "corrupt_staged_action"}
        # Commit nonce with accepted/rejected operation. Other outcomes
        # (signature, schema, identity) return before nonce consumption.
        con.execute("DELETE FROM auth_nonces WHERE expires_at < ?", (now - CLOCK_SKEW,))
        con.execute(
            "INSERT INTO auth_nonces VALUES(?,?,?)",
            (signed["key_id"], signed["nonce"], signed["expires_at"]),
        )
        previous = con.execute(
            "SELECT * FROM effects WHERE operation_id=?", (action.operation_id,)
        ).fetchone()
        if previous is not None:
            if previous["digest"] != digest:
                con.execute("COMMIT")
                return 409, {"error": "idempotency_collision"}
            receipt = {"status": "deduplicated", "operation_id": action.operation_id,
                       "request_digest": digest, "commit_epoch": previous["commit_epoch"]}
            con.execute("COMMIT")
            return 200, receipt
        policy = con.execute("SELECT * FROM authority WHERE singleton=1").fetchone()
        if policy is None:
            raise RuntimeError("policy uninitialized")
        denied = allowed(action, policy)
        if denied is not None:
            con.execute("COMMIT")
            return 403, {"error": denied, "policy_epoch": policy["epoch"]}
        if route == "/stage":
            prior = con.execute(
                "SELECT * FROM staged WHERE operation_id=?", (action.operation_id,)
            ).fetchone()
            if prior is not None:
                stage_owner = con.execute(
                    "SELECT key_id FROM auth_stages WHERE operation_id=?",
                    (action.operation_id,),
                ).fetchone()
                if stage_owner is None:
                    raise RuntimeError("existing stage lacks authenticated owner")
                if stage_owner["key_id"] != signed["key_id"]:
                    con.execute("COMMIT")
                    return 403, {"error": "stage_signer_mismatch"}
                outcome = (
                    (200, {"status": "staged_existing", "operation_id": action.operation_id,
                           "request_digest": digest, "stage_epoch": prior["stage_epoch"]})
                    if prior["digest"] == digest
                    else (409, {"error": "staged_operation_collision"})
                )
                con.execute("COMMIT")
                return outcome
            con.execute("INSERT INTO staged VALUES(?,?,?,?,?,?,?)",
                        (action.operation_id, digest, action.principal, action.tenant,
                         action.resource, action.delta, policy["epoch"]))
            con.execute("INSERT INTO auth_stages VALUES(?,?)",
                        (action.operation_id, signed["key_id"]))
            con.execute("COMMIT")
            return 202, {"status": "staged", "operation_id": action.operation_id,
                         "request_digest": digest, "stage_epoch": policy["epoch"]}
        if route == "/commit-staged" and stage["stage_epoch"] != policy["epoch"]:
            con.execute("COMMIT")
            return 409, {"error": "stage_policy_epoch_stale", "policy_epoch": policy["epoch"]}
        receipt = _commit_in_tx(con, action, policy["epoch"])
        con.execute("INSERT INTO auth_effects VALUES(?,?,?,?)",
                    (action.operation_id, signed["key_id"], signed["nonce"], policy["epoch"]))
        con.execute("COMMIT")
        return 200, receipt


def auth_snapshot(database: Path) -> dict[str, object]:
    with db_connect(database) as con:
        rows = con.execute(
            "SELECT e.operation_id,e.commit_epoch,a.key_id,a.nonce "
            "FROM effects e JOIN auth_effects a ON e.operation_id=a.operation_id "
            "ORDER BY e.operation_id"
        ).fetchall()
    return {"commits": [dict(row) for row in rows]}


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite JSON number")


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
            if route == "/identity":
                self.reply(200, {"audience": audience(database), "version": VERSION})
            elif route == "/auth-journal":
                self.reply(200, auth_snapshot(database))
            elif route in ("/journal", "/state"):
                self.reply(200, snapshot(database, route))
            else:
                self.reply(404, {"error": "unknown_route"})

        def do_POST(self) -> None:
            route = urlsplit(self.path).path
            length = self.headers.get("Content-Length", "")
            if not length.isascii() or not length.isdecimal() or not (0 < int(length) <= MAX_BODY):
                self.reply(400, {"error": "invalid_body_size"})
                return
            try:
                data = json.loads(self.rfile.read(int(length)),
                                  object_pairs_hook=_strict_object,
                                  parse_constant=_reject_constant)
            except (ValueError, UnicodeError):
                self.reply(400, {"error": "invalid_json"})
                return
            status, record = authenticated_process(database, route, data)
            self.reply(status, record)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Loopback-only Ed25519 authenticated effect target")
    parser.add_argument("--database", required=True, type=Path)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    initialize(args.database)
    with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(args.database)) as server:
        print(json.dumps({"port": server.server_port}), flush=True)
        server.serve_forever(poll_interval=0.1)


if __name__ == "__main__":
    main()
