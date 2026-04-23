# cogs/economia/db_manager.py
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import datetime

from .toque_labels import fmt_toque_sentence

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
                for col, sql in [
                    ("anime_bonus_top10", "ALTER TABLE economia_usuarios ADD COLUMN anime_bonus_top10 INTEGER DEFAULT 0"),
                    ("anime_bonus_top30", "ALTER TABLE economia_usuarios ADD COLUMN anime_bonus_top30 INTEGER DEFAULT 0"),
                    (
                        "blister_collector_version_claimed",
                        "ALTER TABLE economia_usuarios ADD COLUMN blister_collector_version_claimed INTEGER DEFAULT 0",
                    ),
                ]:
                    if col not in columns:
                        cursor.execute(sql)
                        print(f"DATABASE MIGRATED: Added '{col}' to economia_usuarios.")

                cursor.execute("PRAGMA table_info(tareas_diarias)")
                dcols = [c[1] for c in cursor.fetchall()]
                for col, sql in [
                    ("mensajes_servidor", "ALTER TABLE tareas_diarias ADD COLUMN mensajes_servidor INTEGER DEFAULT 0"),
                    ("reacciones_servidor", "ALTER TABLE tareas_diarias ADD COLUMN reacciones_servidor INTEGER DEFAULT 0"),
                    ("trampa_enviada", "ALTER TABLE tareas_diarias ADD COLUMN trampa_enviada INTEGER DEFAULT 0"),
                    ("trampa_sin_objetivo", "ALTER TABLE tareas_diarias ADD COLUMN trampa_sin_objetivo INTEGER DEFAULT 0"),
                    ("oraculo_preguntas", "ALTER TABLE tareas_diarias ADD COLUMN oraculo_preguntas INTEGER DEFAULT 0"),
                ]:
                    if col not in dcols:
                        cursor.execute(sql)
                        print(f"DATABASE MIGRATED: Added '{col}' to tareas_diarias.")

                cursor.execute("PRAGMA table_info(tareas_semanales)")
                scols = [c[1] for c in cursor.fetchall()]
                for col, sql in [
                    ("impostor_partidas", "ALTER TABLE tareas_semanales ADD COLUMN impostor_partidas INTEGER DEFAULT 0"),
                    ("impostor_victorias", "ALTER TABLE tareas_semanales ADD COLUMN impostor_victorias INTEGER DEFAULT 0"),
                    ("completado_especial", "ALTER TABLE tareas_semanales ADD COLUMN completado_especial INTEGER DEFAULT 0"),
                    ("mg_ret_roll_apuesta", "ALTER TABLE tareas_semanales ADD COLUMN mg_ret_roll_apuesta INTEGER DEFAULT 0"),
                    ("mg_roll_casual", "ALTER TABLE tareas_semanales ADD COLUMN mg_roll_casual INTEGER DEFAULT 0"),
                    ("mg_duelo", "ALTER TABLE tareas_semanales ADD COLUMN mg_duelo INTEGER DEFAULT 0"),
                    ("mg_voto_dom", "ALTER TABLE tareas_semanales ADD COLUMN mg_voto_dom INTEGER DEFAULT 0"),
                    ("completado_minijuegos", "ALTER TABLE tareas_semanales ADD COLUMN completado_minijuegos INTEGER DEFAULT 0"),
                ]:
                    if col not in scols:
                        cursor.execute(sql)
                        print(f"DATABASE MIGRATED: Added '{col}' to tareas_semanales.")

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trampa_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts INTEGER NOT NULL,
                        guild_id INTEGER,
                        channel_id INTEGER,
                        attacker_id INTEGER NOT NULL,
                        target_id INTEGER,
                        carta_id INTEGER NOT NULL,
                        carta_nombre TEXT
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS temp_roles_shop (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        role_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        granted_by INTEGER NOT NULL,
                        label TEXT,
                        created_ts REAL NOT NULL,
                        expires_ts REAL NOT NULL,
                        kind TEXT DEFAULT 'shop'
                    )
                    """
                )

                cursor.execute("PRAGMA table_info(temp_roles_shop)")
                tr_cols = [c[1] for c in cursor.fetchall()]
                if "kind" not in tr_cols:
                    cursor.execute("ALTER TABLE temp_roles_shop ADD COLUMN kind TEXT DEFAULT 'shop'")
                    print("DATABASE MIGRATED: Added 'kind' to temp_roles_shop.")

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS anime_top_entries (
                        user_id INTEGER NOT NULL,
                        pos INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        updated_ts INTEGER NOT NULL,
                        PRIMARY KEY (user_id, pos),
                        FOREIGN KEY (user_id) REFERENCES economia_usuarios (user_id) ON DELETE CASCADE
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bot_meta (
                        k TEXT PRIMARY KEY,
                        v TEXT NOT NULL
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS minijuego_invite (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL,
                        guild_id INTEGER NOT NULL,
                        channel_id INTEGER NOT NULL,
                        p1_id INTEGER NOT NULL,
                        p2_id INTEGER NOT NULL,
                        stake INTEGER NOT NULL,
                        payload TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_ts REAL NOT NULL,
                        expires_ts REAL NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_wishlist_entries (
                        user_id INTEGER NOT NULL,
                        pos INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        updated_ts INTEGER NOT NULL,
                        PRIMARY KEY (user_id, pos),
                        FOREIGN KEY (user_id) REFERENCES economia_usuarios (user_id) ON DELETE CASCADE
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_anime_hated_entries (
                        user_id INTEGER NOT NULL,
                        pos INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        updated_ts INTEGER NOT NULL,
                        PRIMARY KEY (user_id, pos),
                        FOREIGN KEY (user_id) REFERENCES economia_usuarios (user_id) ON DELETE CASCADE
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_fav_char_entries (
                        user_id INTEGER NOT NULL,
                        pos INTEGER NOT NULL,
                        char_name TEXT NOT NULL,
                        anime_title TEXT NOT NULL,
                        updated_ts INTEGER NOT NULL,
                        PRIMARY KEY (user_id, pos),
                        FOREIGN KEY (user_id) REFERENCES economia_usuarios (user_id) ON DELETE CASCADE
                    )
                    """
                )

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

    def modify_blisters(self, user_id: int, blister_tipo: str, cantidad: int) -> Tuple[int, List[str]]:
        self.ensure_user_exists(user_id)
        blister_tipo = blister_tipo.lower().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO inventario_blisters (user_id, blister_tipo, cantidad) VALUES (?, ?, MAX(0, ?)) ON CONFLICT(user_id, blister_tipo) DO UPDATE SET cantidad = MAX(0, cantidad + ?)", (user_id, blister_tipo, cantidad, cantidad))
            conn.commit()
            cursor.execute("SELECT cantidad FROM inventario_blisters WHERE user_id = ? AND blister_tipo = ?", (user_id, blister_tipo))
            result = cursor.fetchone()
            out = int(result[0]) if result else 0
        bonus_msgs: List[str] = []
        if cantidad > 0:
            try:
                from cogs.economia.blister_collection_reward import try_grant_after_inventory_change

                bonus_msgs = try_grant_after_inventory_change(self, user_id)
            except Exception:
                pass
        return out, bonus_msgs

    def blister_collector_inventory_complete(self, user_id: int, types_norm: List[str], min_single: int) -> bool:
        """Si hay 2+ tipos: al menos 1 de cada. Si hay 1 solo tipo: cantidad >= min_single."""
        if not types_norm:
            return False
        rows = self.get_blisters_for_user(user_id)
        by_t = {str(r["blister_tipo"]).lower(): int(r["cantidad"] or 0) for r in rows}
        if len(types_norm) >= 2:
            return all(by_t.get(t, 0) >= 1 for t in types_norm)
        need = max(1, int(min_single))
        return by_t.get(types_norm[0], 0) >= need

    def apply_blister_collector_bonus(self, user_id: int, types: List[str], min_single: int, points: int, version: int) -> List[str]:
        """Otorga bono de colección si cumple meta y aún no reclamó esta versión."""
        if points <= 0 or not types or version < 1:
            return []
        self.ensure_user_exists(user_id)
        types_norm = [t.lower().strip() for t in types if str(t).strip()]
        if not types_norm:
            return []
        if not self.blister_collector_inventory_complete(user_id, types_norm, min_single):
            return []
        msgs: List[str] = []
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE economia_usuarios
                SET puntos_actuales = puntos_actuales + ?,
                    puntos_conseguidos = puntos_conseguidos + ?,
                    blister_collector_version_claimed = ?
                WHERE user_id = ? AND IFNULL(blister_collector_version_claimed, 0) < ?
                """,
                (points, points, version, user_id, version),
            )
            if cur.rowcount:
                msgs.append(
                    f"📦 **¡Colección de blisters completa!** +{fmt_toque_sentence(int(points))} "
                    f"(meta versión **{version}**; subí `REWARD_BLISTER_COLLECTION_VERSION` cuando agregues tipos nuevos)."
                )
            conn.commit()
        return msgs

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
            elif task_type == "semanal_especial":
                cursor.execute(
                    "UPDATE tareas_semanales SET completado_especial = 1 WHERE user_id = ? AND semana = ?",
                    (user_id, semana),
                )
            elif task_type == "semanal_minijuegos":
                cursor.execute(
                    "UPDATE tareas_semanales SET completado_minijuegos = 1 WHERE user_id = ? AND semana = ?",
                    (user_id, semana),
                )
            conn.commit()
            return cursor.rowcount > 0

    def record_impostor_game_end(self, lobby: Any, winner_role: str) -> None:
        """Cuenta partida jugada para cada humano y victoria del impostor si corresponde."""
        from cogs.impostor.engine import ROLE_IMPOSTOR

        _, semana = self.get_current_date_keys()
        imp_id = getattr(lobby, "impostor_id", None)
        for p in lobby.players.values():
            if getattr(p, "is_bot", False):
                continue
            uid = int(getattr(p, "user_id", 0))
            if not uid:
                continue
            self.ensure_user_exists(uid)
            self.update_task_semanal(uid, "impostor_partidas", semana, 1)
        if winner_role == ROLE_IMPOSTOR and imp_id:
            self.ensure_user_exists(int(imp_id))
            self.update_task_semanal(int(imp_id), "impostor_victorias", semana, 1)

    def mark_trampa_enviada(self, user_id: int) -> None:
        """Trampa dirigida a otro usuario (cuenta para diaria 'completa' en un solo uso)."""
        fecha, _ = self.get_current_date_keys()
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO tareas_diarias (user_id, fecha) VALUES (?, ?)", (user_id, fecha))
            cursor.execute(
                "UPDATE tareas_diarias SET trampa_enviada = 1 WHERE user_id = ? AND fecha = ? AND completado = 0",
                (user_id, fecha),
            )
            conn.commit()

    def bump_trampa_sin_objetivo(self, user_id: int) -> None:
        """Trampa tipo Trampa sin objetivo: suma 1; con 2 en el día equivale a la pista 'casual' de la diaria."""
        fecha, _ = self.get_current_date_keys()
        self.update_task_diaria(user_id, "trampa_sin_objetivo", fecha, 1)

    def log_trampa_uso(
        self,
        attacker_id: int,
        target_id: Optional[int],
        carta_id: int,
        carta_nombre: str,
        guild_id: Optional[int],
        channel_id: Optional[int],
    ) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trampa_audit (ts, guild_id, channel_id, attacker_id, target_id, carta_id, carta_nombre)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (int(time.time()), guild_id, channel_id, attacker_id, target_id, carta_id, carta_nombre[:200]),
            )
            conn.commit()

    def mark_minijuego_semanal(self, user_id: int, campo: str) -> None:
        """Marca un flag de minijuegos semanal (valor 1). campo whitelist."""
        allowed = {"mg_ret_roll_apuesta", "mg_roll_casual", "mg_duelo", "mg_voto_dom"}
        if campo not in allowed:
            raise ValueError("campo inválido")
        _, semana = self.get_current_date_keys()
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO tareas_semanales (user_id, semana) VALUES (?, ?)", (user_id, semana))
            cursor.execute(
                f"UPDATE tareas_semanales SET {campo} = 1 WHERE user_id = ? AND semana = ?",
                (user_id, semana),
            )
            conn.commit()

    # --- Invitaciones roll / duelo (SQLite en economia.db) ---
    def minijuego_invite_create(
        self, kind: str, guild_id: int, channel_id: int, p1: int, p2: int, stake: int, payload: str, ttl_sec: int = 300
    ) -> int:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO minijuego_invite (kind, guild_id, channel_id, p1_id, p2_id, stake, payload, status, created_ts, expires_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (kind, guild_id, channel_id, p1, p2, stake, payload, now, now + ttl_sec),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def minijuego_invite_pending_for_target(self, opponent_user_id: int) -> Optional[Dict[str, Any]]:
        """Invitación pendiente donde vos sos el retado (p2)."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM minijuego_invite
                WHERE status = 'pending' AND expires_ts > ? AND p2_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (time.time(), opponent_user_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def minijuego_invite_resolve(self, invite_id: int, new_status: str = "done") -> None:
        with self._get_connection() as conn:
            conn.cursor().execute("UPDATE minijuego_invite SET status = ? WHERE id = ?", (new_status, invite_id))
            conn.commit()

    def minijuego_fetch_expired_pending(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM minijuego_invite WHERE status = 'pending' AND expires_ts < ?",
                (time.time(),),
            )
            return [dict(r) for r in cur.fetchall()]

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
        column_name = column_map.get(ranking_type, "puntos_actuales")
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = f"SELECT user_id, {column_name} FROM economia_usuarios WHERE {column_name} > 0 ORDER BY {column_name} DESC LIMIT ?"
            cursor.execute(query, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_user_rank_info(self, user_id: int, ranking_type: str) -> Dict[str, Any]:
        """Posición (1 = mejor) según columna de ranking; `value` es el puntaje del usuario."""
        column_map = {"actual": "puntos_actuales", "conseguidos": "puntos_conseguidos", "gastados": "puntos_gastados"}
        col = column_map.get(ranking_type, "puntos_actuales")
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT {col} FROM economia_usuarios WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            val = int(row[0] or 0) if row else 0
            cur.execute(f"SELECT COUNT(*) FROM economia_usuarios WHERE {col} > ?", (val,))
            strictly_above = int(cur.fetchone()[0] or 0)
            rank = strictly_above + 1
            cur.execute(f"SELECT COUNT(*) FROM economia_usuarios WHERE {col} > 0")
            with_positive = int(cur.fetchone()[0] or 0)
        return {"value": val, "rank": rank, "with_positive": with_positive}

    def inventory_cards_totals(self, user_id: int) -> Tuple[int, int]:
        """(copias totales de cartas, cantidad de tipos distintos con stock > 0)."""
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(SUM(cantidad), 0), COUNT(*)
                FROM inventario_cartas
                WHERE user_id = ? AND cantidad > 0
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return 0, 0
            return int(row[0] or 0), int(row[1] or 0)

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

    def register_temp_shop_role(
        self,
        guild_id: int,
        role_id: int,
        user_id: int,
        granted_by: int,
        label: str,
        created_ts: float,
        expires_ts: float,
        kind: str = "shop",
    ) -> int:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO temp_roles_shop (guild_id, role_id, user_id, granted_by, label, created_ts, expires_ts, kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, role_id, user_id, granted_by, label[:200], created_ts, expires_ts, (kind or "shop")[:16]),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_expired_temp_shop_roles(self, now_ts: float) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM temp_roles_shop WHERE expires_ts <= ? ORDER BY id ASC",
                (now_ts,),
            )
            return [dict(r) for r in cur.fetchall()]

    def delete_temp_shop_role_row(self, row_id: int) -> None:
        with self._get_connection() as conn:
            conn.cursor().execute("DELETE FROM temp_roles_shop WHERE id = ?", (row_id,))
            conn.commit()

    # --- Anime top (1-30) ---
    def anime_top_list(self, user_id: int) -> List[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT pos, title FROM anime_top_entries WHERE user_id = ? ORDER BY pos ASC",
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def anime_top_count_filled(self, user_id: int, hasta: int) -> int:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM anime_top_entries
                WHERE user_id = ? AND pos BETWEEN 1 AND ? AND TRIM(title) != ''
                """,
                (user_id, hasta),
            )
            row = cur.fetchone()
            return int(row[0] or 0)

    def anime_top_set(self, user_id: int, pos: int, title: str) -> None:
        self.ensure_user_exists(user_id)
        t = (title or "").strip()[:200]
        if not t:
            raise ValueError("El título no puede estar vacío.")
        if pos < 1 or pos > 33:
            raise ValueError("La posición debe ser entre 1 y 33.")

        ts = int(time.time())
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO anime_top_entries (user_id, pos, title, updated_ts)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, pos) DO UPDATE SET title = excluded.title, updated_ts = excluded.updated_ts
                """,
                (user_id, pos, t, ts),
            )
            conn.commit()

    def anime_top_remove(self, user_id: int, pos: int) -> None:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.cursor().execute(
                "DELETE FROM anime_top_entries WHERE user_id = ? AND pos = ?",
                (user_id, pos),
            )
            conn.commit()

    def get_anime_bonus_flags(self, user_id: int) -> Dict[str, int]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT anime_bonus_top10, anime_bonus_top30 FROM economia_usuarios WHERE user_id = ?",
                (user_id,),
            )
            r = cur.fetchone()
            if not r:
                return {"anime_bonus_top10": 0, "anime_bonus_top30": 0}
            return {"anime_bonus_top10": int(r["anime_bonus_top10"] or 0), "anime_bonus_top30": int(r["anime_bonus_top30"] or 0)}

    def apply_anime_milestones(self, user_id: int, bonus_top10: int, bonus_top30: int) -> List[str]:
        """Otorga bonos una sola vez si completó top 10 / top 30. Devuelve mensajes para mostrar al usuario."""
        self.ensure_user_exists(user_id)
        msgs: List[str] = []
        c10 = self.anime_top_count_filled(user_id, 10)
        c30 = self.anime_top_count_filled(user_id, 30)
        with self._get_connection() as conn:
            cur = conn.cursor()
            if c10 >= 10 and bonus_top10 > 0:
                cur.execute(
                    """
                    UPDATE economia_usuarios
                    SET puntos_actuales = puntos_actuales + ?,
                        puntos_conseguidos = puntos_conseguidos + ?,
                        anime_bonus_top10 = 1
                    WHERE user_id = ? AND IFNULL(anime_bonus_top10, 0) = 0
                    """,
                    (bonus_top10, bonus_top10, user_id),
                )
                if cur.rowcount:
                    msgs.append(f"🎌 **¡Top 10 completo!** +{fmt_toque_sentence(int(bonus_top10))} (bono único).")
            if c30 >= 30 and bonus_top30 > 0:
                cur.execute(
                    """
                    UPDATE economia_usuarios
                    SET puntos_actuales = puntos_actuales + ?,
                        puntos_conseguidos = puntos_conseguidos + ?,
                        anime_bonus_top30 = 1
                    WHERE user_id = ? AND IFNULL(anime_bonus_top30, 0) = 0
                    """,
                    (bonus_top30, bonus_top30, user_id),
                )
                if cur.rowcount:
                    msgs.append(f"🏆 **¡Top 30 completo!** +{fmt_toque_sentence(int(bonus_top30))} (bono único).")
            if msgs:
                conn.commit()
        return msgs

    # --- Mensaje fijo guía del bot (canal BOT_GUIA_CHANNEL_ID) ---
    def bot_meta_get(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT v FROM bot_meta WHERE k = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else None

    def bot_meta_set(self, key: str, value: str) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO bot_meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                (key, value),
            )
            conn.commit()

    # --- Wishlist anime (1–30, público) ---
    def wishlist_list(self, user_id: int) -> List[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT pos, title FROM user_wishlist_entries WHERE user_id = ? ORDER BY pos ASC",
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def wishlist_total_filled(self, user_id: int) -> int:
        """Cantidad de casillas de wishlist con título (cualquier posición 1–33)."""
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM user_wishlist_entries
                WHERE user_id = ? AND TRIM(title) != ''
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return int(row[0] or 0)

    def wishlist_set(self, user_id: int, pos: int, title: str) -> None:
        self.ensure_user_exists(user_id)
        t = (title or "").strip()[:200]
        if not t:
            raise ValueError("El título no puede estar vacío.")
        if pos < 1 or pos > 33:
            raise ValueError("La posición debe ser entre 1 y 33.")
        ts = int(time.time())
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO user_wishlist_entries (user_id, pos, title, updated_ts)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, pos) DO UPDATE SET title = excluded.title, updated_ts = excluded.updated_ts
                """,
                (user_id, pos, t, ts),
            )
            conn.commit()

    def wishlist_remove(self, user_id: int, pos: int) -> None:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.cursor().execute(
                "DELETE FROM user_wishlist_entries WHERE user_id = ? AND pos = ?",
                (user_id, pos),
            )
            conn.commit()

    # --- Animes odiados (1–10) ---
    def hated_list(self, user_id: int) -> List[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT pos, title FROM user_anime_hated_entries WHERE user_id = ? ORDER BY pos ASC",
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def hated_total_filled(self, user_id: int) -> int:
        """Cantidad de animes odiados cargados (hasta 10 posiciones)."""
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM user_anime_hated_entries
                WHERE user_id = ? AND TRIM(title) != ''
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return int(row[0] or 0)

    def hated_set(self, user_id: int, pos: int, title: str) -> None:
        self.ensure_user_exists(user_id)
        t = (title or "").strip()[:200]
        if not t:
            raise ValueError("El título no puede estar vacío.")
        if pos < 1 or pos > 10:
            raise ValueError("La posición debe ser entre 1 y 10.")
        ts = int(time.time())
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO user_anime_hated_entries (user_id, pos, title, updated_ts)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, pos) DO UPDATE SET title = excluded.title, updated_ts = excluded.updated_ts
                """,
                (user_id, pos, t, ts),
            )
            conn.commit()

    def hated_remove(self, user_id: int, pos: int) -> None:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.cursor().execute(
                "DELETE FROM user_anime_hated_entries WHERE user_id = ? AND pos = ?",
                (user_id, pos),
            )
            conn.commit()

    # --- Personajes favoritos (1–10: nombre + anime) ---
    def fav_char_list(self, user_id: int) -> List[Dict[str, Any]]:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT pos, char_name, anime_title FROM user_fav_char_entries WHERE user_id = ? ORDER BY pos ASC",
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def fav_char_set(self, user_id: int, pos: int, char_name: str, anime_title: str) -> None:
        self.ensure_user_exists(user_id)
        cn = (char_name or "").strip()[:120]
        an = (anime_title or "").strip()[:200]
        if not cn or not an:
            raise ValueError("Personaje y anime no pueden estar vacíos.")
        if pos < 1 or pos > 10:
            raise ValueError("La posición debe ser entre 1 y 10.")
        ts = int(time.time())
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO user_fav_char_entries (user_id, pos, char_name, anime_title, updated_ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, pos) DO UPDATE SET
                    char_name = excluded.char_name,
                    anime_title = excluded.anime_title,
                    updated_ts = excluded.updated_ts
                """,
                (user_id, pos, cn, an, ts),
            )
            conn.commit()

    def fav_char_remove(self, user_id: int, pos: int) -> None:
        self.ensure_user_exists(user_id)
        with self._get_connection() as conn:
            conn.cursor().execute(
                "DELETE FROM user_fav_char_entries WHERE user_id = ? AND pos = ?",
                (user_id, pos),
            )
            conn.commit()