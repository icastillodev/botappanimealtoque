# cogs/impostor/endgame.py

import os
import discord
from discord.ext import commands
import logging
import asyncio
from typing import Optional

# Importaciones locales
from . import core
from .engine import GameState, PHASE_END, ROLE_IMPOSTOR, ROLE_SOCIAL
from . import feed 

log = logging.getLogger(__name__)

# --- Configuración ---

def get_rematch_window_seconds() -> int:
    val = os.getenv("IMPOSTOR_REMATCH_WINDOW_SECONDS", "60")
    return int(val)

# --- View de Fin de Partida ---

class EndgameView(discord.ui.View):
    """Vista persistente con el botón 'Salir del lobby'."""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None) 
        self.bot = bot

    @discord.ui.button(label="Salir del lobby", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="imp:leave_now")
    async def leave_now_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Saca al jugador del lobby y gestiona la limpieza del canal."""
        await interaction.response.defer(ephemeral=True) 

        lobby_cog = self.bot.get_cog("ImpostorLobby")
        if not lobby_cog:
            log.error(f"FATAL: No se pudo encontrar 'ImpostorLobby' para manejar la salida en C:{interaction.channel_id}")
            return await interaction.followup.send("❌ Error: Módulo de Lobby no cargado.", ephemeral=True)
            
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.followup.send("Has salido (el lobby ya no existía).", ephemeral=True)

        await lobby_cog.handle_leave_logic(interaction.user, lobby)
        await interaction.followup.send("Has salido del lobby.", ephemeral=True)


# --- Cog: Lógica de Fin de Partida ---

class ImpostorEndgameCog(commands.Cog, name="ImpostorEndgame"):
    """Gestiona el final de la partida, el anuncio de ganadores y la limpieza."""
    _view_registered = False

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not ImpostorEndgameCog._view_registered:
            bot.add_view(EndgameView(self.bot))
            ImpostorEndgameCog._view_registered = True
            log.info("Vista 'EndgameView' registrada persistentemente.")

    # --- Función _lock_channel FUE ELIMINADA ---

    async def _endgame_cleanup_task(self, channel_id: int):
        """Tarea de limpieza post-partida."""
        # ... (Esta función parece estar bien, la dejamos como en la versión anterior) ...
        rematch_seconds = get_rematch_window_seconds()
        log.debug(f"[Cleanup C:{channel_id}] Iniciando timer de {rematch_seconds}s.")
        
        try:
            await asyncio.sleep(rematch_seconds)
        except asyncio.CancelledError:
            log.debug(f"[Cleanup C:{channel_id}] Tarea cancelada.")
            return

        log.info(f"[Cleanup C:{channel_id}] Tiempo finalizado. Iniciando limpieza.")
        
        lobby = core.get_lobby_by_channel(channel_id)
        if not lobby:
            log.warning(f"[Cleanup C:{channel_id}] Lobby ya no existe al despertar.")
            await feed.update_feed(self.bot) 
            return
            
        lobby_cog = self.bot.get_cog("ImpostorLobby")
        if not lobby_cog:
            log.error(f"[Cleanup C:{channel_id}] FATAL: No se encontró ImpostorLobby.")
            core.remove_lobby(channel_id)
            await feed.update_feed(self.bot)
            try:
                 channel = self.bot.get_channel(channel_id)
                 if channel: await channel.delete(reason="Cleanup Endgame Fallido")
            except: pass
            return

        human_ids = list(lobby.human_player_ids)
        log.info(f"[Cleanup C:{channel_id}] Jugadores a limpiar: {human_ids}")

        for user_id in human_ids:
             current_lobby_state = core.get_lobby_by_channel(channel_id)
             if not current_lobby_state:
                  log.warning(f"[Cleanup C:{channel_id}] Lobby desapareció durante limpieza.")
                  break 

             user = self.bot.get_user(user_id) 
             if user:
                 log.debug(f"[Cleanup C:{channel_id}] Llamando handle_leave_logic para {user_id}...")
                 await lobby_cog.handle_leave_logic(user, current_lobby_state)
             else:
                 log.warning(f"[Cleanup C:{channel_id}] Usuario {user_id} no encontrado, usando core.remove.")
                 core.remove_user_from_lobby(user_id)
                 lobby_after_remove = core.get_lobby_by_channel(channel_id)
                 if lobby_after_remove and not lobby_after_remove.human_players:
                      log.warning(f"[Cleanup C:{channel_id}] Lobby sin humanos, forzando borrado.")
                      core.remove_lobby(channel_id)
                      await feed.update_feed(self.bot)
                      try:
                           channel = self.bot.get_channel(channel_id)
                           if channel: await channel.delete(reason="Cleanup Endgame (Forzado)")
                      except: pass
                      break 

        if core.get_lobby_by_channel(channel_id):
             log.error(f"[Cleanup C:{channel_id}] Lobby AÚN existe. Borrado forzoso final.")
             core.remove_lobby(channel_id)
             await feed.update_feed(self.bot)
             try:
                  channel = self.bot.get_channel(channel_id)
                  if channel: await channel.delete(reason="Cleanup Endgame (Forzado Final)")
             except: pass
        else:
             log.info(f"[Cleanup C:{channel_id}] Limpieza completada.")


    async def trigger_end_game(self, lobby: GameState, winner_role: str, reason: str):
        """Punto de entrada principal para finalizar la partida."""
        
        # --- AÑADIR MÁS LOGGING ---
        log.debug(f"[Endgame C:{lobby.channel_id}] === Iniciando trigger_end_game ===")
        
        channel = self.bot.get_channel(lobby.channel_id)
        if not channel:
            log.error(f"[Endgame C:{lobby.channel_id}] Canal no encontrado. Limpiando estado.")
            core.remove_lobby(lobby.channel_id) 
            await feed.update_feed(self.bot)
            return

        log.debug(f"[Endgame C:{lobby.channel_id}] Canal encontrado. Adquiriendo lock...")
        async with lobby._lock:
            log.debug(f"[Endgame C:{lobby.channel_id}] Lock adquirido.")
            if lobby.phase == PHASE_END:
                log.warning(f"[Endgame C:{lobby.channel_id}] Ya estaba en PHASE_END. Saliendo.")
                return
            
            log.info(f"[Endgame C:{lobby.channel_id}] Marcando fin de partida. Ganador: {winner_role}. Razón: {reason}")
            
            lobby.phase = PHASE_END
            lobby.in_progress = False
            log.debug(f"[Endgame C:{lobby.channel_id}] Estado actualizado a PHASE_END. Actualizando feed...")
            try:
                await feed.update_feed(self.bot) 
                log.debug(f"[Endgame C:{lobby.channel_id}] Feed actualizado OK.")
            except Exception as e:
                log.exception(f"[Endgame C:{lobby.channel_id}] EXCEPCIÓN al actualizar feed: {e}")
                # Continuamos de todos modos
            
            log.debug(f"[Endgame C:{lobby.channel_id}] Cancelando tareas...")
            tasks_cancelled = []
            try:
                if lobby._turn_task and not lobby._turn_task.done(): 
                     lobby._turn_task.cancel()
                     tasks_cancelled.append("Turn")
            except Exception as e:
                 log.warning(f"[Endgame C:{lobby.channel_id}] Error menor cancelando turn task: {e}")
            try:
                if lobby._vote_task and not lobby._vote_task.done(): 
                     lobby._vote_task.cancel()
                     tasks_cancelled.append("Vote")
            except Exception as e:
                 log.warning(f"[Endgame C:{lobby.channel_id}] Error menor cancelando vote task: {e}")
            
            lobby._turn_task = None
            lobby._vote_task = None
            log.debug(f"[Endgame C:{lobby.channel_id}] Tareas canceladas ({', '.join(tasks_cancelled) if tasks_cancelled else 'Ninguna'}) y limpiadas.")
        
        log.debug(f"[Endgame C:{lobby.channel_id}] Lock liberado.")
        # --- FIN DEL BLOQUE LOCK ---

        # --- LLAMADA A _lock_channel FUE ELIMINADA ---
        
        log.debug(f"[Endgame C:{lobby.channel_id}] Preparando embed final...")
        embed = None # Inicializar embed como None
        try:
            if winner_role == ROLE_SOCIAL:
                embed = discord.Embed(title="🏁 ¡Partida Finalizada! 🏁", description=f"**¡Ganan los SOCIALES!**\n{reason}", color=discord.Color.green())
            else: # ROLE_IMPOSTOR
                embed = discord.Embed(title="🏁 ¡Partida Finalizada! 🏁", description=f"**¡Gana el IMPOSTOR!**\n{reason}", color=discord.Color.red())
                
            impostor_mention = f"<@{lobby.impostor_id}>" if lobby.impostor_id else "*Error: Impostor no asignado*"
            social_mentions = [f"<@{p.user_id}>" for p in lobby.players.values() if p.role == ROLE_SOCIAL and not p.is_bot]
            
            embed.add_field(name="🕵️ Impostor", value=impostor_mention, inline=False)
            embed.add_field(name="🧑‍🤝‍🧑 Sociales", value=", ".join(social_mentions) or "Ninguno", inline=False)
            char_name = lobby.character_name or "Personaje Desconocido"
            embed.add_field(name="🧩 Personaje", value=f"{char_name}", inline=False)
            log.debug(f"[Endgame C:{lobby.channel_id}] Embed preparado OK.")
        except Exception as e:
            log.exception(f"[Endgame C:{lobby.channel_id}] EXCEPCIÓN preparando el embed final: {e}")
            # Intentar enviar mensaje simple si falla el embed
            try:
                await channel.send(f"🏁 Partida Finalizada! Ganador: {winner_role}. Razón: {reason}\n(Error al generar embed)")
            except Exception as send_error:
                 log.error(f"[Endgame C:{lobby.channel_id}] Falló incluso el mensaje simple: {send_error}")
            # Continuar para iniciar limpieza
        
        # Enviar mensaje final (solo si embed se creó) y botones
        if embed:
            log.debug(f"[Endgame C:{lobby.channel_id}] Intentando enviar mensaje final con embed...")
            view = EndgameView(self.bot)
            cleanup_seconds = get_rematch_window_seconds()
            try:
                await channel.send(
                    content=f"Gracias por jugar. Presiona 'Salir' o espera {cleanup_seconds}s para la limpieza automática.",
                    embed=embed,
                    view=view
                )
                log.debug(f"[Endgame C:{lobby.channel_id}] Mensaje final enviado OK.")
            except (discord.Forbidden, discord.HTTPException) as e:
                 log.error(f"[Endgame C:{lobby.channel_id}] EXCEPCIÓN al enviar mensaje final: {e}")
                 # No podemos hacer mucho más si no podemos enviar el mensaje
        else:
             log.warning(f"[Endgame C:{lobby.channel_id}] No se envió mensaje final porque el embed falló.")

        # Iniciar la tarea de limpieza automática
        log.debug(f"[Endgame C:{lobby.channel_id}] Iniciando tarea de cleanup...")
        try:
             # Cancelar tarea de limpieza anterior si existiera
             if lobby._endgame_task and not lobby._endgame_task.done():
                  lobby._endgame_task.cancel()
                  log.debug(f"[Endgame C:{lobby.channel_id}] Tarea de cleanup anterior cancelada.")
                  
             lobby._endgame_task = asyncio.create_task(self._endgame_cleanup_task(lobby.channel_id))
             log.debug(f"[Endgame C:{lobby.channel_id}] Tarea de cleanup iniciada OK.")
        except Exception as e:
             log.exception(f"[Endgame C:{lobby.channel_id}] EXCEPCIÓN al iniciar tarea de cleanup: {e}")

        log.debug(f"[Endgame C:{lobby.channel_id}] === trigger_end_game finalizado ===")


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorEndgameCog(bot))