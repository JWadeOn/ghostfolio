"""FastAPI application entry point."""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from agent.config import get_settings
from agent.input_validation import MAX_MESSAGE_LENGTH, validate_chat_message
from agent.ghostfolio_client import GhostfolioClient
from agent.graph import build_agent_graph
from agent.schemas import AgentResponse, Observability
from agent.persistence import (
    cache_messages,
    get_conversation_history,
    get_escalation_summary,
    get_feedback_summary,
    get_pending_escalations,
    init_checkpointer,
    init_redis,
    insert_escalation,
    insert_feedback,
    resolve_escalation,
    setup_escalation_table,
    setup_feedback_table,
    shutdown as persistence_shutdown,
)
from agent.tools.regime import detect_regime
from agent.tools.scanner import scan_strategies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure LangSmith sees tracing config (LangChain reads os.environ, not Pydantic)
_settings = get_settings()
if _settings.langchain_api_key and _settings.langchain_tracing_v2:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = _settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = _settings.langchain_project
    logger.info("LangSmith tracing enabled (project=%s)", _settings.langchain_project)
else:
    os.environ.pop("LANGCHAIN_TRACING_V2", None)
    logger.info("LangSmith tracing disabled (no API key or tracing_v2=false)")

# Log loaded tools early so you can verify create_activity is available
try:
    from agent.tools.langchain_tools import get_tools

    _tool_names = [t.name for t in get_tools() if getattr(t, "name", None)]
    logger.info("Agent tools loaded: %s", ", ".join(_tool_names))
except Exception as e:
    logger.warning("Could not list tools at startup: %s", e)

# ---------------------------------------------------------------------------
# Graph compiled at startup with the Postgres checkpointer
# ---------------------------------------------------------------------------
_agent_graph = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup: initialise persistence and compile graph.  Shutdown: close connections."""
    global _agent_graph

    settings = get_settings()

    checkpointer = None
    if settings.database_url:
        try:
            checkpointer = await init_checkpointer()
        except Exception as exc:
            logger.error("Failed to initialise Postgres checkpointer: %s", exc)

    await init_redis()
    await setup_feedback_table()
    await setup_escalation_table()

    _agent_graph = build_agent_graph(checkpointer=checkpointer)
    logger.info("Agent graph compiled (checkpointer=%s)", type(checkpointer).__name__ if checkpointer else "None")

    yield

    await persistence_shutdown()


app = FastAPI(
    title="Ghostfolio Trading Intelligence Agent",
    description="AI-powered trading analysis built on Ghostfolio",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3333",
        "http://localhost:4200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH)
    thread_id: str | None = None
    access_token: str | None = None


class ChatResponse(BaseModel):
    response: dict[str, Any]
    thread_id: str


class ConversationResponse(BaseModel):
    thread_id: str
    messages: list[dict[str, str]]


def _make_json_serializable(obj: Any) -> Any:
    """Recursively convert numpy/pandas scalars to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(v) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj) if np.isfinite(obj) else None
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


_TRADE_INTENTS = frozenset({
    "risk_check", "create_activity", "opportunity_scan", "portfolio_health",
})
_GUARANTEE_PATTERNS = ("guaranteed", "risk-free", "no risk", "cannot lose", "will definitely")


