"""Benchmark*.v0-compatible models (consumed from pcs-core; not redefined)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class BenchmarkCase(BaseModel):
    schema_version: str = "v0"
    case_id: str
    task_id: str
    workflow_id: str
    case_kind: str
    input_artifacts: dict[str, str] = Field(default_factory=dict)
    expected_status: str
    expected_system_outcome: str | None = None
    expected_failure_code: str | None = None
    expected_responsible_component: str | None = None
    expected_repair_hint_kind: str | None = None
    source_repo: str | None = None
    source_commit: str | None = None
    signature_or_digest: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class SuiteCaseRef(BaseModel):
    case_id: str
    path: str


class BenchmarkSuite(BaseModel):
    suite_id: str
    workflow_id: str
    domain: str
    description: str = ""
    cases: list[SuiteCaseRef] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(default_factory=list)
    optional_metrics: list[str] = Field(default_factory=list)
    live_required_for_release: bool = False


class CommandRecord(BaseModel):
    command: list[str]
    cwd: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    started_at: str
    completed_at: str
    duration_ms: int


class BenchmarkRun(BaseModel):
    run_id: str
    case_id: str
    suite_id: str
    workflow_id: str | None = None
    task_id: str | None = None
    observed_status: str
    observed_system_outcome: str | None = None
    expected_status: str
    expected_system_outcome: str | None = None
    observed_failure_code: str | None = None
    expected_failure_code: str | None = None
    observed_responsible_component: str | None = None
    expected_responsible_component: str | None = None
    observed_repair_hint: str | None = None
    expected_repair_hint_kind: str | None = None
    repair_hint_acceptable: bool | None = None
    artifact_analysis_path: str | None = None
    commands: list[CommandRecord] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    passed: bool = False
    first_failing_command: str | None = None
    responsible_repo: str | None = None
    execution_kind: str | None = None


class MetricSummary(BaseModel):
    name: str
    score: float | None = None
    applicability: str = "measured"
    reason: str | None = None
    numerator: int = 0
    denominator: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


class FailureRecord(BaseModel):
    case_id: str
    suite_id: str
    reason: str
    responsible_repo: str | None = None
    responsible_component: str | None = None
    repair_hint: str | None = None
    logs_path: str | None = None
    artifacts_path: str | None = None


class RepoCommits(BaseModel):
    pcs_core: str = "unknown"
    labtrust: str = "unknown"
    certifyedge: str = "unknown"
    provability_fabric: str = "unknown"
    scientific_memory: str = "unknown"
    pcs_bench: str = "unknown"


class BenchmarkReport(BaseModel):
    schema_version: str = "v0"
    report_id: str = Field(default_factory=lambda: f"pcs-bench-report-{uuid4().hex[:12]}")
    benchmark_suite_id: str = "all"
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str | None = None
    source_repo: str | None = None
    source_commit: str | None = None
    repo_commits: RepoCommits = Field(default_factory=RepoCommits)
    runs: list[BenchmarkRun] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    metric_summaries: list[MetricSummary] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    failures: list[FailureRecord] = Field(default_factory=list)
    signature_or_digest: str | None = None
    dry_run: bool = False

    def finalize(self, digest: str | None = None) -> None:
        self.completed_at = datetime.now(timezone.utc).isoformat()
        if digest:
            self.signature_or_digest = digest
