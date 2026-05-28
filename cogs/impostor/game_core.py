# cogs/impostor/game_core.py

import os
import time
import discord
from discord.ext import commands
import logging
import random
from typing import Optional

# Importaciones locales
from . import core
from . import feed
from . import lobby as lobby_cog
from .engine import GameState, ROLE_IMPOSTOR, ROLE_SOCIAL, PHASE_ROLES, PHASE_TURNS, PHASE_VOTE, PHASE_END
from . import chars
from . import rules

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
            lobby.match_started_at_ts = time.time()

            # 1. Secreto + temática (personaje / anime / objeto)
            log.debug(f"[StartGame C:{lobby.channel_id}] Obteniendo secreto...")
            try:
                sec = await chars.get_random_secret()
                lobby.character_name = sec['name']
                lobby.character_slug = sec['slug']
                lobby.secret_theme = sec['theme']
                lobby.character_anime = sec.get("anime")
                lobby.secret_detalle = sec.get("detalle")
                log.debug(f"[StartGame C:{lobby.channel_id}] Secreto: {lobby.character_name} ({lobby.secret_theme})")
            except Exception as e:
                log.exception(f"[StartGame C:{lobby.channel_id}] ERROR al obtener secreto: {e}")
                lobby.character_name = "Error Personaje"
                lobby.character_slug = "error"
                lobby.secret_theme = "personaje"
                lobby.character_anime = None
            
            # 2. Asignar impostor(es)
            log.debug(f"[StartGame C:{lobby.channel_id}] Asignando impostores...")
            human_players = lobby.human_players
            if not human_players:
                log.error(f"[StartGame C:{lobby.channel_id}] ¡No hay humanos!")
                await channel.send("❌ No hay jugadores humanos. No se puede empezar.")
                lobby.in_progress = False
                lobby.phase = PHASE_IDLE
                await feed.update_feed(self.bot)
                await lobby_cog.queue_hud_update(lobby.channel_id)
                return

            imp_n = rules.clamp_impostor_count(lobby)
            human_ids = [p.user_id for p in human_players]
            if imp_n > len(human_ids):
                imp_n = len(human_ids)
            lobby.impostor_ids = set(random.sample(human_ids, k=imp_n))
            log.info(f"[StartGame C:{lobby.channel_id}] Impostores: {lobby.impostor_ids}")

            # 3. Asignar roles y resetear estado
            log.debug(f"[StartGame C:{lobby.channel_id}] Asignando roles a jugadores...")
            for player in lobby.players.values():
                player.alive = True
                player.word = None
                player.voted_for = None
                player.role = (
                    ROLE_IMPOSTOR if player.user_id in lobby.impostor_ids else ROLE_SOCIAL
                )
                player.ready_after_roles = player.is_bot
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
        
        imp_n = len(lobby.impostor_ids)
        total = lobby.all_players_count
        soc_n = max(0, total - imp_n)
        await channel.send(
            f"📋 **Reparto:** **{imp_n}** impostor(es) · **{soc_n}** social(es) · **{total}** jugadores.\n"
            f"**Ganan los sociales** si expulsan a **todos** los impostores.\n"
            f"**Ganan los impostores** si quedan en pie y solo hay **2 sociales o menos** vivos, "
            f"o si llegan al límite de rondas sin ser descubiertos."
        )
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
            victory = rules.check_round_start_victory(lobby)
            if victory:
                should_end_game = True
                winner_role_for_endgame, reason_for_endgame = victory
            else:
                max_rounds = get_max_rounds()
                alive_imps = rules.alive_impostor_players(lobby)
                if lobby.round_num > max_rounds:
                    if alive_imps:
                        should_end_game = True
                        winner_role_for_endgame = ROLE_IMPOSTOR
                        reason_for_endgame = (
                            f"Se alcanzó el límite de {max_rounds} rondas. "
                            f"Los impostores sobreviven."
                        )
                    else:
                        should_end_game = True
                        winner_role_for_endgame = ROLE_SOCIAL
                        reason_for_endgame = (
                            f"Se alcanzó el límite de {max_rounds} rondas y "
                            f"no quedan impostores."
                        )


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