def _check_escalation(response_data: dict, settings: Any) -> str | None:
    """Return an escalation reason string if the response should be flagged, else None."""
    if not settings.escalation_enabled:
        return None

    reasons: list[str] = []

    confidence = response_data.get("confidence", 50)
    if confidence < settings.escalation_confidence_threshold:
        reasons.append(f"low_confidence ({confidence})")

    intent = response_data.get("intent", "")
    warnings = response_data.get("warnings", [])
    if intent in _TRADE_INTENTS and warnings:
        for w in warnings:
            if "violation" in w.lower() or "guardrail" in w.lower():
                reasons.append("guardrail_violation")
                break

    summary = response_data.get("summary", "").lower()
    warning_text = " ".join(w.lower() for w in warnings)
    combined = summary + " " + warning_text
    for pattern in _GUARANTEE_PATTERNS:
        if pattern in combined:
            reasons.append("guarantee_language")
            break

    return "; ".join(reasons) if reasons else None


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint — processes natural language queries through the agent."""
    try:
        message = validate_chat_message(request.message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    thread_id = request.thread_id or str(uuid.uuid4())
    access_token = (request.access_token or "").strip() or None

    # Per-request fields only; regime/portfolio are restored by the checkpointer
    input_state = {
        "messages": [HumanMessage(content=message)],
        "intent": "",
        "extracted_params": {},
        "ghostfolio_access_token": access_token,
        "tool_results": {},
        "tools_called": [],
        "react_step": 0,
        "synthesis": None,
        "verification_result": None,
        "verification_attempts": 0,
        "response": None,
        "token_usage": {},
        "node_latencies": {},
        "error_log": [],
        "trace_log": [],
    }

    config = {"configurable": {"thread_id": thread_id}}

    try:
        t0 = time.perf_counter()
        result = await _agent_graph.ainvoke(input_state, config=config)
        total_latency = round(time.perf_counter() - t0, 3)

        # Cache message history in Redis for the GET endpoint
        await cache_messages(thread_id, result.get("messages", []))

        response_data = result.get(
            "response", {"summary": "No response generated", "confidence": 0}
        )
        obs = response_data.get("observability", {})
        obs["total_latency_seconds"] = total_latency
        response_data["observability"] = obs

        response_data = _make_json_serializable(response_data)

        # Escalation check
        settings = get_settings()
        escalation_reason = _check_escalation(response_data, settings)
        if escalation_reason:
            response_data["escalated"] = True
            response_data["escalation_reason"] = escalation_reason
            await insert_escalation(
                thread_id=thread_id,
                confidence=response_data.get("confidence", 0),
                intent=response_data.get("intent", "unknown"),
                reason=escalation_reason,
                response_snapshot=response_data,
            )
            logger.info("Escalation triggered: thread=%s reason=%s", thread_id, escalation_reason)

        logger.info(
            "Request completed: thread=%s latency=%.2fs tokens=%s",
            thread_id,
            total_latency,
            obs.get("token_usage", {}).get("total", {}),
        )

        return ChatResponse(response=response_data, thread_id=thread_id)
    except Exception as e:
        logger.error("Agent error: %s", e, exc_info=True)
        error_response = AgentResponse(
            summary=f"An error occurred: {str(e)}",
            confidence=0,
            intent="error",
            warnings=[str(e)],
            disclaimer="This is market analysis, not financial advice.",
            observability=Observability(
                error_log=[
                    {"node": "app", "error": str(e), "category": "unknown_error"}
                ],
            ),
        )
        return ChatResponse(
            response=error_response.model_dump(),
            thread_id=thread_id,
        )


@app.get("/api/conversation/{thread_id}", response_model=ConversationResponse)
async def conversation(thread_id: str):
    """Return the message history for a given thread from Redis cache or Postgres checkpoint."""
    messages = await get_conversation_history(thread_id, _agent_graph)
    return ConversationResponse(thread_id=thread_id, messages=messages)


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    settings = get_settings()

    ghostfolio_status = "unreachable"
    try:
        client = GhostfolioClient()
        if client.health_check():
            ghostfolio_status = "connected"
        client.close()
    except Exception:
        pass

    langsmith_status = "configured" if settings.langchain_api_key else "not_configured"

    return {
        "status": "ok",
        "ghostfolio": ghostfolio_status,
        "langsmith": langsmith_status,
        "anthropic": "configured" if settings.anthropic_api_key else "not_configured",
    }


@app.get("/api/regime")
async def get_regime():
    """Shortcut: get current market regime without full agent loop."""
    try:
        result = detect_regime()
        return _make_json_serializable(result)
    except Exception as e:
        logger.error("Regime detection failed: %s", e)
        return {"error": str(e)}


# --- Feedback ---


class FeedbackRequest(BaseModel):
    thread_id: str
    rating: str  # "thumbs_up" | "thumbs_down"
    correction: str | None = None
    comment: str | None = None


@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest):
    """Capture user feedback (thumbs up/down, optional correction) for a thread."""
    feedback_id = await insert_feedback(
        thread_id=req.thread_id,
        rating=req.rating,
        correction=req.correction,
        comment=req.comment,
    )
    if feedback_id is None:
        raise HTTPException(status_code=503, detail="Feedback storage unavailable")
    logger.info("Feedback recorded: thread=%s rating=%s id=%s", req.thread_id, req.rating, feedback_id)
    return {"status": "ok", "feedback_id": str(feedback_id)}


@app.get("/api/feedback/summary")
async def feedback_summary():
    """Return aggregate feedback counts."""
    return await get_feedback_summary()


# --- Escalation ---


@app.get("/api/escalations")
async def list_escalations(limit: int = 50):
    """Return pending escalations for review."""
    return await get_pending_escalations(limit=limit)


class ResolveRequest(BaseModel):
    reviewer_notes: str


@app.post("/api/escalations/{escalation_id}/resolve")
async def resolve_escalation_endpoint(escalation_id: int, req: ResolveRequest):
    """Resolve a pending escalation with reviewer notes."""
    resolved = await resolve_escalation(escalation_id, req.reviewer_notes)
    if not resolved:
        raise HTTPException(status_code=404, detail="Escalation not found or already resolved")
    return {"status": "ok", "escalation_id": escalation_id}


@app.get("/api/escalations/summary")
async def escalation_summary():
    """Return aggregate escalation counts."""
    return await get_escalation_summary()


class ScanRequest(BaseModel):
    strategy: str = "all"
    universe: str = "default"
    symbols: list[str] | None = None


@app.get("/api/scan")
async def scan(strategy: str = "all", symbols: str | None = None):
    """Shortcut: run strategy scan without full agent loop."""
    try:
        strategy_names = None if strategy == "all" else [strategy]
        symbol_list = symbols.split(",") if symbols else None

        result = scan_strategies(
            symbols=symbol_list,
            strategy_names=strategy_names,
        )
        return result
    except Exception as e:
        logger.error("Scan failed: %s", e)
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.agent_port)
