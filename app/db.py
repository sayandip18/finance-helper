import json
import os
import sqlite3

from app.logger import log_event

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_DB_PATH = os.path.join(_DATA_DIR, "sessions.db")
_MEMORY_PATH = os.path.join(_DATA_DIR, "memory.json")

_EMPTY_MEMORY = {
    "goal": "",
    "active_commitments": [],
    "reminders": [],
    "spending_flags": [],
}


def _ensure_data_dir() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def setup_db() -> None:
    _ensure_data_dir()
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                session_number INTEGER NOT NULL,
                role           TEXT NOT NULL,
                content        TEXT,
                raw_message    TEXT NOT NULL,
                created_at     TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def save_message(session_number: int, message: dict) -> None:
    role = message.get("role", "")
    content = message.get("content") if isinstance(message.get("content"), str) else None
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (session_number, role, content, raw_message) VALUES (?, ?, ?, ?)",
            (session_number, role, content, json.dumps(message)),
        )
        conn.commit()


def load_session_messages(session_number: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT raw_message FROM messages WHERE session_number = ? ORDER BY id ASC",
            (session_number,),
        ).fetchall()
    return [json.loads(row["raw_message"]) for row in rows]


def load_memory() -> dict:
    if not os.path.exists(_MEMORY_PATH):
        data = dict(_EMPTY_MEMORY)
    else:
        with open(_MEMORY_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            data = json.loads(content) if content else dict(_EMPTY_MEMORY)
    log_event(event="memory_read", memory=data)
    return data


def save_memory(memory: dict) -> None:
    _ensure_data_dir()
    with open(_MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def merge_memory(updates: dict) -> None:
    log_event(event="memory_write", via="merge_memory", updates=updates)
    """Merge extracted session insights into memory.json.

    - goal: overwritten only if updates provides a non-empty value
    - active_commitments / spending_flags: new items appended, duplicates dropped
    - reminders: not touched here (written live by set_reminder interception)
    """
    current = load_memory()

    if updates.get("goal"):
        current["goal"] = updates["goal"]

    for key in ("active_commitments", "spending_flags"):
        existing = set(current.get(key, []))
        for item in updates.get(key, []):
            if item not in existing:
                current.setdefault(key, []).append(item)
                existing.add(item)

    save_memory(current)


def append_reminder(date: str, content: str) -> None:
    log_event(event="memory_write", via="append_reminder", date=date, content=content)
    memory = load_memory()
    entry = {"date": date, "content": content}
    if entry not in memory.get("reminders", []):
        memory.setdefault("reminders", []).append(entry)
    save_memory(memory)
