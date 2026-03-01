"""Deterministic, binary checks for the golden eval set.

Seven check types — all pure functions, no LLM calls:
  1. Tool selection     — required tools present; or expected_tools_any: at least one of list or no tools; or expected_tools_plus_any_of: all expected_tools plus at least one of list. No extras when exact_tools is set.
  2. Tool execution     — for cases that called tools, no tool returned an error (tool_errors empty).
  3. Source citation     — expected source references appear in response text (expected_sources)
                          AND/OR expected authoritative source IDs appear in response.authoritative_sources
                          (expected_authoritative_sources). Both sub-checks feed into one dimension.
  4. Content validation  — all must_contain terms appear in response; optionally at least one of expected_output_contains_any.
  5. Negative validation — no must_not_contain terms, no give-up phrases, non-empty.
  6. Ground truth        — known mock-data values appear in response (e.g. "$187.50").
  7. Structural          — react_step count and per-case latency within budget.
"""

from __future__ import annotations


DEFAULT_GIVE_UP_PHRASES = [
    "i couldn't",
    "i was unable",
    "i don't have access",
    "unable to process",
    "unable to retrieve",
    "i cannot access",
]


def check_tools(expected: list[str], actual: list[str], exact: bool = False) -> tuple[bool, str]:
    """Check if expected tools were called. Returns (passed, error_message)."""
    missing = [t for t in expected if t not in actual]
    if missing:
        return (False, f"Missing tools: {missing}")

    if exact:
        extra = [t for t in actual if t not in expected]
        if extra:
            return (False, f"Extra tools (exact_tools=True): {extra}")

    if not expected and actual:
        return (False, f"Expected no tools but agent called: {actual}")

    return (True, "")


def check_tools_any(expected_any: list[str], actual: list[str]) -> tuple[bool, str]:
    """Pass if at least one of expected_any was called, or no tools were called (e.g. ask-for-details flow)."""
    if not expected_any:
        return (True, "")
    if not actual:
        return (True, "")
    for t in expected_any:
        if t in actual:
            return (True, "")
    return (False, f"Expected one of {expected_any} or no tools; got: {actual}")


def check_tools_plus_any_of(
    expected: list[str], expected_one_of: list[str], actual: list[str]
) -> tuple[bool, str]:
    """Pass if all expected tools were called AND at least one of expected_one_of was called."""
    ok, err = check_tools(expected, actual)
    if not ok:
        return (False, err)
    if not expected_one_of:
        return (True, "")
    for t in expected_one_of:
        if t in actual:
            return (True, "")
    return (False, f"Expected all of {expected} and at least one of {expected_one_of}; got: {actual}")


def check_sources(expected: list[str], response_text: str) -> tuple[bool, str]:
    """Check that expected source references appear in the response text."""
    if not expected:
        return (True, "")

    text_lower = response_text.lower()
    missing = [s for s in expected if s.lower() not in text_lower]

    if missing:
        return (False, f"Missing source references: {missing}")

    return (True, "")


def check_authoritative_sources(
    expected_ids: list[str],
    authoritative_sources: list[dict],
) -> tuple[bool, str]:
    """Check that expected authoritative source IDs appear in the response's authoritative_sources field.

    Resolves source IDs to labels via the authoritative_sources module, then verifies
    that each expected source appears in the structured response field.
    """
    if not expected_ids:
        return (True, "")

    from agent.authoritative_sources import get_source_by_id

    actual_labels = {s.get("label", "") for s in authoritative_sources}
    missing = []
    for sid in expected_ids:
        source = get_source_by_id(sid)
        if source is None:
            missing.append(f"{sid} (unknown source ID)")
            continue
        if source["label"] not in actual_labels:
            missing.append(f"{sid} ({source['label']})")

    if missing:
        return (False, f"Missing authoritative sources: {missing}")

    return (True, "")


def check_must_contain(terms: list[str], response_text: str) -> tuple[bool, str]:
    """Check that all required terms appear in the response."""
    if not terms:
        return (True, "")

    text_lower = response_text.lower()
    missing = [t for t in terms if t.lower() not in text_lower]

    if missing:
        return (False, f"Missing required content: {missing}")

    return (True, "")


def check_contains_any(terms: list[str], response_text: str) -> tuple[bool, str]:
    """Check that at least one of the terms appears in the response."""
    if not terms:
        return (True, "")

    text_lower = response_text.lower()
    for t in terms:
        if t.lower() in text_lower:
            return (True, "")

    return (False, f"Missing required content (any of): {terms}")


def check_must_not_contain(
    forbidden: list[str],
    response_text: str,
    give_up_phrases: list[str] | None = None,
) -> tuple[bool, str]:
    """Check that no forbidden terms or give-up phrases appear in the response."""
    if not response_text.strip():
        return (False, "Response is empty")

    text_lower = response_text.lower()
    errors = []

    for term in forbidden:
        if term.lower() in text_lower:
            errors.append(f"Forbidden term found: '{term}'")

    for phrase in (give_up_phrases if give_up_phrases is not None else DEFAULT_GIVE_UP_PHRASES):
        if phrase.lower() in text_lower:
            errors.append(f"Give-up phrase found: '{phrase}'")

    if errors:
        return (False, "; ".join(errors))

    return (True, "")


