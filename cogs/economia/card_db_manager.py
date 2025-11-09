# cogs/economia/card_db_manager.py
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
import random

DB_FILE = Path(__file__).parent / "cartas.db"

class CardDBManager:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self._create_tables()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS cartas_stock (
                carta_id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                descripcion TEXT,
                efecto TEXT,
                url_imagen TEXT,
                rareza TEXT NOT NULL,
                tipo_carta TEXT NOT NULL,
                numeracion TEXT
            );
            """)
            conn.commit()

    def add_carta_stock(self, nombre: str, descripcion: str, efecto: str, url_imagen: str, rareza: str, tipo_carta: str, numeracion: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO cartas_stock (nombre, descripcion, efecto, url_imagen, rareza, tipo_carta, numeracion)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (nombre, descripcion, efecto, url_imagen, rareza, tipo_carta, numeracion))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def update_carta_stock(self, carta_id: int, nombre: str, descripcion: str, efecto: str, url_imagen: str, rareza: str, tipo_carta: str, numeracion: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    UPDATE cartas_stock SET
                    nombre = ?, descripcion = ?, efecto = ?, url_imagen = ?, rareza = ?, tipo_carta = ?, numeracion = ?
                    WHERE carta_id = ?
                """, (nombre, descripcion, efecto, url_imagen, rareza, tipo_carta, numeracion, carta_id))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_carta_stock(self, carta_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cartas_stock WHERE carta_id = ?", (carta_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_cartas_stock_by_name(self, query: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT carta_id, nombre, numeracion FROM cartas_stock
                WHERE nombre LIKE ? OR numeracion LIKE ?
                ORDER BY numeracion
                LIMIT 25
            """, (f'%{query}%', f'%{query}%'))
            return [dict(row) for row in cursor.fetchall()]

    def get_carta_stock_by_id(self, carta_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cartas_stock WHERE carta_id = ?", (carta_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
            
    def get_random_card_by_rarity(self, tipo_carta: str) -> Optional[Dict[str, Any]]:
        roll = random.randint(1, 100)
        if roll <= 70: rareza = "Común"
        elif roll <= 95: rareza = "Rara"
        else: rareza = "Legendaria"
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM cartas_stock
                WHERE rareza = ? AND tipo_carta = ?
                ORDER BY RANDOM() LIMIT 1
            """, (rareza, tipo_carta.capitalize()))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_cards_stock(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Esta ya ordenaba por 'numeracion', ¡está perfecta!
            cursor.execute("SELECT * FROM cartas_stock ORDER BY numeracion ASC")
            return [dict(row) for row in cursor.fetchall()]

    # --- ¡¡¡MODIFICADO!!! ---
    def get_stock_by_type(self, tipo_carta: str) -> List[Dict[str, Any]]:
        """Obtiene todas las cartas de un tipo, ordenadas por numeración."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Cambiado el 'ORDER BY' para que priorice la 'numeracion'
            cursor.execute("""
                SELECT nombre, rareza, numeracion, tipo_carta FROM cartas_stock
                WHERE tipo_carta = ?
                ORDER BY numeracion ASC
            """, (tipo_carta.capitalize(),))
            return [dict(row) for row in cursor.fetchall()]