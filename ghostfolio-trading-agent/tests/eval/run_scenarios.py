#!/usr/bin/env python3
"""Labeled Scenario Evaluator for Portfolio Intelligence Agent.

Runs categorized test cases and reports results with coverage mapping.

Usage:
    python3 tests/eval/run_scenarios.py
    python3 tests/eval/run_scenarios.py --category single_tool
    python3 tests/eval/run_scenarios.py --subcategory portfolio
    python3 tests/eval/run_scenarios.py --difficulty straightforward
    python3 tests/eval/run_scenarios.py --report
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_AGENT_ROOT = _SCRIPT_DIR.parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

os.environ.setdefault("EVAL_MODE", "1")

from agent.config import get_settings as _get_settings

_s = _get_settings()
if _s.langchain_api_key and _s.langchain_tracing_v2:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", _s.langchain_api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", _s.langchain_project)

from tests.eval.scenarios import get_all_scenarios, get_scenarios_by_filter, scenarios
from tests.eval.golden_checks import check_tools, check_must_contain, check_must_not_contain
from tests.eval.run_evals import _apply_eval_mocks, run_single_eval

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_scenario(case: dict, agent_graph, idx: int) -> dict:
    """Run a single scenario and return structured result."""
    eval_result = run_single_eval(case, agent_graph, case_id=idx, use_mocks=True)
    response = eval_result.get("response") or {}
    response_text = response.get("summary") or ""
    tools_called = eval_result.get("tools_called") or []

    tool_ok, tool_err = check_tools(
        case.get("expected_tools", []), tools_called,
        exact=case.get("exact_tools", False),
    )

    must_contain = list(case.get("expected_output_contains") or []) + list(case.get("should_contain") or [])
    content_ok, content_err = check_must_contain(must_contain, response_text)

    negative_ok, negative_err = check_must_not_contain(
        case.get("should_not_contain", []), response_text,
    )

    passed = all([tool_ok, content_ok, negative_ok])

    return {
        "id": case.get("id", f"sc-{idx:03d}"),
        "query": case.get("query", case.get("input", "")),
        "category": case.get("category", ""),
        "subcategory": case.get("subcategory", ""),
        "difficulty": case.get("difficulty", ""),
        "passed": passed,
        "tool_check": tool_ok,
        "content_check": content_ok,
        "negative_check": negative_ok,
        "errors": [e for e in [tool_err, content_err, negative_err] if e],
        "tools_called": tools_called,
        "latency_seconds": eval_result.get("latency_seconds"),
    }


def run_all_scenarios(
    cases: list[dict],
    verbose: bool = False,
) -> list[dict]:
    """Run all scenarios with mocks."""
    from agent.graph import agent_graph

    patches = _apply_eval_mocks()
    try:
        results = []
        total = len(cases)

        current_group = ""
        for i, case in enumerate(cases):
            group = f"{case.get('category', '')}/{case.get('subcategory', '')}"
            if group != current_group:
                current_group = group
                print(f"\nCategory: {group}")

            query = case.get("query", case.get("input", ""))[:50] or "(empty)"
            print(f"  [{i + 1}/{total}] {case.get('id', '')}: {query}...")

            result = run_scenario(case, agent_graph, idx=i + 1)
            results.append(result)

            status = "✓" if result["passed"] else "✗"
            print(f"         {status} {'PASS' if result['passed'] else 'FAIL'}")

            if verbose and not result["passed"]:
                for err in result["errors"]:
                    if err:
                        print(f"           - {err}")

        return results
    finally:
        for p in patches:
            p.stop()


def print_summary(results: list[dict]) -> bool:
    """Print summary with coverage matrix."""
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pct = (passed / total * 100) if total > 0 else 0

    print(f"\n{'=' * 60}")
    print("LABELED SCENARIO RESULTS")
    print(f"{'=' * 60}")

    by_group: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        group = f"{r['category']}/{r['subcategory']}"
        by_group[group].append(r)

    for group, group_results in sorted(by_group.items()):
        g_passed = sum(1 for r in group_results if r["passed"])
        g_total = len(group_results)
        g_pct = (g_passed / g_total * 100) if g_total > 0 else 0
        print(f"\n  {group}: {g_passed}/{g_total} ({g_pct:.0f}%)")
        for r in group_results:
            status = "✓" if r["passed"] else "✗"
            print(f"    {status} {r['id']}: {r['query'][:45]}...")
            if not r["passed"] and r["errors"]:
                for err in r["errors"]:
                    if err:
                        print(f"        ERROR: {err}")

    # Coverage matrix
    print(f"\n{'=' * 60}")
    print("COVERAGE MATRIX")
    print(f"{'=' * 60}\n")

    categories = sorted(set(r["category"] for r in results))
    difficulties = sorted(set(r.get("difficulty", "unknown") for r in results))

    header = f"{'':>20} |" + "|".join(f" {d:>15} " for d in difficulties) + "|"
    print(header)
    print("-" * len(header))

    for cat in categories:
        row = f"{cat:>20} |"
        for diff in difficulties:
            subset = [r for r in results if r["category"] == cat and r.get("difficulty") == diff]
            if subset:
                p = sum(1 for r in subset if r["passed"])
                t = len(subset)
                cell = f"{p}/{t}"
            else:
                cell = "-"
            row += f" {cell:>15} |"
        print(row)

    print(f"\n{'-' * 60}")
    print(f"Overall: {passed}/{total} passed ({pct:.1f}%)")

    return passed == total


def write_report(results: list[dict], reports_dir: Path) -> Path:
    """Write timestamped JSON report."""
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    by_group: dict[str, dict] = {}
    for r in results:
        group = f"{r['category']}/{r['subcategory']}"
        if group not in by_group:
            by_group[group] = {"total": 0, "passed": 0}
        by_group[group]["total"] += 1
        if r["passed"]:
            by_group[group]["passed"] += 1

    payload = {
        "timestamp": timestamp,
        "total": total,
        "passed": passed,
        "pass_rate_pct": round(100 * passed / total, 1) if total else 0,
        "by_group": by_group,
        "cases": results,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"scenario-results-{timestamp}.json"
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nReport written to {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run labeled scenario evaluation")
    parser.add_argument("--category", type=str, help="Filter by category (single_tool, multi_tool, no_tool)")
    parser.add_argument("--subcategory", type=str, help="Filter by subcategory (portfolio, market_data, etc)")
    parser.add_argument("--difficulty", type=str, help="Filter by difficulty (straightforward, ambiguous, adversarial, edge_case)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show error details")
    parser.add_argument("--report", action="store_true", help="Write timestamped JSON report")
    args = parser.parse_args()

    print("Portfolio Intelligence Agent - Labeled Scenario Evaluation")
    print("=" * 60)

    cases = get_scenarios_by_filter(
        category=args.category,
        subcategory=args.subcategory,
        difficulty=args.difficulty,
    )
    print(f"\nLoaded {len(cases)} scenarios", end="")
    if args.category or args.subcategory or args.difficulty:
        filters = []
        if args.category:
            filters.append(f"category={args.category}")
        if args.subcategory:
            filters.append(f"subcategory={args.subcategory}")
        if args.difficulty:
            filters.append(f"difficulty={args.difficulty}")
        print(f" (filter: {', '.join(filters)})", end="")
    print()

    start = time.perf_counter()
    results = run_all_scenarios(cases, verbose=args.verbose)
    elapsed = time.perf_counter() - start

    all_passed = print_summary(results)
    print(f"\nTotal time: {elapsed:.1f}s")

    if args.report:
        reports_dir = Path(__file__).resolve().parent.parent.parent / "reports"
        write_report(results, reports_dir)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
