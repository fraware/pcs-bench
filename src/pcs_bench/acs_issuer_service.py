"""Isolated local ACS policy issuer: evaluate real Cedar before signing a grant.

This research process owns an ephemeral Ed25519 issuer private key that is never
returned through HTTP, written to disk, or supplied to the actor process. It
pins the manifest and Cedar policy bytes and provides ONLY an allow/deny policy
evaluation API. An honest process cannot be instructed to sign an arbitrary
permission using a caller-provided verdict, policy digest or target audience.

This is not an attested enclave, HSM, independent organization, or production
authorization authority. Local process isolation does not prevent same-user
or host compromise. The service is strictly loopback-only.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pcs_bench.acs_effect_host import AcsEffectHost
from pcs_bench.authenticated_target import MAX_BODY, _reject_constant, _strict_object
from pcs_bench.dual_authority_target import sign_decision
from pcs_bench.guarded_target import decode_action


class CedarIssuer:
    """A confined signing interface with host-controlled immutable policy inputs."""

    def __init__(
        self, manifest: Path, *, target_audience: str, issuer_id: str,
        actor_key_id: str, epoch: int = 1,
    ) -> None:
        if not target_audience.startswith("pcs-effect-target:"):
            raise ValueError("must pin a concrete lab target audience")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", issuer_id):
            raise ValueError("invalid issuer")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", actor_key_id):
            raise ValueError("invalid actor key")
        if type(epoch) is not int or epoch < 1:
            raise ValueError("invalid policy epoch")
        self._manifest = manifest.resolve(strict=True)
        self._policy = (self._manifest.parent / "effect_guard.cedar").resolve(strict=True)
        self._host = AcsEffectHost(
            self._manifest, epoch=epoch, legacy_cedar_principal_bridge=True
        )
        self._manifest_hash = self._host.manifest_sha256
        self._policy_hash = self._host.cedar_sha256
        self._audience = target_audience
        self._issuer_id = issuer_id
        self._actor_key_id = actor_key_id
        self._private_key = Ed25519PrivateKey.generate()
        self._lock = threading.Lock()
        self._sequence = 0
        self._audit: list[dict[str, object]] = []

    def public_key(self) -> bytes:
        return self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    @property
    def identity(self) -> dict[str, object]:
        return {
            "issuer_id": self._issuer_id,
            "target_audience": self._audience,
            "actor_key_id": self._actor_key_id,
            "policy_sha256": self._policy_hash,
            "manifest_sha256": self._manifest_hash,
            "policy_epoch": self._host.epoch,
            "public_key_sha256": hashlib.sha256(self.public_key()).hexdigest(),
            "alpha4_compatibility_projection": True,
        }

    def _policy_unchanged(self) -> bool:
        return (
            hashlib.sha256(self._manifest.read_bytes()).hexdigest() == self._manifest_hash
            and hashlib.sha256(self._policy.read_bytes()).hexdigest() == self._policy_hash
        )

    def evaluate(self, request: object) -> tuple[int, dict[str, object]]:
        if not isinstance(request, dict) or set(request) != {"action", "actor_key_id"}:
            return 400, {"error": "invalid_issuer_request"}
        if request["actor_key_id"] != self._actor_key_id:
            return 403, {"error": "actor_key_not_enrolled_in_issuer"}
        try:
            action = decode_action(request["action"])
        except (ValueError, TypeError, KeyError):
            return 400, {"error": "invalid_action"}
        with self._lock:
            if not self._policy_unchanged():
                return 503, {"error": "pinned_policy_bytes_changed"}
            self._sequence += 1
            # The only path to the issuer's key is behind a real ACS evaluation.
            verdict = asyncio.run(self._host.authorize(action))
            audit_entry: dict[str, object] = {
                "sequence": self._sequence,
                "checked_at": datetime.now(UTC).isoformat(),
                "request_digest": verdict.request_digest,
                "permitted": verdict.permitted,
                "reason": verdict.reason,
                "policy_sha256": self._policy_hash,
                "policy_epoch": verdict.policy_epoch,
            }
            if not verdict.permitted:
                self._audit.append(audit_entry)
                return 403, {"status": "denied", "reason": verdict.reason}
            if verdict.policy_epoch != self._host.epoch:
                return 503, {"error": "policy_epoch_changed_during_evaluation"}
            credential = sign_decision(
                self._private_key,
                issuer_id=self._issuer_id,
                target_audience=self._audience,
                actor_key_id=self._actor_key_id,
                action=action,
                policy_sha256=self._policy_hash,
                policy_epoch=self._host.epoch,
            )
            audit_entry["decision_id"] = credential["statement"]["decision_id"]
            self._audit.append(audit_entry)
            return 200, {"status": "issued", "authorization": credential}

    def audit(self) -> dict[str, object]:
        with self._lock:
            return {
                "events": [row.copy() for row in self._audit],
                "warning": (
                    "Issuer-owned diagnostic data. Not independently authenticated, "
                    "omission-detectable, or cryptographic proof of ACS execution."
                ),
            }


def make_handler(issuer: CedarIssuer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def respond(self, code: int, payload: dict[str, object]) -> None:
            raw = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            route = urlsplit(self.path).path
            if route == "/identity":
                self.respond(200, issuer.identity)
            elif route == "/audit":
                self.respond(200, issuer.audit())
            else:
                self.respond(404, {"error": "unsupported_route"})

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/authorize":
                self.respond(404, {"error": "unsupported_route"})
                return
            length = self.headers.get("Content-Length", "")
            if not length.isascii() or not length.isdecimal() or not (0 < int(length) <= MAX_BODY):
                self.respond(400, {"error": "invalid_body_size"})
                return
            try:
                data = json.loads(
                    self.rfile.read(int(length)),
                    object_pairs_hook=_strict_object, parse_constant=_reject_constant,
                )
            except (ValueError, UnicodeError):
                self.respond(400, {"error": "invalid_json"})
                return
            try:
                status, response = issuer.evaluate(data)
            except (OSError, RuntimeError, ValueError, TypeError):
                self.respond(503, {"error": "policy_runtime_unavailable"})
                return
            self.respond(status, response)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local ACS policy-gated Ed25519 issuer")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target-audience", required=True)
    parser.add_argument("--issuer-id", default="acs-restricted-issuer")
    parser.add_argument("--actor-key-id", default="acs-restricted-actor")
    parser.add_argument("--public-key-file", type=Path, required=True)
    parser.add_argument("--policy-epoch", type=int, default=1)
    args = parser.parse_args()
    issuer = CedarIssuer(
        args.manifest, target_audience=args.target_audience,
        issuer_id=args.issuer_id, actor_key_id=args.actor_key_id,
        epoch=args.policy_epoch,
    )
    args.public_key_file.parent.mkdir(parents=True, exist_ok=True)
    # Public, not private: trusted operator enrolls these bytes at the target.
    with args.public_key_file.open("xb") as stream:
        stream.write(issuer.public_key())
    with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(issuer)) as server:
        print(json.dumps({"port": server.server_port}), flush=True)
        server.serve_forever(poll_interval=0.1)


if __name__ == "__main__":
    main()
