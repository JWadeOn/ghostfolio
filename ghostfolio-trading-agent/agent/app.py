"""FastAPI application entry point."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from agent.config import get_settings
from agent.graph import agent_graph
from agent.ghostfolio_client import GhostfolioClient
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

app = FastAPI(
    title="Ghostfolio Trading Intelligence Agent",
    description="AI-powered trading analysis built on Ghostfolio",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3333", "http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory thread state (for conversation continuity)
_thread_states: dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    response: dict[str, Any]
    thread_id: str


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


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint — processes natural language queries through the agent."""
    thread_id = request.thread_id or str(uuid.uuid4())

    # Get or create thread state
    prev_state = _thread_states.get(thread_id, {})

    # Build initial state
    initial_state = {
        "messages": prev_state.get("messages", []) + [HumanMessage(content=request.message)],
        "intent": "",
        "extracted_params": {},
        "regime": prev_state.get("regime"),
        "regime_timestamp": prev_state.get("regime_timestamp"),
        "portfolio": prev_state.get("portfolio"),
        "portfolio_timestamp": prev_state.get("portfolio_timestamp"),
        "tool_results": {},
        "tools_called": [],
        "tools_needed": [],
        "synthesis": None,
        "verification_result": None,
        "verification_attempts": 0,
        "response": None,
    }

    # Run the graph
    try:
        result = agent_graph.invoke(initial_state)

        # Save state for thread continuity
        _thread_states[thread_id] = {
            "messages": result.get("messages", []),
            "regime": result.get("regime"),
            "regime_timestamp": result.get("regime_timestamp"),
            "portfolio": result.get("portfolio"),
            "portfolio_timestamp": result.get("portfolio_timestamp"),
        }

        response_data = result.get("response", {"summary": "No response generated", "confidence": 0})
        response_data = _make_json_serializable(response_data)
        return ChatResponse(
            response=response_data,
            thread_id=thread_id,
        )
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        return ChatResponse(
            response={
                "summary": f"An error occurred: {str(e)}",
                "confidence": 0,
                "intent": "error",
                "data": {},
                "citations": [],
                "warnings": [str(e)],
                "tools_used": [],
                "disclaimer": "This is market analysis, not financial advice.",
            },
            thread_id=thread_id,
        )


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    settings = get_settings()

    # Check Ghostfolio
    ghostfolio_status = "unreachable"
    try:
        client = GhostfolioClient()
        if client.health_check():
            ghostfolio_status = "connected"
        client.close()
    except Exception:
        pass

    # Check LangSmith config
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
        logger.error(f"Regime detection failed: {e}")
        return {"error": str(e)}


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
        logger.error(f"Scan failed: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.agent_port)
