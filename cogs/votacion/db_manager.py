# cogs/votacion/db_manager.py
import sqlite3
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_FILE = Path(__file__).parent / "votacion.db"

class PollDBManagerV4:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self._create_tables()
        self._check_and_update_schema()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                image_url TEXT,
                link_url TEXT,
                limite_votos INTEGER DEFAULT 1, 
                formato_votos TEXT DEFAULT 'ambos',
                end_timestamp INTEGER,
                is_active INTEGER DEFAULT 1
            );
            """)
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS poll_options (
                option_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                FOREIGN KEY (message_id) REFERENCES polls (message_id) ON DELETE CASCADE
            );
            """)
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                UNIQUE(message_id, user_id, option_id),
                FOREIGN KEY (message_id) REFERENCES polls (message_id) ON DELETE CASCADE,
                FOREIGN KEY (option_id) REFERENCES poll_options (option_id) ON DELETE CASCADE
            );
            """)
            conn.commit()

    def _check_and_update_schema(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("PRAGMA table_info(polls)")
                columns = [col[1] for col in cursor.fetchall()]
                
                if 'limite_votos' not in columns:
                    cursor.execute("ALTER TABLE polls ADD COLUMN limite_votos INTEGER DEFAULT 1")
                    print("DATABASE MIGRATED: Added 'limite_votos' column.")
                
                if 'formato_votos' not in columns:
                    cursor.execute("ALTER TABLE polls ADD COLUMN formato_votos TEXT DEFAULT 'ambos'")
                    print("DATABASE MIGRATED: Added 'formato_votos' column.")

                if 'max_votes' in columns:
                    cursor.execute("ALTER TABLE polls RENAME COLUMN max_votes TO vote_limit_old")
                    print("DATABASE MIGRATED: Renamed old 'max_votes' column.")
                if 'vote_limit' in columns:
                    cursor.execute("ALTER TABLE polls RENAME COLUMN vote_limit TO vote_limit_old_2")
                    print("DATABASE MIGRATED: Renamed old 'vote_limit' column.")

            except Exception as e:
                print(f"Error actualizando el schema de la DB: {e}")

    def add_poll(self, message_id: int, guild_id: int, channel_id: int, creator_id: int,
                 title: str, options: List[str], description: Optional[str], 
                 image_url: Optional[str], link_url: Optional[str], 
                 limite_votos: int, 
                 formato_votos: str, 
                 end_timestamp: Optional[int]) -> None:
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
            INSERT INTO polls (message_id, guild_id, channel_id, creator_id, title, description, 
                               image_url, link_url, limite_votos, formato_votos, end_timestamp, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (message_id, guild_id, channel_id, creator_id, title, description, 
                  image_url, link_url, limite_votos, formato_votos, end_timestamp, 
                  1))
            
            for option_label in options:
                cursor.execute("""
                INSERT INTO poll_options (message_id, label)
                VALUES (?, ?)
                """, (message_id, option_label))
            
            conn.commit()

    def add_vote(self, message_id: int, user_id: int, option_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                INSERT INTO poll_votes (message_id, option_id, user_id)
                VALUES (?, ?, ?)
                """, (message_id, option_id, user_id))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_vote(self, message_id: int, user_id: int, option_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            DELETE FROM poll_votes 
            WHERE message_id = ? AND user_id = ? AND option_id = ?
            """, (message_id, user_id, option_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_user_votes_for_poll(self, message_id: int, user_id: int) -> List[int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT option_id FROM poll_votes 
            WHERE message_id = ? AND user_id = ?
            """, (message_id, user_id))
            return [row[0] for row in cursor.fetchall()]

    def get_poll_data(self, message_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM polls WHERE message_id = ?", (message_id,))
            poll_row = cursor.fetchone()
            
            if not poll_row:
                return None
                
            poll_data = dict(poll_row)
            
            cursor.execute("""
            SELECT o.option_id, o.label, COUNT(v.vote_id) as vote_count
            FROM poll_options o
            LEFT JOIN poll_votes v ON o.option_id = v.option_id
            WHERE o.message_id = ?
            GROUP BY o.option_id, o.label
            ORDER BY o.option_id
            """, (message_id,))
            
            poll_data['options'] = [dict(row) for row in cursor.fetchall()]
            return poll_data

    def get_active_polls(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM polls WHERE is_active = 1")
            polls = [dict(row) for row in cursor.fetchall()]
            
            for poll in polls:
                cursor.execute("""
                SELECT option_id, label FROM poll_options WHERE message_id = ?
                """, (poll['message_id'],))
                poll['options'] = [dict(row) for row in cursor.fetchall()]
                
            return polls

    def close_poll(self, message_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE polls SET is_active = 0 WHERE message_id = ?
            """, (message_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_poll(self, message_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM polls WHERE message_id = ?", (message_id,))
            conn.commit()
            return cursor.rowcount > 0

    # --- ¡¡¡NUEVA FUNCIÓN PARA AUTOCOMPLETAR!!! ---
    def get_active_polls_by_title(self, query: str) -> List[Dict[str, Any]]:
        """Busca votaciones activas por título para el autocompletado."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Busca títulos que contengan el texto
            cursor.execute("""
                SELECT message_id, title FROM polls
                WHERE is_active = 1 AND title LIKE ?
                ORDER BY message_id DESC
                LIMIT 25
            """, (f'%{query}%',))
            return [dict(row) for row in cursor.fetchall()]