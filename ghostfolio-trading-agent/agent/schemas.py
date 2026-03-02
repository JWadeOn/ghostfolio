"""Pydantic v2 models for validated agent output."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    claim: str
    source: str | None = None
    verified: bool = False


class AuthoritativeSource(BaseModel):
    label: str
    url: str


class Observability(BaseModel):
    token_usage: dict = Field(default_factory=dict)
    node_latencies: dict = Field(default_factory=dict)
    error_log: list[dict] = Field(default_factory=list)
    trace_log: list[dict] = Field(default_factory=list)
    total_latency_seconds: float | None = None


class AgentResponse(BaseModel):
    summary: str = Field(..., min_length=1)
    confidence: int = Field(..., ge=0, le=100)
    intent: str
    data: dict = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    authoritative_sources: list[AuthoritativeSource] = Field(default_factory=list)
    disclaimer: str = ""
    observability: Observability = Field(default_factory=Observability)
    escalated: bool = False
    escalation_reason: str | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: int) -> int:
        if isinstance(v, (int, float)):
            return max(0, min(100, int(v)))
        return v
