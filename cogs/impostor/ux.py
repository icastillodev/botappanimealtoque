# cogs/impostor/ux.py
import time
from typing import Dict, Tuple

# Ventana (segundos) para permitir /revancha tras finalizar
REMATCH_WINDOW_SEC = 60

# (guild_id, lobby_name) -> timestamp de fin
_recent_finishes: Dict[Tuple[int, str], int] = {}

def mark_game_finished_for_rematch(guild_id: int, lobby_name: str) -> None:
    """Marcar que una partida terminó ahora; habilita /revancha por REMATCH_WINDOW_SEC."""
    _recent_finishes[(guild_id, lobby_name)] = int(time.time())

def can_rematch(guild_id: int, lobby_name: str) -> bool:
    """¿Sigue vigente la ventana de revancha?"""
    ts = _recent_finishes.get((guild_id, lobby_name))
    if ts is None:
        return False
    return (int(time.time()) - ts) <= REMATCH_WINDOW_SEC

def clear_rematch(guild_id: int, lobby_name: str) -> None:
    """Borra la marca de revancha (opcional)."""
    _recent_finishes.pop((guild_id, lobby_name), None)
