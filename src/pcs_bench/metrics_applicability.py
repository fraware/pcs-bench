"""Metric applicability semantics for honest simulation scoring."""

from __future__ import annotations

from pcs_bench.schemas import MetricSummary

APPLICABILITY_MEASURED = "measured"
APPLICABILITY_NOT_APPLICABLE = "not_applicable"
APPLICABILITY_INSUFFICIENT = "insufficient_cases"
APPLICABILITY_SKIPPED = "skipped"
APPLICABILITY_FAILED = "failed_to_measure"


def measured(
    name: str,
    score: float,
    *,
    numerator: int = 0,
    denominator: int = 0,
    details: dict | None = None,
) -> MetricSummary:
    return MetricSummary(
        name=name,
        score=score,
        applicability=APPLICABILITY_MEASURED,
        numerator=numerator,
        denominator=denominator,
        details=details or {},
    )


def insufficient(name: str, reason: str, *, details: dict | None = None) -> MetricSummary:
    return MetricSummary(
        name=name,
        score=None,
        applicability=APPLICABILITY_INSUFFICIENT,
        reason=reason,
        details=details or {},
    )


def not_applicable(name: str, reason: str) -> MetricSummary:
    return MetricSummary(
        name=name,
        score=None,
        applicability=APPLICABILITY_NOT_APPLICABLE,
        reason=reason,
    )
