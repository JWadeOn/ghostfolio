"""MVP requirements test report: schema and writers for JSON + Markdown."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIREMENT_NAMES = {
    1: "Natural language domain queries",
    2: "At least 3 functional tools invoked",
    3: "Tools execute successfully and return structured results",
    4: "Agent synthesizes tool results into coherent responses",
    5: "Conversation history maintained across turns",
    6: "Basic error handling (graceful failure, no crashes)",
    7: "At least one domain-specific verification check",
    8: "Simple evaluation: 5+ test cases with expected outcomes",
    9: "Deployed and publicly accessible",
}


def build_report(
    requirements_results: dict[int, dict[str, Any]],
    eval_summary: dict[str, Any] | None = None,
    tools_invoked: list[str] | None = None,
    log_path: str | None = None,
) -> dict[str, Any]:
    """
    Build the MVP requirements report dict.
    requirements_results: { req_id: {"passed": bool, "details": str|None }, ... }
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    requirements = []
    for rid in range(1, 10):
        name = REQUIREMENT_NAMES.get(rid, "")
        r = requirements_results.get(rid, {"passed": False, "details": "not run"})
        requirements.append({
            "id": rid,
            "name": name,
            "passed": r.get("passed", False),
            "details": r.get("details"),
        })
    overall_pass = all(r["passed"] for r in requirements)
    report = {
        "timestamp": timestamp,
        "overall_pass": overall_pass,
        "requirements": requirements,
    }
    if eval_summary is not None:
        report["eval_summary"] = eval_summary
    if tools_invoked is not None:
        report["tools_invoked"] = tools_invoked
    if log_path is not None:
        report["log_path"] = log_path
    return report


def write_report(
    report: dict[str, Any],
    reports_dir: str | Path = "reports",
    write_md: bool = True,
) -> tuple[Path, Path | None]:
    """
    Write report to reports_dir as JSON and optionally Markdown.
    Creates reports_dir if missing. Returns (json_path, md_path or None).
    """
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / "mvp-requirements-report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    md_path = None
    if write_md:
        md_path = reports_dir / "mvp-requirements-report.md"
        with open(md_path, "w") as f:
            f.write(_report_to_markdown(report))
    return json_path, md_path


def _report_to_markdown(report: dict[str, Any]) -> str:
    """Generate a short Markdown summary of the report."""
    lines = [
        f"# MVP Requirements Report",
        f"",
        f"**Timestamp:** {report.get('timestamp', '')}",
        f"**Overall:** {'PASS' if report.get('overall_pass') else 'FAIL'}",
        f"",
        "| # | Requirement | Status | Details |",
        "|---|-------------|--------|---------|",
    ]
    for r in report.get("requirements", []):
        status = "PASS" if r.get("passed") else "FAIL"
        details = r.get("details") or ""
        if isinstance(details, dict):
            details = str(details)[:60]
        details = (details[:50] + "…") if len(str(details)) > 50 else str(details)
        lines.append(f"| {r['id']} | {r['name']} | {status} | {details} |")
    if report.get("eval_summary"):
        es = report["eval_summary"]
        lines.append("")
        lines.append(f"**Eval:** {es.get('passed', 0)}/{es.get('total', 0)} passed ({es.get('pass_rate_pct', 0)}%)")
    if report.get("tools_invoked"):
        lines.append(f"**Tools invoked:** {', '.join(report['tools_invoked'])}")
    return "\n".join(lines)
