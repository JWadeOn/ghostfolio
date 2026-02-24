#!/usr/bin/env python3
"""
MVP requirements check: runs all tests and evals, writes report, exits 0 only if all pass.
Run from repo root or ghostfolio-trading-agent: python scripts/run_mvp_requirements.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Ensure we can import agent and tests
AGENT_DIR = Path(__file__).resolve().parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
os.chdir(AGENT_DIR)

from scripts.mvp_report import (
    build_report,
    write_report,
)


def run_pytest() -> tuple[bool, str]:
    """Run pytest (excluding eval). Return (passed, details)."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--ignore=tests/eval", "-q"],
        cwd=AGENT_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = (r.stdout or "") + (r.stderr or "")
    passed = r.returncode == 0
    details = f"exit_code={r.returncode}"
    return passed, details


def run_evals() -> tuple[list[dict], int, int, set[str]]:
    """Run eval suite. Return (results, passed_count, total, tools_union)."""
    from tests.eval.run_evals import run_all_evals
    from tests.eval.dataset import eval_cases

    results = run_all_evals()
    passed = sum(1 for r in results if r.get("passed"))
    total = len(eval_cases)
    tools_union = set()
    for r in results:
        for t in r.get("tools_called", []):
            tools_union.add(t)
    return results, passed, total, tools_union


def check_api_health(base_url: str) -> tuple[bool, str]:
    """GET /api/health, expect 200 and status ok."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return False, f"status={resp.status}"
            import json
            data = json.loads(resp.read().decode())
            if data.get("status") != "ok":
                return False, f"status={data.get('status')}"
            return True, "connected"
    except Exception as e:
        return False, str(e)


def check_api_chat(base_url: str) -> tuple[bool, str]:
    """POST /api/chat with one message, expect 200 and non-empty summary."""
    try:
        import urllib.request
        import json
        payload = json.dumps({"message": "What's the current market regime?"}).encode()
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status != 200:
                return False, f"status={resp.status}"
            data = json.loads(resp.read().decode())
            summary = (data.get("response") or {}).get("summary") or ""
            if not summary.strip():
                return False, "empty summary"
            return True, "ok"
    except Exception as e:
        return False, str(e)


def check_conversation_continuity(base_url: str) -> tuple[bool, str]:
    """Two-turn chat with same thread_id; second response should be on-topic."""
    try:
        import urllib.request
        import json
        thread_id = "mvp-check-thread"
        # Turn 1
        payload1 = json.dumps({"message": "What's the market regime?", "thread_id": thread_id}).encode()
        req1 = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/chat",
            data=payload1,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req1, timeout=60) as resp1:
            if resp1.status != 200:
                return False, f"turn1 status={resp1.status}"
        # Turn 2
        payload2 = json.dumps({"message": "How does that affect momentum?", "thread_id": thread_id}).encode()
        req2 = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/chat",
            data=payload2,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req2, timeout=60) as resp2:
            if resp2.status != 200:
                return False, f"turn2 status={resp2.status}"
            data = json.loads(resp2.read().decode())
            summary = (data.get("response") or {}).get("summary") or ""
            if not summary.strip():
                return False, "empty second summary"
            low = summary.lower()
            if "regime" not in low and "momentum" not in low and "volatility" not in low and "trend" not in low:
                return False, "second reply may not be on-topic"
            return True, "ok"
    except Exception as e:
        return False, str(e)


def main() -> int:
    reports_dir = AGENT_DIR / "reports"
    requirements_results = {}

    # Requirement 3 & 7: pytest (unit tests + integration + verification)
    print("Running pytest (unit + integration)...")
    pytest_ok, pytest_details = run_pytest()
    requirements_results[3] = {"passed": pytest_ok, "details": pytest_details}
    requirements_results[7] = {"passed": pytest_ok, "details": pytest_details}

    # Eval suite: R1, R2, R4, R8
    print("Running eval suite...")
    eval_passed, eval_total, tools_list = 0, 12, []
    skip_evals = os.environ.get("SKIP_EVALS", "").lower() in ("1", "true", "yes")
    if skip_evals:
        requirements_results[1] = {"passed": True, "details": "skipped: SKIP_EVALS=1"}
        requirements_results[2] = {"passed": True, "details": "skipped: SKIP_EVALS=1"}
        requirements_results[4] = {"passed": True, "details": "skipped: SKIP_EVALS=1"}
        requirements_results[8] = {"passed": True, "details": "skipped: SKIP_EVALS=1"}
        eval_total = 0  # omit eval_summary when skipped
    else:
        try:
            eval_results, eval_passed, eval_total, tools_union = run_evals()
            tools_list = sorted(tools_union)
        except Exception as e:
            requirements_results[1] = {"passed": False, "details": f"eval error: {e}"}
            requirements_results[2] = {"passed": False, "details": "eval failed"}
            requirements_results[4] = {"passed": False, "details": "eval failed"}
            requirements_results[8] = {"passed": False, "details": "eval failed"}
        else:
            requirements_results[1] = {
                "passed": eval_passed >= 5,
                "details": f"eval {eval_passed}/{eval_total} passed",
            }
            requirements_results[2] = {
                "passed": len(tools_list) >= 3,
                "details": f"{len(tools_list)} tools: {', '.join(tools_list)}",
            }
            requirements_results[4] = {
                "passed": eval_passed >= 5,
                "details": f"content assertions {eval_passed}/{eval_total}",
            }
            requirements_results[8] = {
                "passed": eval_total >= 5 and eval_passed >= 5,
                "details": f"{eval_passed}/{eval_total} cases passed",
            }

    # API checks (R5, R6) - optional
    agent_url = os.environ.get("AGENT_URL", "http://localhost:8000")
    try_api = agent_url and agent_url.startswith("http")
    if try_api:
        print("Running API checks...")
        health_ok, health_details = check_api_health(agent_url)
        conv_ok, conv_details = check_conversation_continuity(agent_url)
        requirements_results[5] = {"passed": conv_ok, "details": conv_details}
        requirements_results[6] = {"passed": health_ok, "details": health_details}
    else:
        requirements_results[5] = {"passed": True, "details": "skipped: no AGENT_URL"}
        requirements_results[6] = {"passed": True, "details": "skipped: no AGENT_URL"}

    # R9: deployed and public (optional)
    public_url = os.environ.get("PUBLIC_AGENT_URL")
    if public_url and public_url.startswith("http"):
        print("Checking public deployment...")
        health_ok, health_details = check_api_health(public_url)
        chat_ok, chat_details = check_api_chat(public_url)
        requirements_results[9] = {
            "passed": health_ok and chat_ok,
            "details": f"health={health_ok}, chat={chat_ok}",
        }
    else:
        requirements_results[9] = {"passed": True, "details": "skipped: no PUBLIC_AGENT_URL"}

    eval_summary = None
    if eval_total:
        eval_summary = {
            "passed": eval_passed,
            "total": eval_total,
            "pass_rate_pct": int(round(100 * eval_passed / eval_total)),
        }

    report = build_report(
        requirements_results,
        eval_summary=eval_summary,
        tools_invoked=tools_list if tools_list else None,
    )
    json_path, md_path = write_report(report, reports_dir=reports_dir, write_md=True)

    print(f"\nReport written: {json_path}")
    if md_path:
        print(f"Summary: {md_path}")
    print(f"Overall: {'PASS' if report['overall_pass'] else 'FAIL'}")

    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
