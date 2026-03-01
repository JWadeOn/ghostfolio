"""Persistence layer: Postgres checkpointer + Redis message-history cache."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import AIMessage, HumanMessage
from psycopg import AsyncConnection

from agent.config import get_settings

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60 * 60 * 24  # 24 hours
CACHE_KEY_PREFIX = "conv:"

# Module-level singletons, initialised via init_* helpers at startup
_checkpointer: AsyncPostgresSaver | None = None
_redis: aioredis.Redis | None = None
_pg_conn: AsyncConnection | None = None


async def init_checkpointer() -> AsyncPostgresSaver:
    """Create and set up the Postgres checkpointer (creates tables on first run)."""
    global _checkpointer, _pg_conn
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for session persistence")

    _pg_conn = await AsyncConnection.connect(
        settings.database_url,
        autocommit=True,
        prepare_threshold=0,
    )
    _checkpointer = AsyncPostgresSaver(conn=_pg_conn)
    await _checkpointer.setup()
    logger.info("Postgres checkpointer initialised")
    return _checkpointer


def get_checkpointer() -> AsyncPostgresSaver | None:
    return _checkpointer


async def init_redis() -> aioredis.Redis | None:
    """Create an async Redis client.  Returns None if REDIS_URL is empty."""
    global _redis
    settings = get_settings()
    if not settings.redis_url:
        logger.warning("REDIS_URL not set – message cache disabled")
        return None
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await _redis.ping()
        logger.info("Redis message cache connected")
    except Exception as exc:
        logger.warning("Redis unavailable (%s) – message cache disabled", exc)
        _redis = None
    return _redis


def get_redis() -> aioredis.Redis | None:
    return _redis


def _serialise_messages(messages: list) -> list[dict[str, str]]:
    """Convert LangChain messages to a JSON-friendly list of dicts."""
    out: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            out.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, list):
                content = "\n".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            if content:
                out.append({"role": "assistant", "content": content})
    return out


async def cache_messages(thread_id: str, messages: list) -> None:
    """Write serialised message history to Redis with a 24 h TTL."""
    if _redis is None:
        return
    try:
        payload = json.dumps(_serialise_messages(messages))
        await _redis.set(f"{CACHE_KEY_PREFIX}{thread_id}", payload, ex=CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.warning("Failed to cache messages for %s: %s", thread_id, exc)


async def get_cached_messages(thread_id: str) -> list[dict[str, str]] | None:
    """Return cached message history or None on miss / error."""
    if _redis is None:
        return None
    try:
        raw = await _redis.get(f"{CACHE_KEY_PREFIX}{thread_id}")
        if raw is not None:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis cache read failed for %s: %s", thread_id, exc)
    return None


async def get_conversation_history(
    thread_id: str,
    graph: CompiledStateGraph,
) -> list[dict[str, str]]:
    """Return message history for *thread_id*.

    Strategy: Redis cache first, Postgres checkpoint fallback.
    """
    cached = await get_cached_messages(thread_id)
    if cached is not None:
        return cached

    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)
        if state and state.values and "messages" in state.values:
            messages = _serialise_messages(state.values["messages"])
            await cache_messages(thread_id, state.values["messages"])
            return messages
    except Exception as exc:
        logger.warning("Checkpoint read failed for %s: %s", thread_id, exc)

    return []


async def setup_feedback_table() -> None:
    """Create the feedback table if it does not exist."""
    if _pg_conn is None:
        return
    try:
        await _pg_conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id SERIAL PRIMARY KEY,
                thread_id TEXT NOT NULL,
                rating TEXT NOT NULL,
                correction TEXT,
                comment TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        logger.info("Feedback table ready")
    except Exception as exc:
        logger.error("Failed to create feedback table: %s", exc)


async def insert_feedback(
    thread_id: str,
    rating: str,
    correction: str | None = None,
    comment: str | None = None,
) -> int | None:
    """Insert a feedback row and return its id."""
    if _pg_conn is None:
        logger.warning("No Postgres connection — feedback not stored")
        return None
    try:
        cur = await _pg_conn.execute(
            """
            INSERT INTO feedback (thread_id, rating, correction, comment)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (thread_id, rating, correction, comment),
        )
        row = await cur.fetchone()
        return row[0] if row else None
    except Exception as exc:
        logger.error("Failed to insert feedback: %s", exc)
        return None


async def get_feedback_summary() -> dict:
    """Return aggregate feedback counts from Postgres."""
    if _pg_conn is None:
        return {"total": 0, "thumbs_up": 0, "thumbs_down": 0, "with_corrections": 0}
    try:
        cur = await _pg_conn.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE rating = 'thumbs_up') AS thumbs_up,
                COUNT(*) FILTER (WHERE rating = 'thumbs_down') AS thumbs_down,
                COUNT(*) FILTER (WHERE correction IS NOT NULL AND correction != '') AS with_corrections
            FROM feedback
        """)
        row = await cur.fetchone()
        if row:
            return {
                "total": row[0],
                "thumbs_up": row[1],
                "thumbs_down": row[2],
                "with_corrections": row[3],
            }
    except Exception as exc:
        logger.error("Failed to query feedback summary: %s", exc)
    return {"total": 0, "thumbs_up": 0, "thumbs_down": 0, "with_corrections": 0}


async def shutdown() -> None:
    """Gracefully close Postgres and Redis connections."""
    global _checkpointer, _redis, _pg_conn
    if _pg_conn is not None:
        await _pg_conn.close()
        _pg_conn = None
        _checkpointer = None
        logger.info("Postgres connection closed")
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")
