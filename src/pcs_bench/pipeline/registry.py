"""Workflow-to-pipeline registry."""

from __future__ import annotations

import shutil
from pathlib import Path

from pcs_bench.benchmark_vocabulary import BENCHMARK_FAILED, BENCHMARK_PASSED

from pcs_bench.cases import case_input_dir
from pcs_bench.pipeline.context import CaseExecutionContext, ExecutionMode, ObservedOutcome
from pcs_bench.pipeline.stages import (
    StageFn,
    _all_cli_missing,
    responsible_repo,
    stage_apply_simulation,
    stage_discover_artifacts,
    stage_emit_or_validate_certificate,
    stage_explain_release_chain,
    stage_finalize_analysis,
    stage_infer_from_commands,
    stage_lean_check,
    stage_scientific_memory_import,
    stage_scientific_memory_render,
    stage_scientific_memory_stale,
    stage_validate_release_chain,
    stage_verify_release_chain_pf,
    stage_verify_runtime,
    stage_verify_science_claim,
)
from pcs_bench.schemas import BenchmarkCase, BenchmarkRun, CommandRecord
from pcs_bench.schemas.benchmark import BenchmarkSuite
from pcs_bench.workspace import CaseWorkspace

# Core PCS release evaluation path (LabTrust, tool-use, computation)
RELEASE_PIPELINE: list[StageFn] = [
    stage_discover_artifacts,
    stage_validate_release_chain,
    stage_verify_runtime,
    stage_emit_or_validate_certificate,
    stage_verify_release_chain_pf,
    stage_verify_science_claim,
    stage_explain_release_chain,
    stage_lean_check,
    stage_scientific_memory_import,
    stage_scientific_memory_render,
    stage_scientific_memory_stale,
    stage_apply_simulation,
    stage_infer_from_commands,
    stage_finalize_analysis,
]

FORMAL_PIPELINE: list[StageFn] = [
    stage_discover_artifacts,
    stage_validate_release_chain,
    stage_lean_check,
    stage_apply_simulation,
    stage_infer_from_commands,
    stage_finalize_analysis,
]

MEMORY_PIPELINE: list[StageFn] = [
    stage_discover_artifacts,
    stage_scientific_memory_import,
    stage_scientific_memory_render,
    stage_scientific_memory_stale,
    stage_apply_simulation,
    stage_infer_from_commands,
    stage_finalize_analysis,
]

WORKFLOW_PIPELINES: dict[str, list[StageFn]] = {
    "hospital_lab.qc_release": RELEASE_PIPELINE,
    "agent_tool_use.safety_v0": RELEASE_PIPELINE,
    "scientific_computation.reproducibility_v0": RELEASE_PIPELINE,
    "pcs.formal_trust_kernel": FORMAL_PIPELINE,
    "pcs.scientific_memory": MEMORY_PIPELINE,
    "pcs.cross_domain": RELEASE_PIPELINE,
}


def get_pipeline_for_workflow(workflow_id: str) -> list[StageFn]:
    return WORKFLOW_PIPELINES.get(workflow_id, RELEASE_PIPELINE)


def _case_passed(
    case: BenchmarkCase,
    observed_system_outcome: str,
    observed_failure_code: str | None,
    observed_component: str | None,
) -> bool:
    from pcs_bench.benchmark_vocabulary import (
        is_invalid_release_case,
        is_valid_release_case,
    )

    if is_valid_release_case(case.expected_status, case.expected_system_outcome):
        system_ok = observed_system_outcome == (case.expected_system_outcome or "admitted")
        return system_ok
    if is_invalid_release_case(case.expected_status, case.expected_system_outcome):
        code_ok = (
            not case.expected_failure_code
            or observed_failure_code == case.expected_failure_code
        )
        component_ok = (
            not case.expected_responsible_component
            or observed_component == case.expected_responsible_component
        )
        return code_ok and component_ok
    return observed_system_outcome == case.expected_system_outcome


