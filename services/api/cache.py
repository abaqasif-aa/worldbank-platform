import os
import json
import logging

import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

COUNTRY_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days, in seconds


def get_redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


def get_pg_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", 5432),
        dbname=os.getenv("POSTGRES_DB", "worldbank"),
        user=os.getenv("POSTGRES_USER", "de"),
        password=os.getenv("POSTGRES_PASSWORD", "de"),
    )


def seed_country_cache() -> int:
    """  Note on scale: this loops with individual r.set() calls and a single
    fetchall(). For ~148 countries this is a few ms total and the simplest
    correct implementation. If this ever covered a much larger entity
    (e.g. per-city or per-region records), the right change would be
    fetchmany() batches from Postgres + r.pipeline() batches to Redis,
    chunked at ~1000 rows, to avoid per-row round-trip overhead in both
    directions. Not needed for a fixed ~200-country dataset.
    """
    conn = get_pg_conn()
    r = get_redis()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT country_code, country_name, region,
                       income_group, capital
                FROM marts.country_metadata
            """)
            rows = cur.fetchall()

        for row in rows:
            key = f"country:{row['country_code']}"
            r.set(key, json.dumps(dict(row)), ex=COUNTRY_CACHE_TTL)

        log.info(f"Seeded {len(rows)} countries into Redis cache")
        return len(rows)

    finally:
        conn.close()


def get_country_metadata(country_code: str) -> dict | None:
    """Cache-aside lookup for a single country's metadata.

    1. Check Redis for country:{code}
    2. If found, return it (cache hit)
    3. If not found, query Postgres, store in Redis, return it (cache miss)
    """
    r = get_redis()
    key = f"country:{country_code.upper()}"

    cached = r.get(key)
    if cached is not None:
        return json.loads(cached)

    conn = get_pg_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT country_code, country_name, region,
                       income_group, capital
                FROM marts.country_metadata
                WHERE country_code = %s
            """, (country_code.upper(),))
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    data = dict(row)
    r.set(key, json.dumps(data), ex=COUNTRY_CACHE_TTL)
    return data


# ── Conversation history (for RAG follow-up questions) ─────────────────────────
CONVERSATION_TTL = 60 * 30  # 30 minutes of inactivity


def get_conversation_history(session_id: str) -> list[dict]:
    """Retrieve conversation history for a session. Returns list of
    {"question": ..., "answer": ...} dicts, oldest first."""
    r = get_redis()
    key = f"conversation:{session_id}"
    raw = r.get(key)
    if raw is None:
        return []
    return json.loads(raw)


def append_to_conversation(session_id: str, question: str, answer: str, max_turns: int = 5):
    """Append a question/answer pair to conversation history,
    keeping only the most recent max_turns exchanges."""
    r = get_redis()
    key = f"conversation:{session_id}"

    history = get_conversation_history(session_id)
    history.append({"question": question, "answer": answer})
    history = history[-max_turns:]

    r.set(key, json.dumps(history), ex=CONVERSATION_TTL)


def clear_conversation(session_id: str):
    """Clear conversation history for a session (e.g. user starts a new chat)."""
    r = get_redis()
    r.delete(f"conversation:{session_id}")