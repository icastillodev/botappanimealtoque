# cogs/impostor/game_core.py

import os
import discord
from discord.ext import commands
import logging
import random
from typing import Optional

# Importaciones locales
from . import core
from .engine import GameState, ROLE_IMPOSTOR, ROLE_SOCIAL, PHASE_ROLES, PHASE_TURNS, PHASE_END
from . import chars

log = logging.getLogger(__name__)

# --- Configuración ---

def get_max_rounds() -> int:
    val = os.getenv("IMPOSTOR_MAX_ROUNDS", "4")
    return int(val)

# --- Cog Principal ---

class ImpostorGameCore(commands.Cog, name="ImpostorGameCore"):
    """
    Coordina el inicio de la partida, la asignación de roles y 
    el avance entre rondas y fases.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def start_game(self, lobby: GameState):
        """
        Función central para iniciar una nueva partida.
        Llamada por el botón 'imp:start' en lobby.py.
        """
        channel = self.bot.get_channel(lobby.channel_id)
        if not channel:
            log.error(f"No se pudo encontrar C:{lobby.channel_id} para iniciar la partida.")
            return

        async with lobby._lock:
            if lobby.phase != PHASE_ROLES:
                log.warning(f"Se intentó iniciar una partida en C:{lobby.channel_id} que no estaba en fase ROLES.")
                return

            log.info(f"Iniciando partida en lobby {lobby.lobby_name} (C:{lobby.channel_id}). Asignando roles...")

            # 1. Obtener el personaje para los Sociales
            try:
                char = await chars.get_random_character()
                lobby.character_name = char['name']
                lobby.character_slug = char['slug']
            except Exception as e:
                log.exception(f"Error al obtener personaje. Usando fallback de emergencia: {e}")
                lobby.character_name = "Personaje Desconocido"
                lobby.character_slug = "error"
            
            # 2. Asignar Impostor (solo entre humanos)
            human_players = lobby.human_players
            if not human_players:
                log.error(f"No hay humanos en C:{lobby.channel_id} para empezar partida.")
                await channel.send("❌ No hay jugadores humanos. No se puede empezar.")
                # TODO: Resetear lobby
                return
                
            impostor_player = random.choice(human_players)
            lobby.impostor_id = impostor_player.user_id
            log.info(f"El impostor es: {impostor_player.user_id}")
            
            # 3. Asignar roles y resetear estado de jugadores
            for player in lobby.players.values():
                player.alive = True
                player.word = None
                player.voted_for = None
                
                if player.user_id == lobby.impostor_id:
                    player.role = ROLE_IMPOSTOR
                else:
                    player.role = ROLE_SOCIAL
                
                # Resetear 'listo'
                if player.is_bot:
                    player.ready_after_roles = True
                else:
                    player.ready_after_roles = False
            
            # 4. Limpiar mensajes anteriores del canal (excepto el HUD)
            try:
                await channel.purge(limit=100, check=lambda m: m.id != lobby.hud_message_id)
            except (discord.Forbidden, discord.HTTPException):
                log.warning(f"No se pudo limpiar el canal C:{lobby.channel_id}")

            # 5. Llamar al Cog 'roles' para que envíe la UI
            roles_cog = self.bot.get_cog("ImpostorRoles")
            if not roles_cog:
                log.error(f"FATAL: No se pudo encontrar 'ImpostorRoles' en C:{lobby.channel_id}")
                await channel.send("❌ ERROR FATAL: El módulo 'roles' no está cargado. La partida no puede continuar.")
                return
            
            # Esta función enviará los botones "Ver mi rol" y "Listo"
            await roles_cog.send_role_assignment_ui(lobby)

    async def start_round(self, lobby: GameState):
        """
        Inicia una nueva ronda de turnos.
        Llamada por 'roles.py' (Ronda 1) o 'votes.py' (Rondas 2+).
        """
        channel = self.bot.get_channel(lobby.channel_id)
        if not channel:
            log.error(f"No se pudo encontrar C:{lobby.channel_id} para iniciar ronda {lobby.round_num}")
            return

        endgame_cog = self.bot.get_cog("ImpostorEndgame")
        if not endgame_cog:
            log.error(f"FATAL: No se pudo encontrar 'ImpostorEndgame' en C:{lobby.channel_id}")
            return # No podemos terminar la partida

        async with lobby._lock:
            if lobby.phase == PHASE_END:
                log.info(f"Se intentó iniciar una ronda en C:{lobby.channel_id}, pero la partida ya terminó.")
                return

            log.info(f"Iniciando Ronda {lobby.round_num} en C:{lobby.channel_id}")
            
            # --- 1. Chequear condiciones de victoria ANTES de empezar ---
            
            alive_players = lobby.alive_players
            impostor = lobby.get_player(lobby.impostor_id)

            # Condición 1: Impostor es el único vivo (improbable, pero seguro)
            if len(alive_players) == 1 and impostor.alive:
                log.info(f"Fin de partida (Impostor único vivo) en C:{lobby.channel_id}")
                await endgame_cog.trigger_end_game(lobby, ROLE_IMPOSTOR, "El Impostor es el único superviviente.")
                return

            # Condición 2: Quedan 2 jugadores vivos (Impostor + 1 Social)
            if len(alive_players) <= 2 and impostor.alive:
                log.info(f"Fin de partida (2 vivos) en C:{lobby.channel_id}")
                await endgame_cog.trigger_end_game(lobby, ROLE_IMPOSTOR, "Quedan solo 2 jugadores. El Impostor gana.")
                return
            
            # Condición 3: Se alcanzó el límite de rondas
            max_rounds = get_max_rounds()
            if lobby.round_num > max_rounds:
                log.info(f"Fin de partida (Límite de rondas) en C:{lobby.channel_id}")
                await endgame_cog.trigger_end_game(lobby, ROLE_IMPOSTOR, f"Se alcanzó el límite de {max_rounds} rondas. El Impostor gana.")
                return

            # --- 2. Si no hay victoria, preparar e iniciar la ronda ---
            
            lobby.phase = PHASE_TURNS
            lobby.reset_turn_state()
            lobby.reset_vote_state()
            
            # 3. Llamar al Cog 'turns' para que maneje la fase de palabras
            turns_cog = self.bot.get_cog("ImpostorTurns")
            if not turns_cog:
                log.error(f"FATAL: No se pudo encontrar 'ImpostorTurns' en C:{lobby.channel_id}")
                await channel.send("❌ ERROR FATAL: El módulo 'turns' no está cargado. La partida no puede continuar.")
                return

            await turns_cog.start_turn_phase(lobby)


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorGameCore(bot))