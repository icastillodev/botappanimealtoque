# cogs/semanal_versus/db.py
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_FILE = Path(__file__).parent / "versus.db"


class VersusDB:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS versus_polls (
                    week_key TEXT PRIMARY KEY,
                    message_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    char_a TEXT NOT NULL,
                    char_b TEXT NOT NULL,
                    closed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS versus_votes (
                    week_key TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    side INTEGER NOT NULL,
                    PRIMARY KEY (week_key, user_id)
                )
                """
            )

    def insert_poll_new(self, week_key: str, message_id: int, channel_id: int, char_a: str, char_b: str) -> bool:
        """Devuelve True si insertó fila nueva."""
        with self._conn() as c:
            cur = c.execute(
                """
                INSERT OR IGNORE INTO versus_polls (week_key, message_id, channel_id, char_a, char_b, closed)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (week_key, message_id, channel_id, char_a, char_b),
            )
            return cur.rowcount > 0

    def get_poll(self, week_key: str) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            cur = c.execute("SELECT * FROM versus_polls WHERE week_key = ?", (week_key,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_open_polls(self) -> List[Dict[str, Any]]:
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            cur = c.execute("SELECT * FROM versus_polls WHERE closed = 0")
            return [dict(r) for r in cur.fetchall()]

    def set_vote(self, week_key: str, user_id: int, side: int) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO versus_votes (week_key, user_id, side) VALUES (?, ?, ?)
                ON CONFLICT(week_key, user_id) DO UPDATE SET side = excluded.side
                """,
                (week_key, user_id, side),
            )

    def get_votes(self, week_key: str) -> List[Dict[str, Any]]:
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            cur = c.execute("SELECT user_id, side FROM versus_votes WHERE week_key = ?", (week_key,))
            return [dict(r) for r in cur.fetchall()]

    def mark_closed(self, week_key: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE versus_polls SET closed = 1 WHERE week_key = ?", (week_key,))

    def update_poll_message(self, week_key: str, message_id: int, channel_id: Optional[int] = None) -> None:
        """Tras reinicio: mismo versus pero nuevo message_id (ej. mensaje borrado)."""
        with self._conn() as c:
            if channel_id is not None:
                c.execute(
                    "UPDATE versus_polls SET message_id = ?, channel_id = ? WHERE week_key = ?",
                    (message_id, channel_id, week_key),
                )
            else:
                c.execute("UPDATE versus_polls SET message_id = ? WHERE week_key = ?", (message_id, week_key))
