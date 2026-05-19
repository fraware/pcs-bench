"""Markdown report renderer."""

from __future__ import annotations

from pcs_bench.schemas import BenchmarkReport


def render_markdown(report: BenchmarkReport, comparison_text: str = "") -> str:
    lines: list[str] = [
        "# PCS Benchmark Report",
        "",
        "## Executive summary",
        "",
        f"- **Report ID:** {report.report_id}",
        f"- **Suite:** {report.benchmark_suite_id}",
        f"- **Started:** {report.started_at}",
        f"- **Completed:** {report.completed_at or 'in progress'}",
        f"- **Simulation:** {report.dry_run}",
        f"- **Execution mode:** {report.summary.get('execution_mode', 'n/a')}",
        "",
    ]

    summary = report.summary
    lines.extend(
        [
            f"- **Total runs:** {summary.get('total_runs', len(report.runs))}",
            f"- **Passed:** {summary.get('passed', 0)}",
            f"- **Failed:** {summary.get('failed', 0)}",
            "",
            "## Repo commits tested",
            "",
            f"| Repo | Commit |",
            f"|------|--------|",
        ]
    )
    rc = report.repo_commits
    for name, commit in rc.model_dump().items():
        short = commit[:12] if len(commit) > 12 else commit
        lines.append(f"| {name} | `{short}` |")
    lines.append("")

    lines.extend(["## Metric summary", "", "| Metric | Score |", "|--------|-------|"])
    for name, score in sorted(report.metrics.items()):
        lines.append(f"| {name} | {score:.3f} |")
    lines.append("")

    if report.coverage:
        cov = report.coverage
        lines.extend(["## Coverage", ""])
        fl = cov.get("failure_localization", {})
        if fl:
            lines.append(
                f"- Failure localization: {fl.get('localized', 0)}/{fl.get('total_invalid', 0)} "
                f"({fl.get('accuracy', 0):.2%})"
            )
        reg = cov.get("registry", {})
        if reg.get("mean_coverage") is not None:
            lines.append(f"- Registry mean coverage: {reg['mean_coverage']:.2%}")
        rend = cov.get("rendering", {})
        if rend.get("mean_section_coverage") is not None:
            lines.append(f"- Rendering mean section coverage: {rend['mean_section_coverage']:.2%}")
        lines.append("")

    suites = sorted({r.suite_id for r in report.runs})
    lines.extend(["## Suites run", ""])
    for s in suites:
        suite_runs = [r for r in report.runs if r.suite_id == s]
        passed = sum(1 for r in suite_runs if r.passed)
        lines.append(f"- **{s}:** {passed}/{len(suite_runs)} passed")
    lines.append("")

    workflows = sorted({r.case_id.split("-")[0] for r in report.runs})
    lines.extend(["## Per-suite results", ""])
    for r in report.runs:
        status = "PASS" if r.passed else "FAIL"
        lines.append(
            f"- `{r.case_id}` [{status}] expected={r.expected_status} "
            f"observed={r.observed_status}"
        )
    lines.append("")

    lines.extend(["## Failure localization matrix", ""])
    lines.append("| Case | Expected component | Observed component | Match |")
    lines.append("|------|-------------------|-------------------|-------|")
    for r in report.runs:
        if r.expected_status != "Rejected":
            continue
        match = r.observed_responsible_component == r.expected_responsible_component
        lines.append(
            f"| {r.case_id} | {r.expected_responsible_component} | "
            f"{r.observed_responsible_component} | {'yes' if match else 'no'} |"
        )
    lines.append("")

    for section_title, metric_name in [
        ("Certificate completeness", "certificate_completeness_score"),
        ("Registry coverage", "registry_coverage_score"),
        ("Formal check coverage", "formal_check_coverage_score"),
        ("Scientific Memory interpretability", "scientific_memory_interpretability_score"),
        ("Repair hint quality", "repair_hint_quality_score"),
    ]:
        score = report.metrics.get(metric_name)
        if score is not None:
            lines.extend([f"## {section_title}", "", f"Score: **{score:.3f}**", ""])

    if comparison_text:
        lines.extend(["## Regressions versus baseline", "", comparison_text, ""])

    lines.extend(["## Known limitations", ""])
    mode = report.summary.get("execution_mode", "")
    if mode in ("simulate", "dry_run", "hybrid"):
        lines.append(
            f"- Execution mode `{mode}`: results use fixture sidecars unless live CLIs succeeded."
        )
    lines.append("")

    failed = [r for r in report.runs if not r.passed]
    if failed:
        lines.extend(["## Appendix: failed cases", ""])
        for r in failed:
            lines.extend(
                [
                    f"### {r.case_id}",
                    "",
                    f"- Expected status: {r.expected_status}",
                    f"- Observed status: {r.observed_status}",
                    f"- Expected failure code: {r.expected_failure_code}",
                    f"- Observed failure code: {r.observed_failure_code}",
                    f"- First failing command: {r.first_failing_command}",
                    f"- Responsible repo: {r.responsible_repo}",
                    "",
                ]
            )

    if report.signature_or_digest:
        lines.extend(["---", "", f"Digest: `{report.signature_or_digest}`", ""])

    return "\n".join(lines)
