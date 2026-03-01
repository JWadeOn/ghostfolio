"""Integration smoke test — run eval cases against a live deployed agent via the
Ghostfolio proxy (same path as a real user).

Usage:
    # Via Ghostfolio proxy (recommended — matches real user flow):
    python3 tests/eval/run_smoke_test.py \\
        --ghostfolio-url https://ghostfolio-app-production-9ea6.up.railway.app \\
        --security-token <GHOSTFOLIO_ACCESS_TOKEN>

    # Direct to trading agent (no auth, tools may lack portfolio access):
    python3 tests/eval/run_smoke_test.py \\
        --agent-url https://trading-agent-production-4edd.up.railway.app

    # Limit cases:
    python3 tests/eval/run_smoke_test.py ... --max-cases 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Ensure project root is on path
_SCRIPT_DIR = Path(__file__).resolve().parent
_AGENT_ROOT = _SCRIPT_DIR.parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from tests.eval.dataset import eval_cases
from tests.eval.run_evals import (
    PASS_THRESHOLD,
    TARGET_PASS_RATE_PCT,
    TARGET_TOOL_SUCCESS_RATE_PCT,
    WEIGHT_INTENT,
    WEIGHT_TOOLS,
    WEIGHT_CONTENT,
    WEIGHT_SAFETY,
    WEIGHT_CONFIDENCE,
    WEIGHT_VERIFICATION,
    _score_intent,
    _score_tools,
    _score_content,
    _score_safety,
    _full_response_text,
    aggregate_results,
)

MAX_LATENCY_SECONDS = 60  # generous for network round-trip


def _exchange_for_jwt(ghostfolio_url: str, security_token: str) -> str:
    """Exchange a Ghostfolio security token for a JWT."""
    r = httpx.post(
        f"{ghostfolio_url}/api/v1/auth/anonymous",
        json={"accessToken": security_token},
        timeout=10,
    )
    r.raise_for_status()
    jwt = r.json().get("authToken")
    if not jwt:
        raise RuntimeError("No authToken in response from Ghostfolio auth")
    return jwt


def run_case_via_http(
    chat_url: str,
    case: dict,
    case_id: int,
    client: httpx.Client,
    headers: dict[str, str] | None = None,
) -> dict:
    """Send a single eval case and score the response."""
    input_text = case["input"]
    expected_intent = case.get("expected_intent")
    expected_tools = case.get("expected_tools", [])
    exact_tools = case.get("exact_tools", False)
    expected_contains = case.get("expected_output_contains", [])
    should_contain = case.get("should_contain", [])
    should_not_contain = case.get("should_not_contain", [])
    category = case.get("category", "general")
    case_label = case.get("id", f"case_{case_id}")

    print(f"  [{case_id:02d}] {case_label}: {input_text[:60]}...", end=" ", flush=True)

    start = time.perf_counter()
    try:
        resp = client.post(
            chat_url,
            json={"message": input_text},
            headers=headers or {},
            timeout=MAX_LATENCY_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"ERROR ({elapsed:.1f}s)")
        return {
            "id": case_id,
            "case_id": case_label,
            "category": category,
            "input": input_text,
            "passed": False,
            "overall_score": 0.0,
            "scores": {"intent": 0, "tools": 0, "content": 0, "safety": 0, "confidence": 0, "verification": 0},
            "latency_seconds": round(elapsed, 3),
            "errors": [f"HTTP error: {e}"],
            "tools_called": [],
            "intent": "",
        }

    elapsed = time.perf_counter() - start
    response = data.get("response", {})
    summary = _full_response_text(response)
    summary_lower = summary.lower()
    tools_called = response.get("tools_used", [])
    agent_confidence = response.get("confidence", 0)
    confidence_normalized = (agent_confidence / 100.0) if isinstance(agent_confidence, (int, float)) else 0.0
    inferred_intent = response.get("intent", "general")

    intent_score = _score_intent(expected_intent, inferred_intent)
    tools_score, tools_errors = _score_tools(expected_tools, tools_called, exact_tools)
    content_score, content_errors = _score_content(summary_lower, expected_contains, should_contain)
    safety_score, safety_errors = _score_safety(summary_lower, should_not_contain)
    verification_score = 1.0

    scores = {
        "intent": intent_score,
        "tools": tools_score,
        "content": content_score,
        "safety": safety_score,
        "confidence": max(0.0, min(1.0, confidence_normalized)),
        "verification": verification_score,
    }
    overall = (
        WEIGHT_INTENT * scores["intent"]
        + WEIGHT_TOOLS * scores["tools"]
        + WEIGHT_CONTENT * scores["content"]
        + WEIGHT_SAFETY * scores["safety"]
        + WEIGHT_CONFIDENCE * scores["confidence"]
        + WEIGHT_VERIFICATION * scores["verification"]
    )

    errors = tools_errors + content_errors + safety_errors
    latency_passed = elapsed <= MAX_LATENCY_SECONDS
    if not latency_passed:
        errors.append(f"Latency {elapsed:.1f}s exceeds max {MAX_LATENCY_SECONDS}s")

    passed = overall >= PASS_THRESHOLD and len(errors) == 0
    status = "PASS" if passed else "FAIL"
    print(f"{status} (score={overall:.2f}, {elapsed:.1f}s)")

    return {
        "id": case_id,
        "case_id": case_label,
        "category": category,
        "input": input_text,
        "passed": passed,
        "overall_score": round(overall, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "latency_seconds": round(elapsed, 3),
        "latency_passed": latency_passed,
        "agent_confidence": agent_confidence,
        "errors": errors,
        "tools_called": tools_called,
        "intent": inferred_intent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run smoke test against deployed trading agent")
    parser.add_argument("--ghostfolio-url", help="Ghostfolio app URL (goes through NestJS proxy with auth)")
    parser.add_argument("--security-token", help="Ghostfolio security token (GHOSTFOLIO_ACCESS_TOKEN)")
    parser.add_argument("--agent-url", help="Direct trading agent URL (no auth, skips proxy)")
    parser.add_argument("--max-cases", type=int, default=0, help="Limit number of cases (0 = all)")
    parser.add_argument("--phase", type=int, default=1, help="Run only cases with this phase (default: 1)")
    args = parser.parse_args()

    if not args.ghostfolio_url and not args.agent_url:
        parser.error("Provide --ghostfolio-url (with --security-token) or --agent-url")

    # Determine chat URL and auth headers
    headers: dict[str, str] = {}
    if args.ghostfolio_url:
        gf_url = args.ghostfolio_url.rstrip("/")
        if not args.security_token:
            parser.error("--security-token is required with --ghostfolio-url")

        # Health check
        print(f"Checking Ghostfolio health at {gf_url}...")
        r = httpx.get(f"{gf_url}/api/v1/health", timeout=10)
        print(f"  Ghostfolio: {r.json()}")

        # Exchange security token for JWT
        print("Exchanging security token for JWT...")
        jwt = _exchange_for_jwt(gf_url, args.security_token)
        print("  JWT obtained")

        chat_url = f"{gf_url}/api/v1/trading-agent/chat"
        headers = {"Authorization": f"Bearer {jwt}"}
        display_url = gf_url
    else:
        agent_url = args.agent_url.rstrip("/")
        print(f"Checking agent health at {agent_url}...")
        r = httpx.get(f"{agent_url}/api/health", timeout=10)
        health = r.json()
        print(f"  Status: {health.get('status')} | Ghostfolio: {health.get('ghostfolio')}")
        if health.get("status") != "ok":
            print("Agent is not healthy. Aborting.")
            return 1

        chat_url = f"{agent_url}/api/chat"
        display_url = agent_url

    # Filter cases
    cases = [c for c in eval_cases if c.get("phase", 1) == args.phase]
    if args.max_cases > 0:
        cases = cases[:args.max_cases]

    print(f"\nRunning {len(cases)} cases against {display_url}\n")

    client = httpx.Client()
    results = []
    for i, case in enumerate(cases):
        result = run_case_via_http(chat_url, case, i + 1, client, headers)
        results.append(result)
    client.close()

    # Aggregate
    aggregate = aggregate_results(results)
    passed = aggregate["passed"]
    total = aggregate["total"]
    pass_rate = aggregate["pass_rate_pct"]

    # Write report
    reports_dir = _AGENT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"smoke-test-results-{ts}.json"
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_url": display_url,
        "mode": "ghostfolio_proxy" if args.ghostfolio_url else "direct_agent",
        "total": total,
        "passed": passed,
        "pass_rate_pct": pass_rate,
        "aggregate": aggregate,
        "results": results,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"Smoke Test Results: {passed}/{total} passed ({pass_rate}%)")
    print(f"Avg score: {aggregate['avg_overall_score']:.2f} (threshold={PASS_THRESHOLD})")
    print(f"Target met (>={TARGET_PASS_RATE_PCT}%): {'yes' if pass_rate >= TARGET_PASS_RATE_PCT else 'no'}")
    print(f"Report: {report_path}")
    print(f"{'='*60}")

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] [{r.get('category')}] {r['input'][:55]}")
        if not r["passed"] and r.get("errors"):
            for err in r["errors"][:3]:
                print(f"        - {err}")

    return 0 if pass_rate >= TARGET_PASS_RATE_PCT else 1


if __name__ == "__main__":
    sys.exit(main())
