"""SQLite-backed long-term memory.

Stores:
  - Conversations: every turn of every chat
  - Preferences: small KV store of facts the user has expressed
  - Facts: a free-form table of "things the agent has learned"

The agent reads from this on every chat and writes back when it learns
something new. The DB lives at <state-dir>/memory.db.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.log import get_logger
from shared.types import ChatMessage, Role
from shared.util import state_dir, now

log = get_logger("llm.memory")

DB_PATH = state_dir() / "memory.db"


@dataclass
class Memory:
    db_path: Path = DB_PATH
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    def _init_schema(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    ts REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    fact TEXT NOT NULL,
                    source TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_conv_ts ON conversations(ts);
                CREATE INDEX IF NOT EXISTS idx_facts_ts ON facts(ts);
                """
            )

    # ---- conversations ---------------------------------------------------

    def append(self, msg: ChatMessage) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO conversations (ts, role, content, metadata) VALUES (?, ?, ?, ?)",
                (
                    msg.timestamp or now(),
                    msg.role.value,
                    msg.content,
                    json.dumps({"name": msg.name} if msg.name else {}),
                ),
            )

    def recent(self, limit: int = 20) -> list[ChatMessage]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT ts, role, content FROM conversations ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            ChatMessage(role=Role(r["role"]), content=r["content"], timestamp=r["ts"])
            for r in reversed(rows)
        ]

    def as_messages(self, limit: int = 20) -> list[dict[str, str]]:
        out = []
        for m in self.recent(limit=limit):
            out.append({"role": m.role.value, "content": m.content})
        return out

    # ---- preferences -----------------------------------------------------

    def set_pref(self, key: str, value: Any) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO preferences (key, value, ts) VALUES (?, ?, ?)",
                (key, json.dumps(value), now()),
            )

    def get_pref(self, key: str, default: Any = None) -> Any:
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT value FROM preferences WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row["value"]) if row else default

    def all_prefs(self) -> dict[str, Any]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT key, value FROM preferences").fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    # ---- facts -----------------------------------------------------------

    def add_fact(self, fact: str, source: str | None = None) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO facts (ts, fact, source) VALUES (?, ?, ?)",
                (now(), fact, source),
            )

    def facts(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT ts, fact, source FROM facts ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"ts": r["ts"], "fact": r["fact"], "source": r["source"]} for r in rows]

    def clear_facts(self) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM facts")


memory = Memory()