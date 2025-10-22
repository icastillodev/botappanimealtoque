# cogs/impostor/core.py

import logging
from typing import Dict, Optional, List, Set
from .engine import GameState

log = logging.getLogger(__name__)

# --- Registros Globales en Memoria ---

# El registro principal de lobbies. La clave es el ID del canal del lobby.
_LOBBIES: Dict[int, GameState] = {}

# Un mapa de búsqueda inversa para encontrar en qué lobby está un usuario.
# La clave es el user_id, el valor es el channel_id de su lobby.
_USER_LOBBY_MAP: Dict[int, int] = {}


# --- Funciones de Gestión del Registro ---

def create_lobby(
    guild_id: int,
    channel_id: int,
    host_id: int,
    lobby_name: str,
    is_open: bool = True
) -> GameState:
    """
    Crea un nuevo GameState (lobby), lo registra y lo devuelve.
    """
    if channel_id in _LOBBIES:
        log.warning(f"Se intentó crear un lobby que ya existe: {channel_id}")
        return _LOBBIES[channel_id]

    # Crear la nueva instancia de GameState
    lobby = GameState(
        lobby_name=lobby_name,
        guild_id=guild_id,
        channel_id=channel_id,
        host_id=host_id,
        is_open=is_open
    )
    
    # Registrar el lobby
    _LOBBIES[channel_id] = lobby
    
    # Agregar al host al mapa de usuarios
    _USER_LOBBY_MAP[host_id] = channel_id
    
    # Agregar al host a la lista de jugadores del lobby
    lobby.add_player(host_id, is_bot=False)
    
    log.info(f"Lobby creado: {lobby_name} (Canal: {channel_id}) por Host: {host_id}")
    return lobby


def get_lobby_by_channel(channel_id: int) -> Optional[GameState]:
    """Obtiene un lobby usando el ID de su canal."""
    return _LOBBIES.get(channel_id)


def get_lobby_by_user(user_id: int) -> Optional[GameState]:
    """Encuentra el lobby en el que está un usuario."""
    channel_id = _USER_LOBBY_MAP.get(user_id)
    if channel_id:
        return get_lobby_by_channel(channel_id)
    return None


def get_all_lobbies() -> List[GameState]:
    """Devuelve una lista de todos los lobbies activos."""
    return list(_LOBBIES.values())


def add_user_to_lobby(user_id: int, channel_id: int) -> Optional[GameState]:
    """Agrega un usuario a un lobby existente."""
    lobby = get_lobby_by_channel(channel_id)
    if not lobby:
        log.warning(f"Intento de unirse a lobby inexistente: C:{channel_id} U:{user_id}")
        return None
        
    if user_id in _USER_LOBBY_MAP:
        log.warning(f"Usuario {user_id} ya está en un lobby (C:{_USER_LOBBY_MAP[user_id]}), no puede unirse a C:{channel_id}")
        return None # El usuario ya está en otro lobby

    # Agregar jugador al GameState y al mapa de búsqueda
    lobby.add_player(user_id, is_bot=False)
    _USER_LOBBY_MAP[user_id] = channel_id
    log.debug(f"Usuario {user_id} agregado a lobby C:{channel_id}")
    return lobby


def remove_user_from_lobby(user_id: int) -> Optional[GameState]:
    """Quita a un usuario de cualquier lobby en el que esté."""
    lobby = get_lobby_by_user(user_id)
    if not lobby:
        log.debug(f"Usuario {user_id} intentó salir pero no estaba en ningún lobby.")
        return None

    # Quitar del mapa de búsqueda
    _USER_LOBBY_MAP.pop(user_id, None)
    
    # Quitar del GameState
    lobby.remove_player(user_id)
    log.debug(f"Usuario {user_id} quitado del lobby C:{lobby.channel_id}")
    
    return lobby
    

def remove_lobby(channel_id: int) -> Optional[GameState]:
    """
    Elimina un lobby del registro y limpia a todos sus jugadores
    del mapa de búsqueda.
    """
    lobby = _LOBBIES.pop(channel_id, None)
    if not lobby:
        log.debug(f"Se intentó borrar un lobby inexistente: C:{channel_id}")
        return None

    # Limpiar a todos los jugadores de este lobby del mapa de búsqueda
    player_ids = lobby.get_player_ids()
    for user_id in player_ids:
        # Solo lo borramos si el mapa apunta a ESTE lobby
        if _USER_LOBBY_MAP.get(user_id) == channel_id:
            _USER_LOBBY_MAP.pop(user_id, None)
            
    log.info(f"Lobby C:{channel_id} (Nombre: {lobby.lobby_name}) eliminado y limpiado.")
    return lobby


def get_all_lobby_user_ids() -> Set[int]:
    """Devuelve un Set de todos los user_id que están en algún lobby."""
    return set(_USER_LOBBY_MAP.keys())


def clear_all_lobbies():
    """Limpia todos los lobbies y usuarios. Usado para /cleanimpostor."""
    _LOBBIES.clear()
    _USER_LOBBY_MAP.clear()
    log.info("Todos los lobbies y mapas de usuarios han sido limpiados.")