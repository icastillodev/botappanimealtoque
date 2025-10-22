# cogs/impostor/game_core.py

import os
import discord
from discord.ext import commands
import logging
import random
from typing import Optional

# Importaciones locales
from . import core
from .engine import GameState, ROLE_IMPOSTOR, ROLE_SOCIAL, PHASE_ROLES, PHASE_TURNS, PHASE_VOTE, PHASE_END # Añadido PHASE_VOTE
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
            log.error(f"[StartGame C:{lobby.channel_id}] Canal no encontrado.")
            # Intentar limpiar si el canal no existe
            core.remove_lobby(lobby.channel_id)
            await feed.update_feed(self.bot)
            return

        log.debug(f"[StartGame C:{lobby.channel_id}] Adquiriendo lock...")
        async with lobby._lock:
            log.debug(f"[StartGame C:{lobby.channel_id}] Lock adquirido.")
            # Doble check de fase por si acaso
            if lobby.phase != PHASE_ROLES:
                log.warning(f"[StartGame C:{lobby.channel_id}] Fase incorrecta ({lobby.phase}). Saliendo.")
                return

            log.info(f"[StartGame C:{lobby.channel_id}] Iniciando partida. Lobby: {lobby.lobby_name}")

            # 1. Obtener personaje
            log.debug(f"[StartGame C:{lobby.channel_id}] Obteniendo personaje...")
            try:
                char = await chars.get_random_character()
                lobby.character_name = char['name']
                lobby.character_slug = char['slug']
                log.debug(f"[StartGame C:{lobby.channel_id}] Personaje: {lobby.character_name}")
            except Exception as e:
                log.exception(f"[StartGame C:{lobby.channel_id}] ERROR al obtener personaje: {e}")
                lobby.character_name = "Error Personaje"
                lobby.character_slug = "error"
            
            # 2. Asignar Impostor
            log.debug(f"[StartGame C:{lobby.channel_id}] Asignando impostor...")
            human_players = lobby.human_players
            if not human_players:
                log.error(f"[StartGame C:{lobby.channel_id}] ¡No hay humanos!")
                await channel.send("❌ No hay jugadores humanos. No se puede empezar.")
                # Resetear lobby (marcar como no en progreso y fase idle)
                lobby.in_progress = False
                lobby.phase = PHASE_IDLE
                await feed.update_feed(self.bot)
                await core.queue_hud_update(lobby.channel_id) # Usar queue_hud_update de lobby.py
                return
                
            impostor_player = random.choice(human_players)
            lobby.impostor_id = impostor_player.user_id
            log.info(f"[StartGame C:{lobby.channel_id}] Impostor elegido: {lobby.impostor_id}")
            
            # 3. Asignar roles y resetear estado
            log.debug(f"[StartGame C:{lobby.channel_id}] Asignando roles a jugadores...")
            for player in lobby.players.values():
                player.alive = True
                player.word = None
                player.voted_for = None
                player.role = ROLE_IMPOSTOR if player.user_id == lobby.impostor_id else ROLE_SOCIAL
                player.ready_after_roles = player.is_bot # Bots siempre listos
            log.debug(f"[StartGame C:{lobby.channel_id}] Roles asignados.")

        # --- Lock liberado ---
        log.debug(f"[StartGame C:{lobby.channel_id}] Lock liberado.")

        # 4. Limpiar mensajes (FUERA del lock)
        log.debug(f"[StartGame C:{lobby.channel_id}] Limpiando mensajes del canal...")
        try:
            # No borrar el HUD si existe
            purge_check = lambda m: m.id != lobby.hud_message_id if lobby.hud_message_id else True
            await channel.purge(limit=100, check=purge_check)
            log.debug(f"[StartGame C:{lobby.channel_id}] Mensajes limpiados.")
        except (discord.Forbidden, discord.HTTPException):
            log.warning(f"[StartGame C:{lobby.channel_id}] No se pudo limpiar el canal.")

        # 5. Llamar al Cog 'roles' (FUERA del lock)
        log.debug(f"[StartGame C:{lobby.channel_id}] Llamando a roles_cog.send_role_assignment_ui...")
        roles_cog = self.bot.get_cog("ImpostorRoles")
        if not roles_cog:
            log.error(f"[StartGame C:{lobby.channel_id}] FATAL: No se encontró ImpostorRoles.")
            await channel.send("❌ ERROR FATAL: Módulo 'roles' no cargado.")
            # Intentar resetear
            async with lobby._lock: lobby.in_progress = False; lobby.phase = PHASE_IDLE
            await feed.update_feed(self.bot)
            return
        
        await roles_cog.send_role_assignment_ui(lobby)
        log.debug(f"[StartGame C:{lobby.channel_id}] start_game finalizado.")


    async def start_round(self, lobby: GameState):
        """
        Inicia una nueva ronda de turnos O finaliza el juego si se cumplen condiciones.
        Llamada por 'roles.py' (Ronda 1) o 'votes.py' (Rondas 2+).
        """
        channel = self.bot.get_channel(lobby.channel_id)
        if not channel:
            log.error(f"[StartRound C:{lobby.channel_id}] Canal no encontrado para ronda {lobby.round_num}.")
            core.remove_lobby(lobby.channel_id) # Limpiar si no hay canal
            await feed.update_feed(self.bot)
            return

        endgame_cog = self.bot.get_cog("ImpostorEndgame")
        if not endgame_cog:
            log.error(f"[StartRound C:{lobby.channel_id}] FATAL: No se encontró ImpostorEndgame.")
            await channel.send("❌ ERROR FATAL: Módulo 'endgame' no cargado.")
            # Intentar resetear
            async with lobby._lock: lobby.in_progress = False; lobby.phase = PHASE_IDLE
            await feed.update_feed(self.bot)
            return

        # --- Variables para decidir qué hacer DESPUÉS del lock ---
        should_end_game = False
        winner_role_for_endgame = None
        reason_for_endgame = None
        should_start_turns = False 

        log.debug(f"[StartRound C:{lobby.channel_id}] Adquiriendo lock para ronda {lobby.round_num}...")
        async with lobby._lock:
            log.debug(f"[StartRound C:{lobby.channel_id}] Lock adquirido.")
            # Doble check por si acaso
            if lobby.phase == PHASE_END:
                log.warning(f"[StartRound C:{lobby.channel_id}] Partida ya terminó. Saliendo.")
                return # Salir si ya terminó

            log.info(f"[StartRound C:{lobby.channel_id}] Verificando condiciones para Ronda {lobby.round_num}")
            
            # --- 1. Chequear condiciones de victoria ANTES de empezar ---
            alive_players = lobby.alive_players
            impostor = lobby.get_player(lobby.impostor_id) if lobby.impostor_id else None # Asegurar que impostor_id existe

            # Condición 1: Impostor único vivo (Improbable si los bots se votan a sí mismos)
            if impostor and impostor.alive and len(alive_players) == 1:
                log.info(f"[StartRound C:{lobby.channel_id}] Condición: Impostor único vivo.")
                should_end_game = True
                winner_role_for_endgame = ROLE_IMPOSTOR
                reason_for_endgame = "El Impostor es el único superviviente."

            # Condición 2: Quedan 2 jugadores vivos Y el impostor está vivo
            elif impostor and impostor.alive and len(alive_players) <= 2:
                log.info(f"[StartRound C:{lobby.channel_id}] Condición: 2 vivos (Impostor gana).")
                should_end_game = True
                winner_role_for_endgame = ROLE_IMPOSTOR
                reason_for_endgame = "Quedan solo 2 jugadores. El Impostor gana."
            
            # Condición 3: Se alcanzó el límite de rondas Y el impostor sigue vivo
            max_rounds = get_max_rounds()
            # Usar >= para que la ronda MAX_ROUNDS se juegue y GANE al final de ella si no lo pillan
            if not should_end_game and lobby.round_num > max_rounds: 
                 # Solo si el impostor sigue vivo
                 if impostor and impostor.alive:
                      log.info(f"[StartRound C:{lobby.channel_id}] Condición: Límite de rondas alcanzado.")
                      should_end_game = True
                      winner_role_for_endgame = ROLE_IMPOSTOR
                      reason_for_endgame = f"Se alcanzó el límite de {max_rounds} rondas. El Impostor gana."
                 else:
                      # Si se alcanzó el límite pero el impostor MURIÓ antes, ganan sociales
                      # (Esto debería haber sido detectado por votes.py, pero por seguridad)
                      log.info(f"[StartRound C:{lobby.channel_id}] Condición: Límite rondas, pero impostor muerto.")
                      should_end_game = True
                      winner_role_for_endgame = ROLE_SOCIAL
                      reason_for_endgame = f"Se alcanzó el límite de {max_rounds} rondas y el Impostor fue eliminado."


            # --- 2. Si no hay victoria, preparar e indicar inicio de ronda ---
            if not should_end_game:
                log.info(f"[StartRound C:{lobby.channel_id}] No hay condición de victoria. Preparando Ronda {lobby.round_num}.")
                lobby.phase = PHASE_TURNS
                lobby.reset_turn_state() # Limpia palabras
                lobby.reset_vote_state() # Limpia votos
                should_start_turns = True
            
        # --- Lock liberado ---
        log.debug(f"[StartRound C:{lobby.channel_id}] Lock liberado.")

        # --- 3. Llamar a Endgame O a Turns FUERA del lock ---
        if should_end_game:
            log.info(f"[StartRound C:{lobby.channel_id}] Llamando a trigger_end_game...")
            await endgame_cog.trigger_end_game(lobby, winner_role_for_endgame, reason_for_endgame)
        
        elif should_start_turns:
            log.info(f"[StartRound C:{lobby.channel_id}] Llamando a turns_cog.start_turn_phase...")
            turns_cog = self.bot.get_cog("ImpostorTurns")
            if not turns_cog:
                log.error(f"[StartRound C:{lobby.channel_id}] FATAL: No se encontró ImpostorTurns.")
                await channel.send("❌ ERROR FATAL: Módulo 'turns' no cargado.")
                # Intentar resetear
                async with lobby._lock: lobby.in_progress = False; lobby.phase = PHASE_IDLE
                await feed.update_feed(self.bot)
                return
            await turns_cog.start_turn_phase(lobby)
        
        # Si no es ni should_end_game ni should_start_turns, algo raro pasó (quizás ya estaba en PHASE_END al inicio)
        # No hacemos nada en ese caso.
        log.debug(f"[StartRound C:{lobby.channel_id}] start_round finalizado.")


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorGameCore(bot))