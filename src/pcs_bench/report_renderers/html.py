"""Professional HTML report renderer."""

from __future__ import annotations

import html
from typing import Any

from pcs_bench.config import BenchConfig
from pcs_bench.schemas import BenchmarkReport


def _pct(score: float) -> str:
    return f"{score * 100:.1f}%"


def _metric_class(score: float, threshold: float = 0.9) -> str:
    if score >= threshold:
        return "metric-ok"
    if score >= threshold - 0.05:
        return "metric-warn"
    return "metric-fail"


def render_html(
    report: BenchmarkReport,
    comparison_text: str = "",
    config: BenchConfig | None = None,
) -> str:
    cfg = config or BenchConfig()
    thresholds = cfg.thresholds.model_dump()
    passed = sum(1 for r in report.runs if r.passed)
    failed = len(report.runs) - passed
    mode = report.summary.get("execution_mode", "n/a")

    metric_rows = ""
    summaries = report.metric_summaries or []
    if summaries:
        for summary in sorted(summaries, key=lambda s: s.name):
            thr = thresholds.get(summary.name, 0.9)
            score_txt = f"{summary.score:.3f}" if summary.score is not None else "n/a"
            cls = _metric_class(summary.score, thr) if summary.score is not None else ""
            metric_rows += f"""
        <tr>
          <td>{html.escape(summary.name)}</td>
          <td class="{cls}">{score_txt}</td>
          <td>{html.escape(summary.applicability)}</td>
          <td>{_pct(thr)}</td>
        </tr>"""
    else:
        for name, score in sorted(report.metrics.items()):
            if not isinstance(score, (int, float)):
                continue
            thr = thresholds.get(name, 0.9)
            metric_rows += f"""
        <tr>
          <td>{html.escape(name)}</td>
          <td class="{_metric_class(score, thr)}">{score:.3f}</td>
          <td>measured</td>
          <td>{_pct(thr)}</td>
        </tr>"""

    run_rows = ""
    for r in report.runs:
        status_cls = "pass" if r.passed else "fail"
        run_rows += f"""
        <tr class="{status_cls}">
          <td><code>{html.escape(r.case_id)}</code></td>
          <td>{html.escape(r.suite_id)}</td>
          <td>{html.escape(r.expected_status)}</td>
          <td>{html.escape(r.observed_status)}</td>
          <td>{html.escape(r.expected_responsible_component or '')}</td>
          <td>{html.escape(r.observed_responsible_component or '')}</td>
          <td>{'yes' if r.passed else 'no'}</td>
        </tr>"""

    localization_rows = ""
    for r in report.runs:
        if r.expected_status != "Rejected":
            continue
        match = r.observed_responsible_component == r.expected_responsible_component
        localization_rows += f"""
        <tr>
          <td><code>{html.escape(r.case_id)}</code></td>
          <td>{html.escape(r.expected_responsible_component or '')}</td>
          <td>{html.escape(r.observed_responsible_component or '')}</td>
          <td class="{'pass' if match else 'fail'}">{'yes' if match else 'no'}</td>
        </tr>"""

    commit_rows = ""
    for name, commit in report.repo_commits.model_dump().items():
        short = commit[:12] if len(commit) > 12 else commit
        commit_rows += f"<tr><td>{html.escape(name)}</td><td><code>{html.escape(short)}</code></td></tr>"

    coverage_html = _render_coverage(report.coverage)
    comparison_html = (
        f"<section><h2>Regressions versus baseline</h2><pre>{html.escape(comparison_text)}</pre></section>"
        if comparison_text
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>PCS Benchmark Report — {html.escape(report.report_id)}</title>
  <style>
    :root {{
      --bg: #0f1419;
      --surface: #1a2332;
      --text: #e7ecf3;
      --muted: #8b9cb3;
      --accent: #3d8bfd;
      --ok: #3dd68c;
      --warn: #f0c000;
      --fail: #f66d6d;
      --border: #2d3a4f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      line-height: 1.5;
    }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; }}
    h1 {{ font-size: 1.75rem; margin: 0 0 0.5rem; }}
    h2 {{ font-size: 1.25rem; margin: 2rem 0 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
    .meta {{ color: var(--muted); font-size: 0.9rem; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
    }}
    .card .value {{ font-size: 1.5rem; font-weight: 600; }}
    .card .label {{ color: var(--muted); font-size: 0.8rem; text-transform: uppercase; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }}
    th, td {{ border: 1px solid var(--border); padding: 0.5rem 0.75rem; text-align: left; }}
    th {{ background: var(--surface); color: var(--muted); font-weight: 600; }}
    tr.pass td:last-child {{ color: var(--ok); }}
    tr.fail td:last-child {{ color: var(--fail); }}
    .metric-ok {{ color: var(--ok); font-weight: 600; }}
    .metric-warn {{ color: var(--warn); font-weight: 600; }}
    .metric-fail {{ color: var(--fail); font-weight: 600; }}
    code {{ background: var(--surface); padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.85em; }}
    pre {{ background: var(--surface); padding: 1rem; overflow-x: auto; border-radius: 8px; border: 1px solid var(--border); }}
    footer {{ margin-top: 3rem; color: var(--muted); font-size: 0.85rem; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>PCS Benchmark Report</h1>
    <p class="meta">Report <code>{html.escape(report.report_id)}</code> · Suite <code>{html.escape(report.benchmark_suite_id)}</code> · Mode <code>{html.escape(mode)}</code></p>

    <div class="cards">
      <div class="card"><div class="value">{len(report.runs)}</div><div class="label">Cases</div></div>
      <div class="card"><div class="value" style="color:var(--ok)">{passed}</div><div class="label">Passed</div></div>
      <div class="card"><div class="value" style="color:var(--fail)">{failed}</div><div class="label">Failed</div></div>
    </div>

    <section>
      <h2>Metric summary</h2>
      <table>
        <thead><tr><th>Metric</th><th>Score</th><th>Applicability</th><th>Threshold</th></tr></thead>
        <tbody>{metric_rows}</tbody>
      </table>
    </section>

    {coverage_html}

    <section>
      <h2>Repo commits</h2>
      <table><thead><tr><th>Repository</th><th>Commit</th></tr></thead><tbody>{commit_rows}</tbody></table>
    </section>

    <section>
      <h2>Failure localization</h2>
      <table>
        <thead><tr><th>Case</th><th>Expected</th><th>Observed</th><th>Match</th></tr></thead>
        <tbody>{localization_rows or '<tr><td colspan="4">No rejected cases</td></tr>'}</tbody>
      </table>
    </section>

    <section>
      <h2>All cases</h2>
      <table>
        <thead><tr><th>Case</th><th>Suite</th><th>Expected</th><th>Observed</th><th>Exp. component</th><th>Obs. component</th><th>Pass</th></tr></thead>
        <tbody>{run_rows}</tbody>
      </table>
    </section>

    {comparison_html}

    <footer>
      Digest: <code>{html.escape(report.signature_or_digest or 'n/a')}</code><br/>
      Generated by pcs-bench · Proof-Carrying Science evaluation harness
    </footer>
  </div>
</body>
</html>
"""


def _render_coverage(coverage: dict[str, Any]) -> str:
    if not coverage:
        return ""
    parts = ["<section><h2>Coverage</h2><ul>"]
    fl = coverage.get("failure_localization", {})
    if fl:
        parts.append(
            f"<li>Failure localization: {fl.get('localized', 0)}/{fl.get('total_invalid', 0)} "
            f"({fl.get('accuracy', 0):.1%})</li>"
        )
    reg = coverage.get("registry", {})
    if reg.get("mean_coverage") is not None:
        parts.append(f"<li>Registry coverage: {reg['mean_coverage']:.1%}</li>")
    rend = coverage.get("rendering", {})
    if rend.get("mean_section_coverage") is not None:
        parts.append(f"<li>Rendering coverage: {rend['mean_section_coverage']:.1%}</li>")
    parts.append("</ul></section>")
    return "".join(parts)
