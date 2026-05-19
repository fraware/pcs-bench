"""Release artifact discovery and PCS completeness analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pcs_bench.metrics_definitions import CERTIFICATE_REQUIRED_FIELDS, REQUIRED_MEMORY_SECTIONS

CERTIFICATE_GLOBS = (
    "*certificate*.json",
    "*Certificate*.json",
    "*witness*.json",
    "*Witness*.json",
)
REGISTRY_NAMES = (
    "artifact_registry.v0.json",
    "artifact_registry.json",
)
MANIFEST_NAMES = (
    "release_manifest.v0.json",
    "release_manifest.json",
)
HANDOFF_NAMES = (
    "handoff_manifest.v0.json",
    "handoff_manifest.json",
    "handoff.json",
)


@dataclass
class ArtifactAnalysis:
    release_dir: str
    manifest_path: str | None = None
    registry_path: str | None = None
    handoff_path: str | None = None
    certificate_paths: list[str] = field(default_factory=list)
    bundle_paths: list[str] = field(default_factory=list)
    lean_check_paths: list[str] = field(default_factory=list)
    registry_artifact_count: int = 0
    registry_checked_count: int = 0
    certificate_field_coverage: float = 0.0
    certificate_missing_fields: list[str] = field(default_factory=list)
    rendered_sections: list[str] = field(default_factory=list)
    rendered_section_coverage: float = 0.0
    repair_hint_present: bool = False
    verification: dict[str, Any] = field(default_factory=dict)

    @property
    def registry_coverage_ratio(self) -> float:
        if self.registry_artifact_count == 0:
            return 1.0
        return self.registry_checked_count / self.registry_artifact_count


def _first_existing(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        p = root / name
        if p.exists():
            return p
    return None


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def discover_release_layout(release_dir: Path) -> ArtifactAnalysis:
    analysis = ArtifactAnalysis(release_dir=str(release_dir.resolve()))
    manifest = _first_existing(release_dir, MANIFEST_NAMES)
    registry = _first_existing(release_dir, REGISTRY_NAMES)
    handoff = _first_existing(release_dir, HANDOFF_NAMES)

    if manifest:
        analysis.manifest_path = str(manifest)
    if registry:
        analysis.registry_path = str(registry)
    if handoff:
        analysis.handoff_path = str(handoff)

    for pattern in CERTIFICATE_GLOBS:
        for p in release_dir.glob(pattern):
            if p.is_file() and str(p) not in analysis.certificate_paths:
                analysis.certificate_paths.append(str(p))

    for p in release_dir.glob("**/*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        if "science" in name and "claim" in name and p.suffix == ".json":
            analysis.bundle_paths.append(str(p))
        if "lean_check" in name or "lean-check" in name:
            analysis.lean_check_paths.append(str(p))

    return analysis


def _certificate_field_groups(data: dict[str, Any]) -> set[str]:
    present: set[str] = set()
    keys_lower = {k.lower(): k for k in data}
    for req in CERTIFICATE_REQUIRED_FIELDS:
        if req in data or req.lower() in keys_lower:
            present.add(req)
        if req == "certificate_id" and ("certificate_id" in data or "witness_id" in data):
            present.add(req)
        if req == "witness_id" and "witness_id" in data:
            present.add(req)
        if req == "trace_hash" and ("trace_hash" in data or "result_hashes" in data):
            present.add(req)
        if req == "result_hashes" and "result_hashes" in data:
            present.add(req)
    return present


def analyze_certificate(path: Path) -> tuple[float, list[str]]:
    data = _load_json(path)
    groups = _certificate_field_groups(data)
    required_groups = {
        "certificate_id",
        "trace_hash",
        "property_id",
        "checker",
        "checker_version",
        "status",
        "source_repo",
        "source_commit",
        "signature_or_digest",
    }
    missing = sorted(required_groups - groups)
    score = 1.0 - (len(missing) / max(len(required_groups), 1))
    if data.get("status") == "Rejected":
        if data.get("violations") or data.get("counterexamples"):
            score = min(1.0, score + 0.05)
        if data.get("repair_hint") or data.get("repair_hint_kind"):
            score = min(1.0, score + 0.05)
    return score, missing


def analyze_registry(path: Path) -> tuple[int, int]:
    data = _load_json(path)
    artifacts = data.get("artifacts") or data.get("entries") or []
    if not isinstance(artifacts, list):
        return 0, 0
    total = len(artifacts)
    checked = 0
    for entry in artifacts:
        if not isinstance(entry, dict):
            continue
        if entry.get("checked") or entry.get("registry_checked") or entry.get("hash"):
            checked += 1
    return total, checked


def analyze_rendered_output(path: Path) -> tuple[list[str], float]:
    if not path.exists():
        return [], 0.0
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json":
        data = json.loads(text) if text.strip() else {}
        sections = data.get("sections") or data.get("rendered_sections") or []
        if isinstance(sections, dict):
            found = [k for k in REQUIRED_MEMORY_SECTIONS if k in sections]
        elif isinstance(sections, list):
            found = [s for s in REQUIRED_MEMORY_SECTIONS if s in sections]
        else:
            found = []
    else:
        found = [s for s in REQUIRED_MEMORY_SECTIONS if s.lower() in text.lower()]
    coverage = len(found) / len(REQUIRED_MEMORY_SECTIONS)
    return found, coverage


def enrich_analysis(
    analysis: ArtifactAnalysis,
    *,
    verification_path: Path | None = None,
    rendered_path: Path | None = None,
) -> ArtifactAnalysis:
    if analysis.registry_path:
        total, checked = analyze_registry(Path(analysis.registry_path))
        analysis.registry_artifact_count = total
        analysis.registry_checked_count = checked

    if analysis.certificate_paths:
        scores = []
        all_missing: list[str] = []
        for cert in analysis.certificate_paths:
            score, missing = analyze_certificate(Path(cert))
            scores.append(score)
            all_missing.extend(missing)
        analysis.certificate_field_coverage = sum(scores) / len(scores)
        analysis.certificate_missing_fields = sorted(set(all_missing))

    if verification_path and verification_path.exists():
        analysis.verification = _load_json(verification_path)
        repair = analysis.verification.get("repair_hint") or analysis.verification.get(
            "repair_hint_kind"
        )
        analysis.repair_hint_present = bool(repair)

    if rendered_path:
        sections, coverage = analyze_rendered_output(rendered_path)
        analysis.rendered_sections = sections
        analysis.rendered_section_coverage = coverage

    return analysis
