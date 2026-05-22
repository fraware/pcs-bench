"""Batch ingest and optional validate for all configured producer repos."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pcs_bench.config import BenchConfig
from pcs_bench.producer_gate import PRODUCER_BENCHMARKS, _repo_for_producer
from pcs_bench.producer_ingest import ingest_producer_output


@dataclass
class IngestAllResult:
    outputs: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def ingest_all_producers(
    cfg: BenchConfig,
    out_dir: Path,
    *,
    validate: bool = True,
    require_all: bool = True,
    release_grade: bool = False,
) -> IngestAllResult:
    """Ingest PcsBenchIngest.v0 from each producer repo into normalized BenchmarkReport files."""
    result = IngestAllResult()
    out_dir.mkdir(parents=True, exist_ok=True)

    for spec in PRODUCER_BENCHMARKS:
        repo = _repo_for_producer(cfg, spec.producer)
        ingest_path = repo / spec.ingest_rel_path
        if not ingest_path.is_file():
            result.errors.append(f"{spec.producer}: missing {ingest_path}")
            continue
        dest = out_dir / f"{spec.producer}.normalized.json"
        try:
            ingest_producer_output(
                spec.producer,
                ingest_path,
                dest,
                pcs_core_path=cfg.repos.pcs_core,
                validate=validate,
                release_grade=release_grade,
                producer_repo=repo if repo.is_dir() else None,
            )
        except (ValueError, OSError) as exc:
            result.errors.append(f"{spec.producer}: {exc}")
            continue
        result.outputs.append(dest)

    if require_all and len(result.outputs) < len(PRODUCER_BENCHMARKS):
        result.errors.append(
            f"Expected {len(PRODUCER_BENCHMARKS)} ingests, completed {len(result.outputs)}"
        )
    return result
