# cogs/impostor/stats.py
import os
import aiosqlite
from typing import Tuple, List

DB_PATH = os.getenv("IMPOSTOR_DB_PATH", "./data/impostor.db")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS impostor_user_stats (
  guild_id INTEGER NOT NULL,
  user_id  INTEGER NOT NULL,
  impostor_wins INTEGER NOT NULL DEFAULT 0,
  social_wins   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (guild_id, user_id)
);
"""

class StatsStore:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.db: aiosqlite.Connection | None = None

    async def ensure(self):
        if self.db is None:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self.db = await aiosqlite.connect(self.path)
            await self.db.execute(CREATE_SQL)
            await self.db.commit()

    async def add_win(self, guild_id: int, user_id: int, role: str):
        """role: 'IMPOSTOR' o 'SOCIAL'"""
        await self.ensure()
        assert self.db is not None
        await self.db.execute(
            "INSERT OR IGNORE INTO impostor_user_stats (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        if role == "IMPOSTOR":
            await self.db.execute(
                "UPDATE impostor_user_stats SET impostor_wins = impostor_wins + 1 WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            )
        else:
            await self.db.execute(
                "UPDATE impostor_user_stats SET social_wins = social_wins + 1 WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            )
        await self.db.commit()

    async def get_user(self, guild_id: int, user_id: int) -> Tuple[int, int]:
        """Devuelve (impostor_wins, social_wins)"""
        await self.ensure()
        assert self.db is not None
        async with self.db.execute(
            "SELECT impostor_wins, social_wins FROM impostor_user_stats WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return (0, 0)
            return (int(row[0]), int(row[1]))

    async def get_all(self, guild_id: int) -> List[tuple[int, int, int, int]]:
        """
        Devuelve lista de filas: (user_id, impostor_wins, social_wins, total)
        Ordenada por total desc, luego impostor_wins desc.
        """
        await self.ensure()
        assert self.db is not None
        async with self.db.execute(
            """
            SELECT user_id, impostor_wins, social_wins,
                   (impostor_wins + social_wins) as total
            FROM impostor_user_stats
            WHERE guild_id=?
            ORDER BY total DESC, impostor_wins DESC, user_id ASC
            """,
            (guild_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [(int(r[0]), int(r[1]), int(r[2]), int(r[3])) for r in rows]

# instancia global para usar desde otros módulos
stats_store = StatsStore()
