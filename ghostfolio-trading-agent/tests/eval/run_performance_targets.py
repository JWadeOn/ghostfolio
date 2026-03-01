#!/usr/bin/env python3
"""PRD §3.7 Performance Targets Validation.

Runs the combined golden + dataset eval suite, measures all 6 PRD performance
targets, prints a pass/fail table, and writes a timestamped JSON report.

Targets:
  1. End-to-end latency   — p95 < 5s for single-tool queries
  2. Multi-step latency   — p95 < 15s for 3+ tool chains
  3. Tool success rate     — > 95% successful execution
  4. Eval pass rate        — > 80% on test suite
  5. Hallucination rate    — < 5% unsupported claims
  6. Verification accuracy — > 90% correct flags

Usage:
    python3 tests/eval/run_performance_targets.py
    python3 tests/eval/run_performance_targets.py --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_AGENT_ROOT = _SCRIPT_DIR.parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

os.environ.setdefault("EVAL_MODE", "1")

from tests.eval.dataset import eval_cases
from tests.eval.golden_cases import GOLDEN_CASES
from tests.eval.run_evals import _apply_eval_mocks, run_single_eval

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── PRD §3.7 thresholds ──────────────────────────────────────────────────
TARGET_E2E_LATENCY_P95 = 5.0        # seconds
TARGET_MULTI_STEP_LATENCY_P95 = 15.0  # seconds
TARGET_TOOL_SUCCESS_RATE = 95.0      # percent
TARGET_EVAL_PASS_RATE = 80.0         # percent
TARGET_HALLUCINATION_RATE = 5.0      # percent (upper bound)
TARGET_VERIFICATION_ACCURACY = 90.0  # percent


def _percentile(values: list[float], pct: int) -> float:
    """Return the pct-th percentile of a sorted list (nearest-rank)."""
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, int(len(s) * pct / 100) - 1)
    return s[k]


def _deduplicate_cases(golden: list[dict], dataset: list[dict]) -> list[dict]:
    """Merge golden + dataset cases, deduplicating by input text."""
    seen: set[str] = set()
    merged: list[dict] = []
    for case in golden + dataset:
        key = case["input"].strip().lower()
        if key not in seen:
            seen.add(key)
            merged.append(case)
    return merged


def _classify_tool_count(tools_called: list[str]) -> str:
    n = len(tools_called)
    if n == 0:
        return "no_tool"
    if n == 1:
        return "single_tool"
    if n == 2:
        return "two_tool"
    return "multi_step"


def compute_targets(results: list[dict]) -> dict:
    """Compute all 6 PRD performance targets from eval results."""
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))

    # Classify results by tool count
    for r in results:
        r["_tool_class"] = _classify_tool_count(r.get("tools_called", []))

    # 1. End-to-end latency (single-tool cases)
    single_latencies = [
        r["latency_seconds"] for r in results
        if r["_tool_class"] == "single_tool" and r.get("latency_seconds") is not None
    ]
    e2e_p95 = _percentile(single_latencies, 95)
    e2e_avg = sum(single_latencies) / len(single_latencies) if single_latencies else 0.0
    e2e_max = max(single_latencies) if single_latencies else 0.0

    # 2. Multi-step latency (3+ tools)
    multi_latencies = [
        r["latency_seconds"] for r in results
        if r["_tool_class"] == "multi_step" and r.get("latency_seconds") is not None
    ]
    ms_p95 = _percentile(multi_latencies, 95)
    ms_avg = sum(multi_latencies) / len(multi_latencies) if multi_latencies else 0.0
    ms_max = max(multi_latencies) if multi_latencies else 0.0

    # 3. Tool success rate
    cases_with_tools = [r for r in results if r.get("tools_called")]
    cases_with_tool_errors = [r for r in cases_with_tools if r.get("tool_errors")]
    tool_success_rate = (
        (len(cases_with_tools) - len(cases_with_tool_errors)) / len(cases_with_tools) * 100
        if cases_with_tools else 100.0
    )

    # 4. Eval pass rate
    eval_pass_rate = (passed / total * 100) if total else 0.0

    # 5. Hallucination rate — cases where verification explicitly failed
    cases_with_verification = [r for r in results if r.get("verification_passed") is not None]
    verification_failed = sum(1 for r in cases_with_verification if r.get("verification_passed") is False)
    hallucination_rate = (
        verification_failed / len(cases_with_verification) * 100
        if cases_with_verification else 0.0
    )

    # 6. Verification accuracy — cases where verification passed
    verification_passed_count = sum(1 for r in cases_with_verification if r.get("verification_passed") is True)
    verification_accuracy = (
        verification_passed_count / len(cases_with_verification) * 100
        if cases_with_verification else 100.0
    )

    targets = {
        "end_to_end_latency": {
            "target": f"<{TARGET_E2E_LATENCY_P95}s",
            "p95": round(e2e_p95, 3),
            "avg": round(e2e_avg, 3),
            "max": round(e2e_max, 3),
            "sample_size": len(single_latencies),
            "passed": e2e_p95 < TARGET_E2E_LATENCY_P95,
        },
        "multi_step_latency": {
            "target": f"<{TARGET_MULTI_STEP_LATENCY_P95}s",
            "p95": round(ms_p95, 3),
            "avg": round(ms_avg, 3),
            "max": round(ms_max, 3),
            "sample_size": len(multi_latencies),
            "passed": ms_p95 < TARGET_MULTI_STEP_LATENCY_P95,
        },
        "tool_success_rate": {
            "target": f">{TARGET_TOOL_SUCCESS_RATE}%",
            "measured": round(tool_success_rate, 1),
            "cases_with_tools": len(cases_with_tools),
            "cases_with_errors": len(cases_with_tool_errors),
            "passed": tool_success_rate > TARGET_TOOL_SUCCESS_RATE,
        },
        "eval_pass_rate": {
            "target": f">{TARGET_EVAL_PASS_RATE}%",
            "measured": round(eval_pass_rate, 1),
            "passed_count": passed,
            "total_count": total,
            "passed": eval_pass_rate > TARGET_EVAL_PASS_RATE,
        },
        "hallucination_rate": {
            "target": f"<{TARGET_HALLUCINATION_RATE}%",
            "measured": round(hallucination_rate, 1),
            "verification_ran": len(cases_with_verification),
            "verification_failed": verification_failed,
            "passed": hallucination_rate < TARGET_HALLUCINATION_RATE,
        },
        "verification_accuracy": {
            "target": f">{TARGET_VERIFICATION_ACCURACY}%",
            "measured": round(verification_accuracy, 1),
            "verification_ran": len(cases_with_verification),
            "verification_passed": verification_passed_count,
            "passed": verification_accuracy > TARGET_VERIFICATION_ACCURACY,
        },
    }

    all_met = all(t["passed"] for t in targets.values())
    return {"targets": targets, "all_targets_met": all_met}


def print_table(targets: dict, all_met: bool) -> None:
    """Print a formatted pass/fail table for the 6 metrics."""
    print(f"\n{'=' * 72}")
    print("PRD §3.7 PERFORMANCE TARGETS")
    print(f"{'=' * 72}")
    print(f"{'Metric':<28} {'Target':<12} {'Measured':<14} {'Result':<6}")
    print(f"{'-' * 28} {'-' * 12} {'-' * 14} {'-' * 6}")

    rows = [
        ("End-to-end latency (p95)", targets["end_to_end_latency"]["target"],
         f"{targets['end_to_end_latency']['p95']:.2f}s (n={targets['end_to_end_latency']['sample_size']})",
         targets["end_to_end_latency"]["passed"]),
        ("Multi-step latency (p95)", targets["multi_step_latency"]["target"],
         f"{targets['multi_step_latency']['p95']:.2f}s (n={targets['multi_step_latency']['sample_size']})",
         targets["multi_step_latency"]["passed"]),
        ("Tool success rate", targets["tool_success_rate"]["target"],
         f"{targets['tool_success_rate']['measured']:.1f}%",
         targets["tool_success_rate"]["passed"]),
        ("Eval pass rate", targets["eval_pass_rate"]["target"],
         f"{targets['eval_pass_rate']['measured']:.1f}% ({targets['eval_pass_rate']['passed_count']}/{targets['eval_pass_rate']['total_count']})",
         targets["eval_pass_rate"]["passed"]),
        ("Hallucination rate", targets["hallucination_rate"]["target"],
         f"{targets['hallucination_rate']['measured']:.1f}%",
         targets["hallucination_rate"]["passed"]),
        ("Verification accuracy", targets["verification_accuracy"]["target"],
         f"{targets['verification_accuracy']['measured']:.1f}%",
         targets["verification_accuracy"]["passed"]),
    ]

    for label, target, measured, ok in rows:
        status = "PASS" if ok else "FAIL"
        print(f"{label:<28} {target:<12} {measured:<14} {status}")

    print(f"{'-' * 72}")
    overall = "ALL TARGETS MET" if all_met else "TARGETS NOT MET"
    print(f"Overall: {overall}")
    print(f"{'=' * 72}")


def write_report(results: list[dict], target_data: dict) -> Path:
    """Write timestamped JSON report to reports/."""
    reports_dir = _AGENT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"performance-targets-{timestamp}.json"

    per_case_latency = {}
    for r in results:
        cls = r.get("_tool_class", "unknown")
        if cls not in per_case_latency:
            per_case_latency[cls] = []
        per_case_latency[cls].append({
            "id": r.get("id"),
            "input": r.get("input", "")[:80],
            "latency_seconds": r.get("latency_seconds"),
            "tools_called": r.get("tools_called", []),
        })

    payload = {
        "timestamp": timestamp,
        "total_cases": len(results),
        "all_targets_met": target_data["all_targets_met"],
        "targets": target_data["targets"],
        "per_case_latency": per_case_latency,
    }

    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nReport written to {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PRD §3.7 performance targets")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-case details")
    args = parser.parse_args()

    from agent.graph import agent_graph

    # Combine and deduplicate golden + dataset cases
    all_cases = _deduplicate_cases(GOLDEN_CASES, eval_cases)
    print(f"PRD §3.7 Performance Targets Validation")
    print(f"Golden: {len(GOLDEN_CASES)} | Dataset: {len(eval_cases)} | Deduplicated: {len(all_cases)}")
    print()

    patches = _apply_eval_mocks()
    try:
        results: list[dict] = []
        total = len(all_cases)
        start_all = time.perf_counter()

        for i, case in enumerate(all_cases):
            query = case["input"][:55] or "(empty)"
            logger.info(f"[{i + 1}/{total}] {query}...")
            r = run_single_eval(case, agent_graph, case_id=i + 1, use_mocks=True)
            results.append(r)
            status = "PASS" if r["passed"] else "FAIL"
            logger.info(f"  {status} (score={r['overall_score']:.2f}, {r['latency_seconds']:.1f}s)")

        elapsed = time.perf_counter() - start_all
    finally:
        for p in patches:
            p.stop()

    # Compute targets
    target_data = compute_targets(results)
    print_table(target_data["targets"], target_data["all_targets_met"])

    # Verbose per-case output
    if args.verbose:
        print(f"\nPer-case results ({total} cases, {elapsed:.1f}s total):")
        for r in results:
            cls = r.get("_tool_class", "?")
            status = "PASS" if r["passed"] else "FAIL"
            tools = ", ".join(r.get("tools_called", [])) or "(none)"
            print(f"  [{status}] [{cls}] {r['input'][:50]}  ({r['latency_seconds']:.1f}s) tools=[{tools}]")
            if not r["passed"] and r.get("errors"):
                for err in r["errors"][:3]:
                    print(f"        - {err}")

    # Write report
    report_path = write_report(results, target_data)

    return 0 if target_data["all_targets_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
