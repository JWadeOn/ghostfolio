"""Observability helpers — token tracking, latency, structured errors, and trace logging."""

from __future__ import annotations

import time
import logging
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (Claude Sonnet 4, as of 2025)
COST_PER_1M_INPUT = 3.00
COST_PER_1M_OUTPUT = 15.00


def extract_token_usage(response: Any) -> dict:
    """Extract token counts from a LangChain LLM response."""
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
    meta = getattr(response, "usage_metadata", None)
    if meta and isinstance(meta, dict):
        usage["input_tokens"] = meta.get("input_tokens", 0)
        usage["output_tokens"] = meta.get("output_tokens", 0)
    elif meta:
        usage["input_tokens"] = getattr(meta, "input_tokens", 0)
        usage["output_tokens"] = getattr(meta, "output_tokens", 0)

    response_meta = getattr(response, "response_metadata", None)
    if response_meta and isinstance(response_meta, dict):
        rm_usage = response_meta.get("usage", {})
        if rm_usage:
            usage["input_tokens"] = usage["input_tokens"] or rm_usage.get("input_tokens", 0)
            usage["output_tokens"] = usage["output_tokens"] or rm_usage.get("output_tokens", 0)

    return usage


def aggregate_token_usage(token_usage: dict) -> dict:
    """Compute totals and estimated cost across all tracked LLM calls."""
    total_in = 0
    total_out = 0
    for key, val in token_usage.items():
        if key == "total":
            continue
        if isinstance(val, dict):
            total_in += val.get("input_tokens", 0)
            total_out += val.get("output_tokens", 0)
    cost = (total_in / 1_000_000) * COST_PER_1M_INPUT + (total_out / 1_000_000) * COST_PER_1M_OUTPUT
    return {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "total_tokens": total_in + total_out,
        "estimated_cost_usd": round(cost, 6),
    }


@contextmanager
def track_latency() -> Generator[dict, None, None]:
    """Context manager that yields a dict; on exit populates elapsed_seconds."""
    result: dict[str, float] = {}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["elapsed_seconds"] = round(time.perf_counter() - start, 4)


class ErrorCategory:
    LLM = "llm_error"
    TOOL = "tool_error"
    VALIDATION = "validation_error"
    PARSE = "parse_error"
    NETWORK = "network_error"
    UNKNOWN = "unknown_error"


def make_error_entry(
    node: str,
    error: Exception,
    category: str = ErrorCategory.UNKNOWN,
    context: dict | None = None,
) -> dict:
    """Build a structured error log entry."""
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": node,
        "category": category,
        "error": str(error),
        "error_type": type(error).__name__,
        "stacktrace": traceback.format_exception(type(error), error, error.__traceback__)[-3:],
    }
    if context:
        entry["context"] = context
    return entry


def make_trace_entry(
    node: str,
    input_summary: str = "",
    output_summary: str = "",
    metadata: dict | None = None,
) -> dict:
    """Build a structured trace log entry."""
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": node,
    }
    if input_summary:
        entry["input"] = input_summary[:500]
    if output_summary:
        entry["output"] = output_summary[:500]
    if metadata:
        entry["metadata"] = metadata
    return entry
