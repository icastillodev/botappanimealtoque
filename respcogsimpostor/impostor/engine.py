# cogs/impostor/engine.py

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

# Constantes de roles
ROLE_IMPOSTOR = "IMPOSTOR"
ROLE_SOCIAL = "SOCIAL"

# Constantes de fases
PHASE_IDLE = "idle"    # En lobby, antes de empezar
PHASE_ROLES = "roles"  # Repartiendo roles, esperando "Listo"
PHASE_TURNS = "turns"  # Ronda de palabras
PHASE_VOTE = "vote"    # Votación
PHASE_END = "end"      # Fin de partida, mostrando resultados

@dataclass
class GameState:
    """
    Representa el estado completo de un lobby y la partida en curso.
    Esta clase combina el estado del lobby (antes de jugar) y el 
    estado del juego (durante la partida).
    """

    # --- Estado del Lobby ---
    lobby_name: str
    guild_id: int
    channel_id: int
    host_id: int
    is_open: bool = True
    hud_message_id: Optional[int] = None
    feed_message_id: Optional[int] = None # ID del mensaje en el canal feed
    
    # --- Estado del Juego ---
    in_progress: bool = False
    phase: str = field(default=PHASE_IDLE)
    round_num: int = 0
    
    # --- Personaje (para Sociales) ---
    character_name: Optional[str] = None
    character_slug: Optional[str] = None

    # --- Jugadores ---
    @dataclass
    class Player:
        user_id: int
        is_bot: bool = False
        
        # Estado de Lobby
        ready_in_lobby: bool = False # ¿Está listo para empezar?
        
        # Estado de Partida
        role: Optional[str] = None   # ROLE_IMPOSTOR | ROLE_SOCIAL
        alive: bool = True
        word: Optional[str] = None   # Pista de la ronda actual
        voted_for: Optional[int] = None
        ready_after_roles: bool = False # ¿Vio su rol y está listo?

    # Diccionario de jugadores: {user_id: Player}
    players: Dict[int, Player] = field(default_factory=dict)
    
    # --- Estado de Partida (Impostor y Turnos) ---
    impostor_id: Optional[int] = None
    alive_order: List[int] = field(default_factory=list) # Orden de turnos
    current_turn_idx: int = -1
    votes_open: bool = False
    
    # Tareas y Bloqueo
    # (init=False) significa que no se pasan al __init__
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    
    # Tareas para manejar timeouts
    _role_task: Optional[asyncio.Task] = None
    _turn_task: Optional[asyncio.Task] = None
    _vote_task: Optional[asyncio.Task] = None
    _endgame_task: Optional[asyncio.Task] = None # Tarea para el cierre post-partida

    
    # --- Métodos de Ayuda (Helpers) ---

    def get_player(self, user_id: int) -> Optional[Player]:
        return self.players.get(user_id)

    def add_player(self, user_id: int, is_bot: bool = False) -> Player:
        """Agrega un jugador al lobby, o lo devuelve si ya existe."""
        if user_id in self.players:
            return self.players[user_id]
        
        # Los bots siempre están listos
        is_ready = is_bot
        player = self.Player(
            user_id=user_id, 
            is_bot=is_bot, 
            ready_in_lobby=is_ready
        )
        self.players[user_id] = player
        return player

    def remove_player(self, user_id: int) -> Optional[Player]:
        """Quita un jugador del lobby."""
        return self.players.pop(user_id, None)

    @property
    def human_players(self) -> List[Player]:
        return [p for p in self.players.values() if not p.is_bot]

    @property
    def bot_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.is_bot]
    
    @property
    def alive_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.alive]

    @property
    def human_alive_players(self) -> List[Player]: # <-- CORREGIDO (con indentación)
        return [p for p in self.players.values() if not p.is_bot and p.alive]
    
    @property
    def human_player_ids(self) -> Set[int]:
        return {p.user_id for p in self.players.values() if not p.is_bot}

    @property
    def all_players_count(self) -> int:
        return len(self.players)

    @property
    def all_humans_ready_in_lobby(self) -> bool:
        """Verifica si todos los humanos en el lobby están 'Ready'."""
        humans = self.human_players
        if not humans:
            return False # No se puede empezar sin humanos
        return all(p.ready_in_lobby for p in humans)
    
    @property
    def all_humans_ready_after_roles(self) -> bool:
        """Verifica si todos los humanos vieron su rol y están listos."""
        humans = self.human_players
        if not humans:
            return True # Si no hay humanos, están "listos"
        return all(p.ready_after_roles for p in humans)

    def get_votes(self) -> Dict[int, int]:
        """Cuenta los votos. Devuelve {user_id_votado: conteo}."""
        counts = {}
        # Contar votos de humanos vivos
        for voter in self.human_alive_players:
            if voter.voted_for:
                target_id = voter.voted_for
                counts[target_id] = counts.get(target_id, 0) + 1
        
        # Bots se votan a sí mismos (como pide el prompt)
        for bot in self.bot_players:
            if bot.alive:
                counts[bot.user_id] = counts.get(bot.user_id, 0) + 1
                
        return counts

    def reset_turn_state(self):
        """Limpia las palabras de la ronda anterior."""
        for player in self.players.values():
            player.word = None

    def reset_vote_state(self):
        """Limpia los votos de la ronda anterior."""
        self.votes_open = False
        for player in self.players.values():
            player.voted_for = None
            
    def get_player_ids(self) -> Set[int]:
        """Devuelve un set de todos los user_id en el lobby."""
        return set(self.players.keys())