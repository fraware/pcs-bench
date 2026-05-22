"""Validate embedded producer PcsBenchIngest.v0 fixtures (offline CI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parents[1]
FIXTURE_ROOT = _REPO_ROOT / "tests" / "fixtures" / "producer_ingest"

PRODUCER_FIXTURE_DIRS: tuple[tuple[str, str], ...] = (
    ("certifyedge", "certifyedge"),
    ("provability-fabric", "provability_fabric"),
    ("scientific-memory", "scientific_memory"),
    ("labtrust-gym", "labtrust_reproducibility"),
)

LABTRUST_FIXTURE_FALLBACK_DIRS: tuple[str, ...] = (
    "labtrust_reproducibility",
    "labtrust",
)

# Every embedded ingest directory under tests/fixtures/producer_ingest/
_FIXTURE_DIR_TO_PRODUCER: dict[str, str] = {
    "certifyedge": "certifyedge",
    "provability_fabric": "provability-fabric",
    "scientific_memory": "scientific-memory",
    "labtrust": "labtrust-gym",
    "labtrust_reproducibility": "labtrust-gym",
}


@dataclass
class ProducerFixtureValidation:
    producer: str
    path: Path
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def fixture_ingest_path(producer_dir: str) -> Path:
    return FIXTURE_ROOT / producer_dir / "pcs_bench_ingest.v0.json"


def resolve_schema_root(pcs_core: Path | None) -> Path:
    if pcs_core and (pcs_core / "schemas").is_dir():
        return pcs_core.resolve()
    return _PKG_ROOT


def validate_all_producer_fixtures(
    pcs_core: Path | None = None,
    *,
    use_pcs_validate: bool = False,
    release_grade: bool = False,
) -> list[ProducerFixtureValidation]:
    from pcs_bench.ingest_validation import validate_ingest_json

    schema_root = resolve_schema_root(pcs_core)
    results: list[ProducerFixtureValidation] = []

    seen_paths: set[Path] = set()
    for dirname in sorted(_FIXTURE_DIR_TO_PRODUCER):
        producer_id = _FIXTURE_DIR_TO_PRODUCER[dirname]
        path = fixture_ingest_path(dirname)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        entry = ProducerFixtureValidation(producer=f"{producer_id}:{dirname}", path=path)
        if not path.is_file():
            entry.errors.append(f"Missing fixture: {path}")
        else:
            entry.errors.extend(
                validate_ingest_json(
                    path,
                    schema_root,
                    use_pcs_validate=use_pcs_validate,
                    release_grade=release_grade,
                )
            )
        results.append(entry)

    return results


def all_fixtures_valid(pcs_core: Path | None = None) -> bool:
    return all(r.valid for r in validate_all_producer_fixtures(pcs_core))
