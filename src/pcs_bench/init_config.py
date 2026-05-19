"""Scaffold pcs-bench.yaml for new installations."""

from __future__ import annotations

from pathlib import Path

DEFAULT_CONFIG = """repos:
  pcs_core: ../pcs-core
  labtrust: ../LabTrust-Gym
  certifyedge: ../CertifyEdge
  provability_fabric: ../provability-fabric
  scientific_memory: ../scientific-memory

commands:
  pcs: pcs
  labtrust: labtrust
  certifyedge: certifyedge
  pf: pf
  just: just

workspace:
  root: .pcs-bench-workspaces
  clean_between_cases: true
  preserve_failed_cases: true

execution:
  parallel_cases: 1

thresholds:
  release_reproducibility_score: 0.95
  failure_localization_accuracy: 0.90
  certificate_completeness_score: 0.95
  registry_coverage_score: 0.95
  formal_check_coverage_score: 0.90
  scientific_memory_interpretability_score: 0.95
  repair_hint_quality_score: 0.90
  cross_domain_portability_score: 0.90

timeouts:
  command_seconds: 120
  suite_seconds: 1800
"""


def write_default_config(path: Path, *, force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return True
