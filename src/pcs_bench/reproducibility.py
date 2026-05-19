"""Fixture integrity and reproducibility manifests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pcs_bench.config import BenchConfig


@dataclass
class FixtureEntry:
    path: str
    sha256: str
    size_bytes: int


@dataclass
class FixtureManifest:
    manifest_id: str
    generated_at: str
    benchmarks_root: str
    entries: list[FixtureEntry] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.entries)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def build_fixture_manifest(config: BenchConfig | None = None) -> FixtureManifest:
    cfg = config or BenchConfig()
    root = cfg.benchmarks_root.resolve()
    entries: list[FixtureEntry] = []
    patterns = ("*.json", "*.yaml", "*.yml", "*.md")

    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if ".pcs-bench-workspaces" in str(path):
                continue
            rel = str(path.relative_to(root))
            entries.append(
                FixtureEntry(
                    path=rel,
                    sha256=_hash_file(path),
                    size_bytes=path.stat().st_size,
                )
            )

    return FixtureManifest(
        manifest_id=f"fixture-manifest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        generated_at=datetime.now(timezone.utc).isoformat(),
        benchmarks_root=str(root),
        entries=entries,
    )


def save_fixture_manifest(manifest: FixtureManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "manifest_id": manifest.manifest_id,
        "generated_at": manifest.generated_at,
        "benchmarks_root": manifest.benchmarks_root,
        "file_count": manifest.file_count,
        "entries": [
            {"path": e.path, "sha256": e.sha256, "size_bytes": e.size_bytes}
            for e in manifest.entries
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_fixture_manifest(path: Path) -> FixtureManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = [
        FixtureEntry(path=e["path"], sha256=e["sha256"], size_bytes=e["size_bytes"])
        for e in data.get("entries", [])
    ]
    return FixtureManifest(
        manifest_id=data["manifest_id"],
        generated_at=data["generated_at"],
        benchmarks_root=data["benchmarks_root"],
        entries=entries,
    )


@dataclass
class FixtureVerificationResult:
    valid: bool
    missing_files: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)


def verify_fixture_manifest(
    config: BenchConfig,
    manifest_path: Path,
) -> FixtureVerificationResult:
    stored = load_fixture_manifest(manifest_path)
    current = build_fixture_manifest(config)
    stored_map = {e.path: e.sha256 for e in stored.entries}
    current_map = {e.path: e.sha256 for e in current.entries}

    missing = sorted(set(stored_map) - set(current_map))
    new = sorted(set(current_map) - set(stored_map))
    changed = sorted(
        p for p in stored_map if p in current_map and stored_map[p] != current_map[p]
    )
    return FixtureVerificationResult(
        valid=not missing and not changed and not new,
        missing_files=missing,
        changed_files=changed,
        new_files=new,
    )