def stage_case_inputs(case_ws: CaseWorkspace, suite_dir: Path, case: BenchmarkCase) -> None:
    from pcs_bench.simulation import find_case_root

    case_root = find_case_root(suite_dir, case)
    if not case_root:
        return
    for _key, rel in case.input_artifacts.items():
        src = (case_root / rel).resolve()
        if not src.exists():
            continue
        dest = case_ws.input / rel.strip("/")
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def run_case_pipeline(
    case: BenchmarkCase,
    case_ws: CaseWorkspace,
    adapters,
    suite: BenchmarkSuite,
    suite_dir: Path,
    *,
    mode: ExecutionMode,
) -> BenchmarkRun:
    stage_case_inputs(case_ws, suite_dir, case)
    release_dir = case_input_dir(case_ws.root, case)
    ctx = CaseExecutionContext(
        case=case,
        case_ws=case_ws,
        suite=suite,
        suite_dir=suite_dir,
        release_dir=release_dir,
        adapters=adapters,
        mode=mode,
        verification_path=case_ws.output / "verification_result.json",
        rendered_path=case_ws.output / "rendered_claim.md",
    )
    ctx.case_ws.output.mkdir(parents=True, exist_ok=True)

    pipeline = get_pipeline_for_workflow(suite.workflow_id)
    for stage in pipeline:
        stage(ctx)

    # Hybrid: if live CLIs unavailable, fall back to fixture simulation
    if mode == ExecutionMode.HYBRID and _all_cli_missing(ctx):
        ctx.used_simulation_fallback = True
        ctx.observed = ObservedOutcome()
        stage_apply_simulation(ctx)
        stage_infer_from_commands(ctx)
        stage_finalize_analysis(ctx)

    system_outcome = ctx.observed.system_outcome or ctx.observed.status
    passed = _case_passed(
        case,
        system_outcome,
        ctx.observed.failure_code,
        ctx.observed.responsible_component,
    )

    case_ws.record_commands(ctx.commands)
    for i, cmd in enumerate(ctx.commands):
        case_ws.write_log(f"cmd-{i:03d}.log", f"exit={cmd.exit_code}\n{cmd.stdout}\n{cmd.stderr}")

    analysis_path: Path | None = None
    if ctx.analysis:
        analysis_path = case_ws.artifacts / "artifact_analysis.json"
        case_ws.artifacts.mkdir(parents=True, exist_ok=True)
        import json

        analysis_path.write_text(
            json.dumps(
                {
                    "registry_coverage": ctx.analysis.registry_coverage_ratio,
                    "certificate_field_coverage": ctx.analysis.certificate_field_coverage,
                    "rendered_section_coverage": ctx.analysis.rendered_section_coverage,
                    "rendered_sections": ctx.analysis.rendered_sections,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    first_fail = next(
        (" ".join(c.command) for c in ctx.commands if c.exit_code != 0),
        None,
    )
    component = ctx.observed.responsible_component
    repair_acceptable = bool(
        ctx.observed.repair_hint
        or (ctx.analysis and ctx.analysis.repair_hint_present)
        or (component and ctx.observed.failure_code)
    )

    if ctx.verification_path and ctx.verification_path.exists():
        from pcs_bench.failure_localization import load_failure_localization

        fl = load_failure_localization(ctx.verification_path, case.case_id)
        if fl:
            fl_path = case_ws.artifacts / "failure_localization.v0.json"
            case_ws.artifacts.mkdir(parents=True, exist_ok=True)
            fl_path.write_text(json.dumps(fl.to_dict(), indent=2), encoding="utf-8")

    return BenchmarkRun(
        run_id=ctx.run_id,
        case_id=case.case_id,
        suite_id=suite.suite_id,
        workflow_id=case.workflow_id,
        task_id=case.task_id,
        observed_status=BENCHMARK_PASSED if passed else BENCHMARK_FAILED,
        observed_system_outcome=system_outcome,
        expected_status=case.expected_status,
        expected_system_outcome=case.expected_system_outcome,
        observed_failure_code=ctx.observed.failure_code,
        expected_failure_code=case.expected_failure_code,
        observed_responsible_component=component,
        expected_responsible_component=case.expected_responsible_component,
        observed_repair_hint=ctx.observed.repair_hint,
        repair_hint_acceptable=repair_acceptable,
        commands=[
            CommandRecord(
                command=c.command,
                cwd=str(c.cwd),
                exit_code=c.exit_code,
                stdout=c.stdout[:4000],
                stderr=c.stderr[:4000],
                started_at=c.started_at.isoformat(),
                completed_at=c.completed_at.isoformat(),
                duration_ms=c.duration_ms,
            )
            for c in ctx.commands
        ],
        artifacts=[str(p.resolve()) for p in case_ws.artifacts.rglob("*") if p.is_file()],
        artifact_analysis_path=str(analysis_path.resolve()) if analysis_path else None,
        logs=[str(p) for p in case_ws.logs.glob("*.log")],
        duration_ms=sum(c.duration_ms for c in ctx.commands),
        passed=passed,
        first_failing_command=first_fail,
        responsible_repo=responsible_repo(component),
        execution_kind=_execution_kind(mode, ctx),
    )


def _execution_kind(mode: ExecutionMode, ctx: CaseExecutionContext) -> str:
    if ctx.used_simulation_fallback:
        return "hybrid_fallback"
    if mode == ExecutionMode.LIVE:
        return "live"
    if mode == ExecutionMode.DRY_RUN:
        return "dry_run"
    return "simulate"
