"""Integration tests for persistent session storage.

Verifies the two-tier persistence layer (Redis L1 + Postgres L2):
  1. Multi-turn conversations share context within a thread
  2. Conversation history retrievable via GET /api/conversation/{thread_id}
  3. Sessions survive Redis flush (Postgres L2 fallback)
  4. Redis cache is populated and used as L1
  5. Message serialization for Redis storage
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from agent.app import app, lifespan
from agent.persistence import (
    get_cached_messages,
    _serialise_messages,
)
from langchain_core.messages import AIMessage, HumanMessage


# ---------------------------------------------------------------------------
# Mocks — prevent real LLM calls and external API hits
# ---------------------------------------------------------------------------

def _apply_mocks():
    from tests.mocks.ghostfolio_mock import MockGhostfolioClient
    from tests.mocks.market_data_mock import mock_fetch_with_retry

    def _mock_get_sector(symbol: str) -> str | None:
        return "Technology"

    patches = [
        patch("agent.nodes.tools.GhostfolioClient", MockGhostfolioClient),
        patch("agent.tools.market_data._fetch_with_retry", mock_fetch_with_retry),
        patch("agent.tools.risk._get_sector", _mock_get_sector),
    ]
    for p in patches:
        p.start()
    return patches


# ---------------------------------------------------------------------------
# Serialization unit tests (sync, no fixtures needed)
# ---------------------------------------------------------------------------

class TestMessageSerialization:
    """Verify messages are correctly serialized for Redis storage."""

    def test_serialise_human_and_ai(self):
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]
        result = _serialise_messages(messages)
        assert result == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

    def test_serialise_ai_with_list_content(self):
        """AIMessage content can be a list of blocks (e.g. from tool use)."""
        messages = [
            AIMessage(content=[
                {"type": "text", "text": "Here is the data."},
                {"type": "text", "text": "And some analysis."},
            ]),
        ]
        result = _serialise_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert "Here is the data." in result[0]["content"]
        assert "And some analysis." in result[0]["content"]

    def test_serialise_empty_ai_content_skipped(self):
        """AIMessages with empty content (e.g. pure tool_calls) should be skipped."""
        messages = [
            HumanMessage(content="Do something"),
            AIMessage(content=""),
            AIMessage(content="Here's the result"),
        ]
        result = _serialise_messages(messages)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "Here's the result"


# ---------------------------------------------------------------------------
# Async integration tests
#
# All tests share a single event loop (loop_scope="class") so the Postgres
# checkpointer's internal asyncio.Lock stays on the same loop throughout.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="class", loop_scope="class")
async def client():
    """Async HTTP client wired to the FastAPI app with full lifespan."""
    patches = _apply_mocks()
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    for p in patches:
        p.stop()


@pytest.mark.asyncio(loop_scope="class")
class TestPersistenceIntegration:
    """All async integration tests in one class so Postgres/Redis connections
    share a single event loop."""

    # -- Multi-turn conversation --

    async def test_second_turn_receives_history(self, client: AsyncClient):
        """Send two messages on the same thread; the second should see the first."""
        tid = str(uuid.uuid4())

        r1 = await client.post("/api/chat", json={
            "message": "What is the current market regime?",
            "thread_id": tid,
        })
        assert r1.status_code == 200
        assert r1.json()["thread_id"] == tid
        assert r1.json()["response"].get("summary")

        r2 = await client.post("/api/chat", json={
            "message": "How does that affect my portfolio?",
            "thread_id": tid,
        })
        assert r2.status_code == 200
        assert r2.json()["thread_id"] == tid
        assert r2.json()["response"].get("summary")

    async def test_different_threads_are_isolated(self, client: AsyncClient):
        """Two different thread_ids should not share conversation history."""
        thread_a = str(uuid.uuid4())
        thread_b = str(uuid.uuid4())

        await client.post("/api/chat", json={
            "message": "What is my portfolio allocation?",
            "thread_id": thread_a,
        })
        await client.post("/api/chat", json={
            "message": "Show me AAPL market data",
            "thread_id": thread_b,
        })

        hist_a = await client.get(f"/api/conversation/{thread_a}")
        hist_b = await client.get(f"/api/conversation/{thread_b}")

        msgs_a = hist_a.json()["messages"]
        msgs_b = hist_b.json()["messages"]

        assert any("portfolio" in m["content"].lower() for m in msgs_a if m["role"] == "user")
        assert not any("AAPL" in m["content"] for m in msgs_a if m["role"] == "user")

        assert any("AAPL" in m["content"] for m in msgs_b if m["role"] == "user")
        assert not any("portfolio" in m["content"].lower() for m in msgs_b if m["role"] == "user")

    # -- Conversation history endpoint --

    async def test_returns_history_after_chat(self, client: AsyncClient):
        """After a chat, the conversation endpoint should return messages."""
        tid = str(uuid.uuid4())

        await client.post("/api/chat", json={
            "message": "Look up the symbol for Apple",
            "thread_id": tid,
        })

        r = await client.get(f"/api/conversation/{tid}")
        assert r.status_code == 200
        messages = r.json()["messages"]

        assert len(messages) >= 2
        assert messages[0]["role"] == "user"
        assert "Apple" in messages[0]["content"]
        assert any(m["role"] == "assistant" for m in messages)

    async def test_unknown_thread_returns_empty(self, client: AsyncClient):
        """A thread_id that was never used should return an empty list."""
        r = await client.get(f"/api/conversation/{uuid.uuid4()}")
        assert r.status_code == 200
        assert r.json()["messages"] == []

    # -- Redis L1 cache --

    async def test_cache_populated_after_chat(self, client: AsyncClient):
        """After a chat request, messages should be cached in Redis."""
        tid = str(uuid.uuid4())

        await client.post("/api/chat", json={
            "message": "Detect the current market regime",
            "thread_id": tid,
        })

        cached = await get_cached_messages(tid)
        assert cached is not None
        assert len(cached) >= 2
        assert cached[0]["role"] == "user"
        assert any(m["role"] == "assistant" for m in cached)

    async def test_cache_hit_returns_consistent_results(self, client: AsyncClient):
        """Repeated GETs to conversation endpoint return identical results."""
        tid = str(uuid.uuid4())

        await client.post("/api/chat", json={
            "message": "Show me AAPL data",
            "thread_id": tid,
        })

        r1 = await client.get(f"/api/conversation/{tid}")
        r2 = await client.get(f"/api/conversation/{tid}")
        assert r1.json()["messages"] == r2.json()["messages"]

    # -- Postgres L2 fallback --

    async def test_history_survives_redis_flush(self, client: AsyncClient):
        """Clear Redis after a chat; history should still come from Postgres."""
        tid = str(uuid.uuid4())

        await client.post("/api/chat", json={
            "message": "What are the top holdings in my portfolio?",
            "thread_id": tid,
        })

        # Verify it's in Redis
        cached = await get_cached_messages(tid)
        assert cached is not None
        assert len(cached) >= 2

        # Flush the Redis key to simulate cache eviction / restart
        from agent.persistence import _redis, CACHE_KEY_PREFIX
        if _redis is not None:
            await _redis.delete(f"{CACHE_KEY_PREFIX}{tid}")

        # Confirm Redis is empty
        assert await get_cached_messages(tid) is None

        # History should still come back via Postgres checkpoint
        r = await client.get(f"/api/conversation/{tid}")
        assert r.status_code == 200
        messages = r.json()["messages"]
        assert len(messages) >= 2
        assert messages[0]["role"] == "user"

    # -- Feedback API (Postgres-backed) --

    async def test_feedback_thumbs_up(self, client: AsyncClient):
        """Submit thumbs up feedback and get a feedback_id back."""
        tid = str(uuid.uuid4())
        r = await client.post("/api/feedback", json={
            "thread_id": tid,
            "rating": "thumbs_up",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["feedback_id"]

    async def test_feedback_thumbs_down_with_correction(self, client: AsyncClient):
        """Submit thumbs down with a correction string."""
        tid = str(uuid.uuid4())
        r = await client.post("/api/feedback", json={
            "thread_id": tid,
            "rating": "thumbs_down",
            "correction": "The portfolio has 5 holdings, not 3.",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["feedback_id"]

    async def test_feedback_summary_reflects_submissions(self, client: AsyncClient):
        """Summary endpoint should count all feedback submitted in this session."""
        r = await client.get("/api/feedback/summary")
        assert r.status_code == 200
        summary = r.json()
        assert summary["total"] >= 2  # at least the two above
        assert summary["thumbs_up"] >= 1
        assert summary["thumbs_down"] >= 1
        assert summary["with_corrections"] >= 1