def check_ground_truth(terms: list[str], response_text: str) -> tuple[bool, str]:
    """Check that known ground-truth values from mock data appear in the response."""
    if not terms:
        return (True, "")

    text_lower = response_text.lower()
    missing = [t for t in terms if str(t).lower() not in text_lower]

    if missing:
        return (False, f"Missing ground truth values: {missing}")

    return (True, "")


def check_structural(
    react_step: int | None,
    max_react_steps: int | None,
    latency_seconds: float | None,
    max_latency_seconds: float | None,
) -> tuple[bool, str]:
    """Check react step count and latency against per-case budgets."""
    errors = []

    if max_react_steps is not None and react_step is not None:
        if react_step > max_react_steps:
            errors.append(
                f"ReAct steps {react_step} exceeds max {max_react_steps}"
            )

    if max_latency_seconds is not None and latency_seconds is not None:
        if latency_seconds > max_latency_seconds:
            errors.append(
                f"Latency {latency_seconds:.1f}s exceeds max {max_latency_seconds}s"
            )

    if errors:
        return (False, "; ".join(errors))

    return (True, "")


def run_golden_checks(case: dict, result: dict) -> dict:
    """Run all seven golden checks and return structured result."""
    response = result.get("response") or {}
    response_text = response.get("summary") or ""
    tools_called = result.get("tools_called") or []

    # 1. Tool selection
    expected_any = case.get("expected_tools_any") or []
    expected_plus_any_of = case.get("expected_tools_plus_any_of") or []
    if expected_plus_any_of:
        tool_ok, tool_err = check_tools_plus_any_of(
            case.get("expected_tools", []),
            expected_plus_any_of,
            tools_called,
        )
    elif expected_any:
        tool_ok, tool_err = check_tools_any(expected_any, tools_called)
    else:
        tool_ok, tool_err = check_tools(
            case.get("expected_tools", []),
            tools_called,
            exact=case.get("exact_tools", False),
        )

    # 2. Tool execution — no tool returned {"error": ...} for this case
    tools_called = result.get("tools_called") or []
    tool_errors = result.get("tool_errors") or []
    if tools_called:
        tool_exec_ok = len(tool_errors) == 0
        tool_exec_err = "; ".join(tool_errors) if tool_errors else ""
    else:
        tool_exec_ok = True  # N/A when no tools called
        tool_exec_err = ""

    # 3. Source citation (text references + structured authoritative sources)
    source_ok, source_err = check_sources(
        case.get("expected_sources", []),
        response_text,
    )

    # 3b. Authoritative sources (structured field in response)
    expected_auth = case.get("expected_authoritative_sources", [])
    if expected_auth:
        auth_sources = response.get("authoritative_sources", [])
        auth_ok, auth_err = check_authoritative_sources(expected_auth, auth_sources)
        if not auth_ok:
            source_ok = False
            source_err = (source_err + "; " + auth_err) if source_err else auth_err

    # 4. Content validation
    must_contain = list(case.get("expected_output_contains") or []) + list(case.get("should_contain") or [])
    content_ok, content_err = check_must_contain(must_contain, response_text)

    # 3b. Optional "any of" content (e.g. position OR portfolio OR holdings)
    contains_any = case.get("expected_output_contains_any") or []
    if content_ok and contains_any:
        any_ok, any_err = check_contains_any(contains_any, response_text)
        if not any_ok:
            content_ok, content_err = False, any_err

    # 5. Negative validation
    negative_ok, negative_err = check_must_not_contain(
        case.get("should_not_contain", []),
        response_text,
    )

    # 6. Ground truth validation
    ground_truth_ok, ground_truth_err = check_ground_truth(
        case.get("ground_truth_contains", []),
        response_text,
    )

    # 7. Structural validation (react steps + latency)
    react_step = result.get("react_step")
    latency_seconds = result.get("latency_seconds")
    structural_ok, structural_err = check_structural(
        react_step=react_step,
        max_react_steps=case.get("max_react_steps"),
        latency_seconds=latency_seconds,
        max_latency_seconds=case.get("max_latency_seconds"),
    )

    all_checks = [tool_ok, tool_exec_ok, source_ok, content_ok, negative_ok, ground_truth_ok, structural_ok]
    all_passed = all(c for c in all_checks if c is not None)

    return {
        "passed": all_passed,
        "tool_selection": {"passed": tool_ok, "error": tool_err},
        "tool_execution": {"passed": tool_exec_ok, "error": tool_exec_err},
        "source_citation": {"passed": source_ok, "error": source_err},
        "content": {"passed": content_ok, "error": content_err},
        "negative": {"passed": negative_ok, "error": negative_err},
        "ground_truth": {"passed": ground_truth_ok, "error": ground_truth_err},
        "structural": {"passed": structural_ok, "error": structural_err},
    }
