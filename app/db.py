import json
import os

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()


def _connect():
    return psycopg.connect(os.environ["DATABASE_URL"])


def setup_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id          SERIAL PRIMARY KEY,
                session_number INTEGER NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT,
                raw_message JSONB NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.commit()


def setup_vector_db():
    with _connect() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_insights (
                id              SERIAL PRIMARY KEY,
                session_number  INTEGER NOT NULL,
                insight         TEXT NOT NULL,
                embedding       VECTOR(1536),
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.commit()


def load_messages() -> list[dict]:
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT raw_message FROM messages ORDER BY id ASC"
        ).fetchall()
    return [row["raw_message"] for row in rows]


def load_session_messages(session_number: int) -> list[dict]:
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT raw_message FROM messages WHERE session_number = %s ORDER BY id ASC",
            (session_number,),
        ).fetchall()
    return [row["raw_message"] for row in rows]


def save_insights(session_number: int, insights: list[str], embeddings: list[list[float]]) -> None:
    with _connect() as conn:
        for insight, embedding in zip(insights, embeddings):
            conn.execute(
                "INSERT INTO session_insights (session_number, insight, embedding) VALUES (%s, %s, %s::vector)",
                (session_number, insight, json.dumps(embedding)),
            )
        conn.commit()


def load_insights(session_number: int) -> list[str]:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
            rows = conn.execute(
                "SELECT insight FROM session_insights WHERE session_number = %s ORDER BY id ASC",
                (session_number,),
            ).fetchall()
        return [row["insight"] for row in rows]
    except Exception:
        return []


def save_message(session_number: int, message: dict):
    role = message.get("role", "")
    content = message.get("content") if isinstance(message.get("content"), str) else None
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (session_number, role, content, raw_message) VALUES (%s, %s, %s, %s)",
            (session_number, role, content, json.dumps(message)),
        )
        conn.commit()
