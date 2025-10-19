# cogs/impostor/core.py
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple

import discord

CATEGORY_ID = int(os.getenv("IMPOSTOR_CATEGORY_ID", "0"))
FEED_CHANNEL_ID = int(os.getenv("IMPOSTOR_FEED_CHANNEL_ID", "0"))
ADMIN_ROLE_IDS = [int(x) for x in os.getenv("IMPOSTOR_ADMIN_ROLE_IDS", "").split(",") if x.strip().isdigit()]

MAX_PLAYERS = 5
PRE_GAME_TIMEOUT_SEC = 5 * 60     # 5 minutos sin iniciar → el host puede finalizar
MIN_STAY_TO_LEAVE_SEC = 30        # debes estar 30s en el lobby antes de poder /leave

# ---------- modelos ----------
@dataclass
class Player:
    user_id: int
    display: str
    joined_ts: int = field(default_factory=lambda: int(time.time()))
    ready: bool = False
    is_bot_sim: bool = False

@dataclass
class Lobby:
    name: str
    host_id: int
    is_open: bool
    guild_id: int
    channel_id: Optional[int] = None
    created_ts: int = field(default_factory=lambda: int(time.time()))
    in_game: bool = False
    players: Dict[int, Player] = field(default_factory=dict)  # user_id -> Player
    dashboard_msg_id: Optional[int] = None

    def slots(self) -> str:
        return f"{len(self.players)}/{MAX_PLAYERS}"

# ---------- helpers ----------
def is_admin_member(member: discord.Member) -> bool:
    if member.guild is None:
        return False
    if member.guild.owner_id == member.id:
        return True
    perms = member.guild_permissions
    if perms.manage_guild or perms.administrator:
        return True
    if any(r.id in ADMIN_ROLE_IDS for r in member.roles):
        return True
    return False

# ---------- manager en memoria ----------
class LobbyManager:
    def __init__(self):
        self._lobbies: Dict[Tuple[int, str], Lobby] = {}   # (guild_id, name) -> Lobby
        self._user_to_lobby: Dict[int, Tuple[int, str]] = {}  # user_id -> (guild_id, name)

    def get(self, guild_id: int, name: str) -> Optional[Lobby]:
        return self._lobbies.get((guild_id, name))

    def by_user(self, user_id: int) -> Optional[Lobby]:
        key = self._user_to_lobby.get(user_id)
        return self._lobbies.get(key) if key else None

    def all_in_guild(self, guild_id: int) -> List[Lobby]:
        # La cartelera usa esto; más abajo añadimos una bandera oculta para lobbies finalizados
        return [lob for (gid, _), lob in self._lobbies.items() if gid == guild_id and not lob.in_game]

    def register(self, lobby: Lobby):
        self._lobbies[(lobby.guild_id, lobby.name)] = lobby

    def add_user(self, lobby: Lobby, member: discord.Member) -> bool:
        if member.id in self._user_to_lobby:
            return False
        if len(lobby.players) >= MAX_PLAYERS:
            return False
        lobby.players[member.id] = Player(member.id, member.display_name, is_bot_sim=False)
        self._user_to_lobby[member.id] = (lobby.guild_id, lobby.name)
        return True

    def add_sim_bot(self, lobby: Lobby) -> int:
        if len(lobby.players) >= MAX_PLAYERS:
            return 0
        uid = -int(time.time() * 1000) % 1000000000
        while uid in lobby.players or uid in self._user_to_lobby:
            uid -= 1
        display = f"AAT-Bot#{sum(1 for p in lobby.players.values() if p.is_bot_sim) + 1}"
        lobby.players[uid] = Player(user_id=uid, display=display, ready=True, is_bot_sim=True)
        return uid

    def remove_user(self, guild_id: int, user_id: int) -> Optional[Lobby]:
        key = self._user_to_lobby.pop(user_id, None)
        lob = None
        if key:
            lob = self._lobbies.get(key)
        else:
            for (gid, _name), l in self._lobbies.items():
                if gid == guild_id and user_id in l.players:
                    lob = l
                    break
        if not lob:
            return None
        lob.players.pop(user_id, None)
        return lob

    def leave_allowed(self, user_id: int) -> bool:
        lob = self.by_user(user_id)
        if not lob:
            return False
        p = lob.players.get(user_id)
        if not p:
            return False
        return (int(time.time()) - p.joined_ts) >= MIN_STAY_TO_LEAVE_SEC

    def delete_if_empty(self, guild_id: int, name: str):
        lob = self._lobbies.get((guild_id, name))
        if not lob:
            return
        if len([p for p in lob.players.values() if not p.is_bot_sim]) == 0:
            self._lobbies.pop((guild_id, name), None)

    # ---- NUEVO: liberar jugadores tras finalizar la partida ----
    def release_players(self, lobby: Lobby):
        """
        Quita el mapping user->lobby para TODOS los humanos del lobby,
        así pueden unirse a otro lobby aun si mantienen acceso de lectura al canal.
        """
        for uid, p in list(lobby.players.items()):
            if not p.is_bot_sim:
                self._user_to_lobby.pop(uid, None)

# instancia global del manager
manager = LobbyManager()
