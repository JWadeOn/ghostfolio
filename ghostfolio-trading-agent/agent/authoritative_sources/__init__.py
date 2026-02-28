"""Authoritative sources knowledge store for tax and compliance citations."""

from __future__ import annotations

import json
from pathlib import Path

_SOURCES_PATH = Path(__file__).parent / "sources.json"

# Module-level cache — loaded once on first import
_sources: list[dict] | None = None


def _load_sources() -> list[dict]:
    global _sources
    if _sources is None:
        with open(_SOURCES_PATH) as f:
            _sources = json.load(f)
    return _sources


TOOL_TO_SOURCES: dict[str, list[str]] = {
    "compliance_check": ["irc_1091", "irs_pub550", "irc_1222", "irc_1h", "irs_pub544"],
    "tax_estimate": ["irc_1", "irs_pub17", "irc_1222", "irc_1h"],
}


def get_sources_for_tools(tools_called: list[str]) -> list[dict]:
    """Return list of {"id", "label", "url"} for tools that have authoritative sources."""
    sources = _load_sources()
    source_map = {s["id"]: s for s in sources}
    seen: set[str] = set()
    result: list[dict] = []
    for tool in tools_called:
        for sid in TOOL_TO_SOURCES.get(tool, []):
            if sid not in seen and sid in source_map:
                seen.add(sid)
                s = source_map[sid]
                result.append({"id": s["id"], "label": s["label"], "url": s["url"]})
    return result


def get_excerpts_for_tools(tools_called: list[str]) -> str:
    """Return formatted excerpt block for prompt injection. Empty string if no match."""
    sources = _load_sources()
    source_map = {s["id"]: s for s in sources}
    seen: set[str] = set()
    parts: list[str] = []
    for tool in tools_called:
        for sid in TOOL_TO_SOURCES.get(tool, []):
            if sid not in seen and sid in source_map:
                seen.add(sid)
                s = source_map[sid]
                parts.append(f"- **{s['label']}**: {s['excerpt']}")
    if not parts:
        return ""
    return "## Authoritative Tax & Compliance References\n" + "\n".join(parts)


def get_source_by_id(source_id: str) -> dict | None:
    """Lookup a single source record by id."""
    sources = _load_sources()
    for s in sources:
        if s["id"] == source_id:
            return s
    return None
