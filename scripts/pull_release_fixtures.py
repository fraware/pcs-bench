#!/usr/bin/env python3
"""
Copy real release artifacts from sibling PCS repos into benchmark case fixtures.

Requires sibling repositories on disk (see pcs-bench.yaml repos.* paths).
Only overwrites input_artifacts when source bundles exist; never deletes cases.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARTIFACT_NAMES = (
    "release_manifest.v0.json",
    "artifact_registry.v0.json",
    "handoff_manifest.v0.json",
    "trace_certificate.v0.json",
    "science_claim_bundle.v0.json",
    "admission_profile.v0.json",
    "computation_witness.v0.json",
    "proof_obligation.v0.json",
    "lean_check_result.v0.json",
)


def _load_config_repos() -> dict[str, Path]:
    cfg_path = ROOT / "pcs-bench.yaml"
    if not cfg_path.exists():
        return {}
    import yaml

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    repos = raw.get("repos") or {}
    return {k: (ROOT / v).resolve() if not Path(v).is_absolute() else Path(v) for k, v in repos.items()}


def find_release_bundle(repo_path: Path, release_id: str) -> Path | None:
    """Search common fixture/release locations under a sibling repo."""
    if not repo_path.is_dir():
        return None
    candidates = [
        repo_path / "benchmarks" / "releases" / release_id,
        repo_path / "fixtures" / "releases" / release_id,
        repo_path / "examples" / release_id,
        repo_path / "releases" / release_id,
    ]
    for base in candidates:
        if base.is_dir() and (base / "release_manifest.v0.json").exists():
            return base
    for manifest in repo_path.rglob("release_manifest.v0.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("release_id") == release_id:
                return manifest.parent
        except (json.JSONDecodeError, OSError):
            continue
    return None


def copy_bundle(source_dir: Path, dest_dir: Path, *, dry_run: bool) -> int:
    copied = 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in ARTIFACT_NAMES:
        src = source_dir / name
        if src.exists():
            if dry_run:
                print(f"  would copy {src.name}")
            else:
                shutil.copy2(src, dest_dir / name)
            copied += 1
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="labtrust_qc_release", help="Benchmark suite directory name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--labtrust", type=Path, help="Override LabTrust repo path")
    args = parser.parse_args()

    repos = _load_config_repos()
    labtrust = args.labtrust or repos.get("labtrust")
    if not labtrust or not labtrust.is_dir():
        print("LabTrust repo not found; set repos.labtrust in pcs-bench.yaml", file=sys.stderr)
        return 1

    suite_dir = ROOT / "benchmarks" / args.suite
    updated = 0
    for case_file in sorted(suite_dir.rglob("benchmark_case.v0.json")):
        case = json.loads(case_file.read_text(encoding="utf-8"))
        release_id = case.get("case_id") or case.get("task_id")
        if not release_id:
            continue
        bundle = find_release_bundle(labtrust, release_id)
        if not bundle:
            print(f"skip {case['case_id']}: no bundle in LabTrust")
            continue
        dest = case_file.parent / "input_artifacts"
        n = copy_bundle(bundle, dest, dry_run=args.dry_run)
        if n:
            print(f"{'[dry-run] ' if args.dry_run else ''}{case['case_id']}: {n} artifacts from {bundle}")
            updated += 1

    print(f"Done. Updated {updated} case(s). Re-run: python scripts/materialize_fixtures.py (if needed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
