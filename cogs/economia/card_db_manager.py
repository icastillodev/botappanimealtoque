# cogs/economia/card_db_manager.py
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import random

DB_FILE = Path(__file__).parent / "cartas.db"

# Sufijo numérico al final de `numeracion` (p.ej. AAT-2 vs AAT-10 → 2 antes que 10).
_NUM_TAIL = re.compile(r"(\d+)\s*$")


def _catalog_sort_key(card: Dict[str, Any]) -> Tuple[str, int, int]:
    raw = str(card.get("numeracion") or "").strip()
    cid = int(card.get("carta_id") or 0)
    m = _NUM_TAIL.search(raw)
    if m:
        prefix = raw[: m.start(1)].lower()
        tail = int(m.group(1))
        return (prefix, tail, cid)
    # Sin número final reconocible: al final, estable por id.
    return ("\uffff", 0, cid)


class CardDBManager:
    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self._create_tables()
        self._migrate_schema()

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

    def _migrate_schema(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(cartas_stock)")
            cols = [c[1] for c in cursor.fetchall()]
            if "poder" not in cols:
                cursor.execute("ALTER TABLE cartas_stock ADD COLUMN poder INTEGER NOT NULL DEFAULT 50")
                conn.commit()
                print("DATABASE MIGRATED: Added 'poder' to cartas_stock.")
            self._migrate_numeracion_unique_index(conn)

    def _migrate_numeracion_unique_index(self, conn) -> None:
        """
        Una sola carta por numeración (comparación sin distinguir mayúsculas / espacios laterales).
        Si ya había duplicados, se renombran las “extra” a `CODIGO ·#<carta_id>` para poder crear el índice.
        """
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_cartas_stock_numeracion_norm_unique'"
        )
        if cursor.fetchone():
            return

        cursor.execute(
            """
            SELECT lower(trim(numeracion)) AS nk, group_concat(carta_id ORDER BY carta_id) AS ids
            FROM cartas_stock
            WHERE numeracion IS NOT NULL AND length(trim(numeracion)) > 0
            GROUP BY lower(trim(numeracion))
            HAVING COUNT(*) > 1
            """
        )
        for nk, id_blob in cursor.fetchall():
            ids = [int(x) for x in str(id_blob).split(",") if str(x).strip().isdigit()]
            if len(ids) < 2:
                continue
            keeper = ids[0]
            for cid in ids[1:]:
                cursor.execute("SELECT numeracion FROM cartas_stock WHERE carta_id = ?", (cid,))
                row = cursor.fetchone()
                base = (row[0] if row else nk or "").strip()
                new_val = f"{base} ·#{cid}"
                cursor.execute(
                    "UPDATE cartas_stock SET numeracion = ? WHERE carta_id = ?",
                    (new_val, cid),
                )
                print(f"DATABASE MIGRATED: numeración duplicada resuelta carta_id={cid} -> {new_val!r}")

        # Guardar deduplicación aunque falle el CREATE INDEX (DDL puede ir en otra transacción).
        conn.commit()

        try:
            cursor.execute(
                """
                CREATE UNIQUE INDEX idx_cartas_stock_numeracion_norm_unique
                ON cartas_stock (lower(trim(numeracion)))
                WHERE numeracion IS NOT NULL AND length(trim(numeracion)) > 0
                """
            )
            conn.commit()
            print("DATABASE MIGRATED: índice único idx_cartas_stock_numeracion_norm_unique creado.")
        except sqlite3.OperationalError as e:
            print(f"DATABASE MIGRATE WARN: no se pudo crear índice único de numeración: {e}")

    @staticmethod
    def _norm_num_key(numeracion: Optional[str]) -> str:
        return (numeracion or "").strip().lower()

    def _numeracion_en_uso(self, conn, numeracion: str, exclude_id: Optional[int]) -> bool:
        key = self._norm_num_key(numeracion)
        if not key:
            return False
        cursor = conn.cursor()
        if exclude_id is None:
            cursor.execute(
                """
                SELECT 1 FROM cartas_stock
                WHERE numeracion IS NOT NULL AND length(trim(numeracion)) > 0
                  AND lower(trim(numeracion)) = ?
                LIMIT 1
                """,
                (key,),
            )
        else:
            cursor.execute(
                """
                SELECT 1 FROM cartas_stock
                WHERE carta_id != ? AND numeracion IS NOT NULL AND length(trim(numeracion)) > 0
                  AND lower(trim(numeracion)) = ?
                LIMIT 1
                """,
                (exclude_id, key),
            )
        return cursor.fetchone() is not None

    @staticmethod
    def _nombre_en_uso(conn, nombre: str, exclude_id: Optional[int]) -> bool:
        nombre = (nombre or "").strip()
        if not nombre:
            return False
        cursor = conn.cursor()
        if exclude_id is None:
            cursor.execute("SELECT 1 FROM cartas_stock WHERE nombre = ? LIMIT 1", (nombre,))
        else:
            cursor.execute(
                "SELECT 1 FROM cartas_stock WHERE nombre = ? AND carta_id != ? LIMIT 1",
                (nombre, exclude_id),
            )
        return cursor.fetchone() is not None

    def add_carta_stock(
        self,
        nombre: str,
        descripcion: str,
        efecto: str,
        url_imagen: str,
        rareza: str,
        tipo_carta: str,
        numeracion: str,
        poder: int = 50,
    ) -> Tuple[bool, str]:
        nombre = (nombre or "").strip()
        numeracion = (numeracion or "").strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if self._nombre_en_uso(conn, nombre, None):
                return False, "Ya existe otra carta con ese **nombre**."
            if self._numeracion_en_uso(conn, numeracion, None):
                return False, "Ya existe otra carta con esa **numeración** (código duplicado)."
            try:
                cursor.execute(
                    """
                    INSERT INTO cartas_stock (nombre, descripcion, efecto, url_imagen, rareza, tipo_carta, numeracion, poder)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        nombre,
                        descripcion,
                        efecto,
                        url_imagen,
                        rareza.capitalize(),
                        tipo_carta.capitalize(),
                        numeracion,
                        int(poder),
                    ),
                )
                conn.commit()
                return True, ""
            except sqlite3.IntegrityError:
                conn.rollback()
                return False, "No se pudo crear (nombre o numeración duplicada según la base de datos)."

    def update_carta_stock(
        self,
        carta_id: int,
        nombre: str,
        descripcion: str,
        efecto: str,
        url_imagen: str,
        rareza: str,
        tipo_carta: str,
        numeracion: str,
        poder: int = 50,
    ) -> Tuple[bool, str]:
        nombre = (nombre or "").strip()
        numeracion = (numeracion or "").strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if self._nombre_en_uso(conn, nombre, int(carta_id)):
                return False, "Ese **nombre** ya lo usa otra carta (cambiá uno de los dos)."
            if self._numeracion_en_uso(conn, numeracion, int(carta_id)):
                return (
                    False,
                    "Esa **numeración** ya la usa otra carta (no pueden repetirse; elegí otro código o editá la otra con `/aat-admin-modificar-carta`).",
                )
            try:
                cursor.execute(
                    """
                    UPDATE cartas_stock SET
                    nombre = ?, descripcion = ?, efecto = ?, url_imagen = ?, rareza = ?, tipo_carta = ?, numeracion = ?, poder = ?
                    WHERE carta_id = ?
                    """,
                    (
                        nombre,
                        descripcion,
                        efecto,
                        url_imagen,
                        rareza.capitalize(),
                        tipo_carta.capitalize(),
                        numeracion,
                        int(poder),
                        carta_id,
                    ),
                )
                if cursor.rowcount == 0:
                    conn.rollback()
                    return False, "No se encontró esa carta (id inválido)."
                conn.commit()
                return True, ""
            except sqlite3.IntegrityError:
                conn.rollback()
                return False, "Conflicto en la base de datos (nombre o numeración duplicada)."

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
            cursor.execute(
                """
                SELECT carta_id, nombre, numeracion FROM cartas_stock
                WHERE nombre LIKE ? OR numeracion LIKE ?
                ORDER BY carta_id ASC
                LIMIT 25
                """,
                (f"%{query}%", f"%{query}%"),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_carta_stock_by_id(self, carta_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cartas_stock WHERE carta_id = ?", (carta_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("poder") is None:
                d["poder"] = 50
            return d

    def get_random_card_by_rarity(self) -> Optional[Dict[str, Any]]:
        roll = random.randint(1, 100)

        if roll <= 70:
            rareza = "Común"
        elif roll <= 95:
            rareza = "Rara"
        else:
            rareza = "Legendaria"

        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM cartas_stock
                WHERE rareza = ?
                ORDER BY RANDOM() LIMIT 1
                """,
                (rareza,),
            )

            row = cursor.fetchone()

            if not row and rareza != "Común":
                cursor.execute(
                    """
                    SELECT * FROM cartas_stock
                    WHERE rareza = 'Común'
                    ORDER BY RANDOM() LIMIT 1
                    """
                )
                row = cursor.fetchone()

            return dict(row) if row else None

    def get_random_card_blister_trampa(self) -> Optional[Dict[str, Any]]:
        """Sobres tipo trampa: prioriza cartas con tipo Trampa (~70%), si no hay stock cae al gacha normal."""
        if random.randint(1, 100) > 30:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT * FROM cartas_stock
                    WHERE LOWER(tipo_carta) = 'trampa'
                    ORDER BY RANDOM() LIMIT 1
                    """
                )
                row = cursor.fetchone()
                if row:
                    d = dict(row)
                    if d.get("poder") is None:
                        d["poder"] = 50
                    return d
        return self.get_random_card_by_rarity()

    def get_all_cards_stock(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cartas_stock")
            rows = [dict(row) for row in cursor.fetchall()]
            rows.sort(key=_catalog_sort_key)
            return rows

    def get_stock_by_type(self, tipo_carta: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT carta_id, nombre, rareza, numeracion, tipo_carta FROM cartas_stock
                WHERE LOWER(tipo_carta) = LOWER(?)
                """,
                (tipo_carta,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            rows.sort(key=_catalog_sort_key)
            return rows
