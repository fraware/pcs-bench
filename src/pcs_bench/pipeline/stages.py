"""Declarative PCS evaluation pipeline stages."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from pcs_bench.adapters.base import CommandResult
from pcs_bench.artifacts import discover_release_layout, enrich_analysis
from pcs_bench.benchmark_vocabulary import (
    SYSTEM_ADMITTED,
    SYSTEM_REJECTED,
    is_benchmark_pass_expected,
)
from pcs_bench.pipeline.context import CaseExecutionContext, ExecutionMode, ObservedOutcome
from pcs_bench.constants import RESPONSIBLE_COMPONENT_TO_REPO
from pcs_bench.simulation import simulate_outcome

StageFn = Callable[[CaseExecutionContext], None]


def stage_discover_artifacts(ctx: CaseExecutionContext) -> None:
    ctx.analysis = discover_release_layout(ctx.release_dir)
    manifest = ctx.analysis.manifest_path
    if manifest:
        data = json.loads(Path(manifest).read_text(encoding="utf-8"))
        ctx.claim_id = data.get("release_id") or data.get("claim_id") or ctx.case.case_id
    ctx.stage_notes["discover"] = "ok"


def stage_validate_release_chain(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli():
        return
    result = ctx.adapters.pcs_core.validate_release_chain(ctx.release_dir)
    ctx.record(result)
    ctx.release_chain_path = ctx.output_path("release_chain_validation.json")
    if ctx.release_chain_path.exists():
        return
    if result.exit_code != 0:
        _apply_cli_failure(ctx, result, default_component="registry")


def stage_verify_runtime(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli():
        return
    if ctx.suite.workflow_id != "hospital_lab.qc_release":
        return
    result = ctx.adapters.labtrust.verify_release_protocol(ctx.release_dir)
    ctx.record(result)
    if result.exit_code != 0:
        _apply_cli_failure(ctx, result, default_component="runtime_producer")


def stage_emit_or_validate_certificate(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli() or not ctx.analysis:
        return
    handoff = ctx.analysis.handoff_path
    if not handoff:
        return
    profile_registry = ctx.adapters.certifyedge.repo_path / "profiles"
    if not profile_registry.exists():
        profile_registry = ctx.release_dir
    cert_out = ctx.output_path("emitted_certificate.json")
    handoff_out = ctx.output_path("handoff_out.json")
    if is_benchmark_pass_expected(ctx.case.expected_status):
        result = ctx.adapters.certifyedge.emit_certificate(
            Path(handoff),
            profile_registry,
            cert_out,
            handoff_out,
        )
        ctx.record(result)
        if cert_out.exists() and ctx.analysis:
            ctx.analysis.certificate_paths.append(str(cert_out))
    else:
        profile = ctx.case.workflow_id
        cases_dir = ctx.release_dir
        bench_out = ctx.output_path("certifyedge_benchmark")
        bench_out.mkdir(exist_ok=True)
        result = ctx.adapters.certifyedge.benchmark_certificates(
            profile, cases_dir, bench_out
        )
        ctx.record(result)


def stage_verify_release_chain_pf(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli() or not ctx.analysis:
        return
    manifest = ctx.analysis.manifest_path
    registry = ctx.analysis.registry_path
    if not manifest or not registry:
        return
    out = ctx.output_path("release_chain_validation.json")
    result = ctx.adapters.pf.verify_release_chain(
        Path(manifest), ctx.release_dir, Path(registry), out
    )
    ctx.record(result)
    ctx.release_chain_path = out


def stage_verify_science_claim(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli() or not ctx.analysis:
        return
    if not ctx.analysis.bundle_paths or not ctx.analysis.handoff_path:
        return
    registry = Path(ctx.analysis.registry_path) if ctx.analysis.registry_path else None
    if not registry:
        return
    profile = ctx.release_dir / "admission_profile.v0.json"
    if not profile.exists():
        profile = ctx.release_dir / "admission_profile.json"
    if not profile.exists():
        return
    out = ctx.output_path("verification_result.json")
    rcr = ctx.release_chain_path if ctx.release_chain_path and ctx.release_chain_path.exists() else None
    result = ctx.adapters.pf.verify_science_claim(
        Path(ctx.analysis.bundle_paths[0]),
        Path(ctx.analysis.handoff_path),
        registry,
        profile,
        out,
        rcr,
    )
    ctx.record(result)
    ctx.verification_path = out
    _merge_verification_file(ctx, out)


def stage_explain_release_chain(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli():
        return
    path = ctx.release_chain_path or ctx.output_path("release_chain_validation.json")
    if not path.exists():
        return
    result = ctx.adapters.pf.explain_release_chain(path)
    ctx.record(result)
    explain_out = ctx.output_path("release_chain_explanation.json")
    if result.stdout.strip():
        explain_out.write_text(result.stdout, encoding="utf-8")


def stage_lean_check(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli() or not ctx.analysis:
        return
    obligations = list(ctx.release_dir.glob("**/*obligation*.json"))
    if not obligations:
        return
    out = ctx.output_path("lean_check_result.json")
    result = ctx.adapters.pcs_core.lean_check(obligations[0], out)
    ctx.record(result)


def stage_scientific_memory_import(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli() or not ctx.analysis or not ctx.analysis.manifest_path:
        return
    result = ctx.adapters.scientific_memory.import_release(Path(ctx.analysis.manifest_path))
    ctx.record(result)


def stage_scientific_memory_render(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli():
        return
    claim_id = ctx.claim_id or ctx.case.case_id
    result = ctx.adapters.scientific_memory.render_claim(claim_id)
    ctx.record(result)
    ctx.rendered_path = ctx.output_path("rendered_claim.md")
    if result.stdout.strip():
        ctx.rendered_path.write_text(result.stdout, encoding="utf-8")


def _all_cli_missing(ctx: CaseExecutionContext) -> bool:
    if not ctx.commands:
        return True
    return all(c.exit_code == 127 for c in ctx.commands)


def stage_scientific_memory_stale(ctx: CaseExecutionContext) -> None:
    if not ctx.should_invoke_cli():
        return
    stale_kinds = {"stale_trace", "stale_trace_after_certificate"}
    if ctx.case.case_kind not in stale_kinds and "stale" not in ctx.case.case_id:
        return
    claim_id = ctx.claim_id or ctx.case.case_id
    result = ctx.adapters.scientific_memory.check_stale(claim_id)
    ctx.record(result)


def stage_finalize_analysis(ctx: CaseExecutionContext) -> None:
    if not ctx.analysis:
        ctx.analysis = discover_release_layout(ctx.release_dir)
    ctx.verification_path = ctx.verification_path or ctx.output_path("verification_result.json")
    if not ctx.verification_path.exists():
        sidecar = _find_expected(ctx, "verification_result.json")
        if sidecar:
            shutil.copy2(sidecar, ctx.verification_path)
    rendered = ctx.rendered_path or ctx.output_path("rendered_claim.md")
    if not rendered.exists():
        sidecar = _find_expected(ctx, "rendered_sections.json")
        if sidecar:
            rendered = ctx.output_path("rendered_sections.json")
            shutil.copy2(sidecar, rendered)
            ctx.rendered_path = rendered
    ctx.analysis = enrich_analysis(
        ctx.analysis,
        verification_path=ctx.verification_path if ctx.verification_path.exists() else None,
        rendered_path=ctx.rendered_path if ctx.rendered_path and ctx.rendered_path.exists() else None,
    )
    if ctx.analysis.verification:
        _merge_verification_dict(ctx, ctx.analysis.verification)


def stage_apply_simulation(ctx: CaseExecutionContext) -> None:
    if ctx.mode == ExecutionMode.HYBRID:
        return
    if ctx.mode not in (ExecutionMode.DRY_RUN, ExecutionMode.SIMULATE):
        return
    sim = simulate_outcome(ctx.case, ctx.suite_dir)
    ctx.observed = ObservedOutcome(
        status=sim.status,
        system_outcome=sim.system_outcome or sim.status,
        failure_code=sim.failure_code,
        responsible_component=sim.responsible_component,
        repair_hint=sim.repair_hint,
        repair_hint_kind=sim.repair_hint_kind,
    )
    if sim.verification and ctx.verification_path:
        ctx.verification_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.verification_path.write_text(json.dumps(sim.verification, indent=2), encoding="utf-8")
    if sim.rendered_sections and ctx.rendered_path:
        ctx.rendered_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.rendered_path.write_text(
            json.dumps({"sections": sim.rendered_sections}, indent=2),
            encoding="utf-8",
        )
    ctx.stage_notes["simulation"] = sim.source


def stage_infer_from_commands(ctx: CaseExecutionContext) -> None:
    if ctx.observed.status != "Unknown":
        return
    failed = [c for c in ctx.commands if c.exit_code != 0]
    if not failed and is_benchmark_pass_expected(ctx.case.expected_status):
        ctx.observed.system_outcome = SYSTEM_ADMITTED
        ctx.observed.status = SYSTEM_ADMITTED
        return
    if failed:
        ctx.observed.system_outcome = SYSTEM_REJECTED
        ctx.observed.status = SYSTEM_REJECTED
        ctx.observed.failure_code = ctx.observed.failure_code or ctx.case.expected_failure_code
        ctx.observed.responsible_component = (
            ctx.observed.responsible_component
            or _component_from_command(failed[0])
            or ctx.case.expected_responsible_component
        )
        if not ctx.observed.repair_hint:
            ctx.observed.repair_hint = _hint_from_stderr(failed[0])
    elif is_benchmark_pass_expected(ctx.case.expected_status):
        ctx.observed.system_outcome = SYSTEM_ADMITTED
        ctx.observed.status = SYSTEM_ADMITTED
    else:
        ctx.observed.system_outcome = ctx.case.expected_system_outcome or SYSTEM_REJECTED
        ctx.observed.status = ctx.observed.system_outcome


def _find_expected(ctx: CaseExecutionContext, name: str) -> Path | None:
    from pcs_bench.simulation import find_case_root

    case_root = find_case_root(ctx.suite_dir, ctx.case)
    if case_root:
        candidate = case_root / "expected" / name
        if candidate.exists():
            return candidate
    return None


def _merge_verification_file(ctx: CaseExecutionContext, path: Path) -> None:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        _merge_verification_dict(ctx, data)


def _merge_verification_dict(ctx: CaseExecutionContext, data: dict) -> None:
    from pcs_bench.benchmark_vocabulary import system_outcome_from_sidecar

    ctx.observed.status = data.get("status") or data.get("admission_status") or ctx.observed.status
    ctx.observed.system_outcome = system_outcome_from_sidecar(data)
    ctx.observed.failure_code = data.get("failure_code") or data.get("code") or ctx.observed.failure_code
    ctx.observed.responsible_component = (
        data.get("responsible_component") or ctx.observed.responsible_component
    )
    hint = data.get("repair_hint") or data.get("repair_hint_kind")
    if hint:
        ctx.observed.repair_hint = hint if isinstance(hint, str) else json.dumps(hint)


def _apply_cli_failure(
    ctx: CaseExecutionContext,
    result: CommandResult,
    *,
    default_component: str,
) -> None:
    if ctx.observed.status == "Unknown":
        ctx.observed.system_outcome = SYSTEM_REJECTED
        ctx.observed.status = SYSTEM_REJECTED
    ctx.observed.responsible_component = (
        ctx.observed.responsible_component or _component_from_command(result) or default_component
    )
    if not ctx.observed.failure_code:
        ctx.observed.failure_code = _code_from_stderr(result) or ctx.case.expected_failure_code
    if not ctx.observed.repair_hint:
        ctx.observed.repair_hint = _hint_from_stderr(result)


def _component_from_command(result: CommandResult) -> str | None:
    joined = " ".join(result.command).lower()
    if "labtrust" in joined:
        return "runtime_producer"
    if "certifyedge" in joined:
        return "certificate_producer"
    if "pf" in joined:
        return "verifier"
    if "registry" in joined:
        return "registry"
    if "lean-check" in joined:
        return "formal_kernel"
    if "pcs-import" in joined or "render" in joined:
        return "scientific_memory"
    return None


def _code_from_stderr(result: CommandResult) -> str | None:
    text = (result.stderr + result.stdout).lower()
    for code in (
        "trace_hash_mismatch",
        "certificate_id_mismatch",
        "handoff_schema_mismatch",
        "placeholder_commit_detected",
        "policy_hash_mismatch",
        "result_hash_mismatch",
        "missing_qc_result",
        "unauthorized_release",
        "stale_trace_after_certificate",
        "lean_theorem_failed",
    ):
        if code in text:
            return code
    return None


def _hint_from_stderr(result: CommandResult) -> str | None:
    if result.stderr.strip():
        return result.stderr.strip()[:500]
    return None


def responsible_repo(component: str | None) -> str | None:
    if not component:
        return None
    return RESPONSIBLE_COMPONENT_TO_REPO.get(component, "unknown")
