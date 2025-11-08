# cogs/economia/db_manager.py
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import datetime

DB_FILE = Path(__file__).parent / "economia.db"

# --- RENOMBRADA CLASE ---
class EconomiaDBManagerV2:
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
            CREATE TABLE IF NOT EXISTS economia_usuarios (
                user_id INTEGER PRIMARY KEY,
                puntos_actuales INTEGER DEFAULT 0,
                puntos_conseguidos INTEGER DEFAULT 0,
                puntos_gastados INTEGER DEFAULT 0,
                creditos_pin INTEGER DEFAULT 0,
                reclamado_rol_creador INTEGER DEFAULT 0 
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventario_blisters (
                user_id INTEGER NOT NULL,
                blister_tipo TEXT NOT NULL,
                cantidad INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, blister_tipo),
                FOREIGN KEY (user_id) REFERENCES economia_usuarios (user_id) ON DELETE CASCADE
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventario_cartas (
                user_id INTEGER NOT NULL,
                carta_id INTEGER NOT NULL,
                cantidad INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, carta_id),
                FOREIGN KEY (user_id) REFERENCES economia_usuarios (user_id) ON DELETE CASCADE
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tareas_inicial (
                user_id INTEGER PRIMARY KEY,
                presentacion INTEGER DEFAULT 0,
                reaccion_pais INTEGER DEFAULT 0,
                reaccion_rol INTEGER DEFAULT 0,
                reaccion_social INTEGER DEFAULT 0,
                reaccion_reglas INTEGER DEFAULT 0,
                general_mensaje INTEGER DEFAULT 0,
                completado INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES economia_usuarios (user_id) ON DELETE CASCADE
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tareas_diarias (
                user_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                general_mensajes INTEGER DEFAULT 0,
                debate_actividad INTEGER DEFAULT 0,
                media_actividad INTEGER DEFAULT 0,
                completado INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, fecha)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tareas_semanales (
                user_id INTEGER NOT NULL,
                semana TEXT NOT NULL,
                debate_post INTEGER DEFAULT 0,
                videos_reaccion INTEGER DEFAULT 0,
                media_escrito INTEGER DEFAULT 0,
                completado INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, semana)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial_cartas (
                historial_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES economia_usuarios (user_id) ON DELETE CASCADE
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS creador_posts (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL UNIQUE,
                semana_key TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES economia_usuarios (user_id) ON DELETE CASCADE
            );
            """)
            conn.commit()
    
    def _check_and_update_schema(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("PRAGMA table_info(economia_usuarios)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'reclamado_rol_creador' not in columns:
                    cursor.execute("ALTER TABLE economia_usuarios ADD COLUMN reclamado_rol_creador INTEGER DEFAULT 0")
                    print("DATABASE MIGRATED: Added 'reclamado_rol_creador' column to economia_usuarios.")
                conn.commit()
            except Exception as e:
                print(f"Error actualizando el schema de economia_usuarios: {e}")

    def ensure_user_exists(self, user_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO economia_usuarios (user_id) VALUES (?)", (user_id,))
            cursor.execute("INSERT OR IGNORE INTO tareas_inicial (user_id) VALUES (?)", (user_id,))
            conn.commit()

    def get_user_economy(self, user_id: int) -> Optional[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM economia_usuarios WHERE user_id = ?", (user_id,))
            return dict(cursor.fetchone())

    def modify_points(self, user_id: int, cantidad: int, gastar: bool = False) -> int:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if gastar:
                cantidad_abs = abs(cantidad)
                cursor.execute("UPDATE economia_usuarios SET puntos_actuales = MAX(0, puntos_actuales - ?), puntos_gastados = puntos_gastados + ? WHERE user_id = ?", (cantidad_abs, cantidad_abs, user_id))
            else:
                cantidad_abs = abs(cantidad)
                cursor.execute("UPDATE economia_usuarios SET puntos_actuales = puntos_actuales + ?, puntos_conseguidos = puntos_conseguidos + ? WHERE user_id = ?", (cantidad_abs, cantidad_abs, user_id))
            conn.commit()
            cursor.execute("SELECT puntos_actuales FROM economia_usuarios WHERE user_id = ?", (user_id,))
            return cursor.fetchone()[0]

    def modify_blisters(self, user_id: int, blister_tipo: str, cantidad: int) -> int:
        self.ensure_user_exists(user_id)
        blister_tipo = blister_tipo.lower().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO inventario_blisters (user_id, blister_tipo, cantidad) VALUES (?, ?, MAX(0, ?)) ON CONFLICT(user_id, blister_tipo) DO UPDATE SET cantidad = MAX(0, cantidad + ?)", (user_id, blister_tipo, cantidad, cantidad))
            conn.commit()
            cursor.execute("SELECT cantidad FROM inventario_blisters WHERE user_id = ? AND blister_tipo = ?", (user_id, blister_tipo))
            result = cursor.fetchone()
            return result[0] if result else 0

    def set_credits(self, user_id: int, cantidad: int) -> int:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE economia_usuarios SET creditos_pin = ? WHERE user_id = ?", (cantidad, user_id))
            conn.commit()
            return cantidad
    
    def use_credit(self, user_id: int) -> bool:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT creditos_pin FROM economia_usuarios WHERE user_id = ?", (user_id,))
            creditos = cursor.fetchone()[0]
            if creditos > 0:
                cursor.execute("UPDATE economia_usuarios SET creditos_pin = creditos_pin - 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                return True
            return False

    def get_current_date_keys(self) -> (str, str):
        now = datetime.datetime.now()
        fecha = now.strftime("%Y-%m-%d")
        semana = now.strftime("%Y-%U")
        return fecha, semana

    def get_progress_inicial(self, user_id: int) -> Dict[str, Any]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tareas_inicial WHERE user_id = ?", (user_id,))
            return dict(cursor.fetchone())

    def get_progress_diaria(self, user_id: int) -> Dict[str, Any]:
        self.ensure_user_exists(user_id)
        fecha, _ = self.get_current_date_keys()
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO tareas_diarias (user_id, fecha) VALUES (?, ?)", (user_id, fecha))
            cursor.execute("SELECT * FROM tareas_diarias WHERE user_id = ? AND fecha = ?", (user_id, fecha))
            return dict(cursor.fetchone())
            
    def get_progress_semanal(self, user_id: int) -> Dict[str, Any]:
        self.ensure_user_exists(user_id)
        _, semana = self.get_current_date_keys()
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO tareas_semanales (user_id, semana) VALUES (?, ?)", (user_id, semana))
            cursor.execute("SELECT * FROM tareas_semanales WHERE user_id = ? AND semana = ?", (user_id, semana))
            return dict(cursor.fetchone())

    def update_task_inicial(self, user_id: int, task_name: str):
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE tareas_inicial SET {task_name} = 1 WHERE user_id = ? AND completado = 0", (user_id,))
            conn.commit()
    
    def update_task_diaria(self, user_id: int, task_name: str, fecha: str, amount: int = 1):
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO tareas_diarias (user_id, fecha) VALUES (?, ?)", (user_id, fecha))
            cursor.execute(f"UPDATE tareas_diarias SET {task_name} = {task_name} + ? WHERE user_id = ? AND fecha = ? AND completado = 0", (amount, user_id, fecha))
            conn.commit()
            
    def update_task_semanal(self, user_id: int, task_name: str, semana: str, amount: int = 1):
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO tareas_semanales (user_id, semana) VALUES (?, ?)", (user_id, semana))
            cursor.execute(f"UPDATE tareas_semanales SET {task_name} = {task_name} + ? WHERE user_id = ? AND semana = ? AND completado = 0", (amount, user_id, semana))
            conn.commit()

    def claim_reward(self, user_id: int, task_type: str) -> bool:
        self.ensure_user_exists(user_id)
        fecha, semana = self.get_current_date_keys()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if task_type == "inicial":
                cursor.execute("UPDATE tareas_inicial SET completado = 1 WHERE user_id = ?", (user_id,))
            elif task_type == "diaria":
                cursor.execute("UPDATE tareas_diarias SET completado = 1 WHERE user_id = ? AND fecha = ?", (user_id, fecha))
            elif task_type == "semanal":
                cursor.execute("UPDATE tareas_semanales SET completado = 1 WHERE user_id = ? AND semana = ?", (user_id, semana))
            conn.commit()
            return cursor.rowcount > 0

    def get_blisters_for_user(self, user_id: int) -> List[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT blister_tipo, cantidad FROM inventario_blisters WHERE user_id = ? AND cantidad > 0", (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def add_card_to_inventory(self, user_id: int, carta_id: int, cantidad: int = 1) -> int:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO inventario_cartas (user_id, carta_id, cantidad) VALUES (?, ?, ?) ON CONFLICT(user_id, carta_id) DO UPDATE SET cantidad = cantidad + ?", (user_id, carta_id, cantidad, cantidad))
            conn.commit()
            cursor.execute("SELECT cantidad FROM inventario_cartas WHERE user_id = ? AND carta_id = ?", (user_id, carta_id))
            return cursor.fetchone()[0]

    def get_cards_in_inventory(self, user_id: int) -> List[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT carta_id, cantidad FROM inventario_cartas WHERE user_id = ? AND cantidad > 0", (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_card_from_inventory(self, user_id: int, carta_id: int) -> Optional[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM inventario_cartas WHERE user_id = ? AND carta_id = ? AND cantidad > 0", (user_id, carta_id))
            row = cursor.fetchone()
            return dict(row) if row else None

    def use_card_from_inventory(self, user_id: int, carta_id: int) -> bool:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE inventario_cartas SET cantidad = cantidad - 1 WHERE user_id = ? AND carta_id = ? AND cantidad > 0", (user_id, carta_id))
            conn.commit()
            return cursor.rowcount > 0

    def log_card_usage(self, user_id: int):
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO historial_cartas (user_id, timestamp) VALUES (?, ?)", (user_id, int(time.time())))
            conn.commit()

    def get_card_usage_history(self, user_id: int, minutes: int = 10) -> List[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            time_limit = int(time.time()) - (minutes * 60)
            cursor.execute("SELECT * FROM historial_cartas WHERE user_id = ? AND timestamp > ?", (user_id, time_limit))
            return [dict(row) for row in cursor.fetchall()]
            
    def get_top_users(self, ranking_type: str, limit: int = 10) -> List[Dict[str, Any]]:
        column_map = {"actual": "puntos_actuales", "conseguidos": "puntos_conseguidos", "gastados": "puntos_gastados"}
        column_name = column_map.get(ranking_type, "actual")
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = f"SELECT user_id, {column_name} FROM economia_usuarios WHERE {column_name} > 0 ORDER BY {column_name} DESC LIMIT ?"
            cursor.execute(query, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_rol_creador_status(self, user_id: int) -> int:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT reclamado_rol_creador FROM economia_usuarios WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 0

    def claim_rol_creador(self, user_id: int) -> bool:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE economia_usuarios SET reclamado_rol_creador = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
            
    def get_creator_posts_this_week(self, user_id: int, semana_key: str) -> List[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM creador_posts WHERE user_id = ? AND semana_key = ?", (user_id, semana_key))
            return [dict(row) for row in cursor.fetchall()]

    def log_creator_post(self, user_id: int, message_id: int, semana_key: str):
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO creador_posts (user_id, message_id, semana_key) VALUES (?, ?, ?)", (user_id, message_id, semana_key))
            conn.commit()