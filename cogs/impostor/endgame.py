# cogs/impostor/endgame.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Optional

# Importaciones locales
from . import core
from . import chat_guard
from .engine import GameState, PHASE_END, ROLE_IMPOSTOR, ROLE_SOCIAL
from . import feed
from . import chars
from .lobby import close_lobby_channel, queue_hud_update, _lobby_howto_text
from .activity import post_staff_log, touch_lobby_activity
from .config import get_rematch_window_seconds, get_rematch_vote_percent
from .engine import PHASE_IDLE
from .rematch_utils import rematch_votes_needed, rematch_vote_status

log = logging.getLogger(__name__)

# --- View de Fin de Partida ---

class EndgameView(discord.ui.View):
    """Vista persistente: salir o cerrar sala (host)."""
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None) 
        self.bot = bot

    @discord.ui.button(
        label="Revancha (host)",
        style=discord.ButtonStyle.success,
        emoji="🔁",
        custom_id="imp:rematch",
        row=0,
    )
    async def rematch_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.followup.send("El lobby ya no existe.", ephemeral=True)
        endgame_cog = self.bot.get_cog("ImpostorEndgame")
        if not endgame_cog:
            return await interaction.followup.send("❌ Módulo de fin de partida no cargado.", ephemeral=True)
        ok, msg = await endgame_cog.trigger_rematch(lobby, interaction.user.id)
        if not ok:
            return await interaction.followup.send(msg or "No se pudo iniciar la revancha.", ephemeral=True)
        await interaction.followup.send("🔁 Lobby listo para otra partida.", ephemeral=True)

    @discord.ui.button(
        label="Quiero revancha",
        style=discord.ButtonStyle.primary,
        emoji="👍",
        custom_id="imp:rematch_vote",
        row=1,
    )
    async def rematch_vote_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby or lobby.phase != PHASE_END:
            return await interaction.followup.send(
                "❌ Solo podés votar revancha al terminar la partida.", ephemeral=True
            )
        player = lobby.get_player(interaction.user.id)
        if not player or player.is_bot:
            return await interaction.followup.send("❌ Solo jugadores humanos del lobby.", ephemeral=True)

        endgame_cog = self.bot.get_cog("ImpostorEndgame")
        if not endgame_cog:
            return await interaction.followup.send("❌ Módulo de fin de partida no cargado.", ephemeral=True)

        added, msg = await endgame_cog.register_rematch_vote(lobby, interaction.user.id)
        if added:
            ok, _ = await endgame_cog.try_rematch_if_majority(lobby)
            if ok:
                msg += "\n\n🔁 **¡Mayoría alcanzada!** Lobby reiniciado."
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(
        label="Cerrar sala (host)",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        custom_id="imp:close_lobby_host",
        row=0,
    )
    async def close_lobby_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.followup.send("El lobby ya no existe.", ephemeral=True)
        if lobby.host_id != interaction.user.id:
            return await interaction.followup.send("❌ Solo el **host** puede cerrar la sala.", ephemeral=True)
        lobby_name = lobby.lobby_name
        lobby_cid = lobby.channel_id
        ok = await close_lobby_channel(
            self.bot, lobby, reason="Host cerró lobby Impostor (fin de partida)"
        )
        if ok:
            try:
                close_embed = discord.Embed(
                    title="Impostor — sala cerrada (host)",
                    description=f"Host <@{interaction.user.id}> cerró el lobby.",
                    color=discord.Color.dark_grey(),
                )
                close_embed.add_field(name="Sala", value=lobby_name, inline=True)
                close_embed.add_field(name="Canal", value=f"<#{lobby_cid}>", inline=True)
                await post_staff_log(self.bot, close_embed)
            except Exception as e:
                log.warning("staff log cierre host: %s", e)
        if not ok:
            return await interaction.followup.send(
                "No pude borrar el canal (permisos). Sacá a los jugadores con **Salir**.",
                ephemeral=True,
            )
        await interaction.followup.send("Sala cerrada.", ephemeral=True)

    @discord.ui.button(label="Salir del lobby", style=discord.ButtonStyle.secondary, emoji="🚪", custom_id="imp:leave_now", row=2)
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

        ok = await lobby_cog.handle_leave_logic(interaction.user, lobby)
        if not ok:
            return await interaction.followup.send(
                "No pudiste salir (restricción de tiempo o error).", ephemeral=True
            )
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
                 await lobby_cog.handle_leave_logic(user, current_lobby_state, force=True)
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
            lobby.rematch_votes = set()
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

        await chat_guard.restore_channel_chat(self.bot, lobby)

        # --- LLAMADA A _lock_channel FUE ELIMINADA ---
        
        log.debug(f"[Endgame C:{lobby.channel_id}] Preparando embed final...")
        embed = None # Inicializar embed como None
        try:
            if winner_role == ROLE_SOCIAL:
                embed = discord.Embed(
                    title="🏁 ¡Partida Finalizada! 🏁",
                    description=f"**¡Ganan los SOCIALES!**\n{reason}",
                    color=discord.Color.green(),
                )
            else:
                embed = discord.Embed(
                    title="🏁 ¡Partida Finalizada! 🏁",
                    description=f"**¡Ganan los IMPOSTORES!**\n{reason}",
                    color=discord.Color.red(),
                )

            imp_ids = lobby.impostor_ids or ({lobby.impostor_id} if lobby.impostor_id else set())
            impostor_mention = ", ".join(f"<@{uid}>" for uid in imp_ids) or "*Ninguno*"
            social_mentions = [
                f"<@{p.user_id}>"
                for p in lobby.players.values()
                if p.role == ROLE_SOCIAL and not p.is_bot
            ]

            embed.add_field(name="🕵️ Impostor(es)", value=impostor_mention, inline=False)
            embed.add_field(name="🧑‍🤝‍🧑 Sociales", value=", ".join(social_mentions) or "Ninguno", inline=False)
            char_name = lobby.character_name or "Secreto desconocido"
            tema = lobby.secret_theme or "personaje"
            tema_txt = chars.SECRET_THEME_LABELS_ES.get(tema, tema)
            embed.add_field(name="🎲 Temática", value=tema_txt, inline=False)
            secreto_val = char_name
            if tema == "personaje" and getattr(lobby, "character_anime", None):
                secreto_val = f"{char_name}\n*{lobby.character_anime}*"
            embed.add_field(name="🧩 Secreto", value=secreto_val, inline=False)
            needed = rematch_votes_needed(lobby)
            pct = get_rematch_vote_percent()
            cleanup_seconds = get_rematch_window_seconds()
            embed.add_field(
                name="🔁 Revancha",
                value=(
                    f"Votos: **0/{needed}** ({pct}% de humanos). "
                    f"Botón **Quiero revancha** o `?quierorevancha`.\n"
                    f"Host: **Revancha** / `/revancha` · auto-cleanup en **{cleanup_seconds}s**."
                ),
                inline=False,
            )
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
                    content=(
                        f"Gracias por jugar. **Host:** **Revancha** o **Cerrar sala** "
                        f"(si no, auto-cleanup en **{cleanup_seconds}s**).\n"
                        f"**Jugadores:** **Quiero revancha** (mayoría reinicia el lobby) o **Salir**."
                    ),
                    embed=embed,
                    view=view,
                )
                log.debug(f"[Endgame C:{lobby.channel_id}] Mensaje final enviado OK.")
            except (discord.Forbidden, discord.HTTPException) as e:
                 log.error(f"[Endgame C:{lobby.channel_id}] EXCEPCIÓN al enviar mensaje final: {e}")
                 # No podemos hacer mucho más si no podemos enviar el mensaje
        else:
             log.warning(f"[Endgame C:{lobby.channel_id}] No se envió mensaje final porque el embed falló.")

        # Economía: estadísticas semanales (partidas / victoria como impostor)
        eco = getattr(self.bot, "economia_db", None)
        if eco:
            try:
                eco.record_impostor_game_end(lobby, winner_role)
                eco.record_impostor_ranked_stats(lobby, winner_role)
                eco.record_impostor_game_log(lobby, winner_role, reason)
            except Exception as e:
                log.warning(f"[Endgame C:{lobby.channel_id}] No se pudo registrar stats Impostor: {e}")

        try:
            imp_ids = lobby.impostor_ids or set()
            log_embed = discord.Embed(
                title="Impostor — partida terminada",
                description=reason[:500] if reason else "—",
                color=discord.Color.green() if winner_role == ROLE_SOCIAL else discord.Color.red(),
            )
            log_embed.add_field(
                name="Ganador",
                value="Sociales" if winner_role == ROLE_SOCIAL else "Impostores",
                inline=True,
            )
            log_embed.add_field(name="Canal", value=f"<#{lobby.channel_id}>", inline=True)
            log_embed.add_field(
                name="Impostor(es)",
                value=", ".join(f"<@{u}>" for u in imp_ids) or "—",
                inline=False,
            )
            log_embed.add_field(name="Secreto", value=lobby.character_name or "—", inline=False)
            await post_staff_log(self.bot, log_embed)
        except Exception as e:
            log.warning("[Endgame C:%s] staff log: %s", lobby.channel_id, e)

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

    async def register_rematch_vote(self, lobby: GameState, user_id: int) -> tuple[bool, str]:
        """Registra voto de revancha. Devuelve (True, mensaje) si se añadió."""
        if lobby.phase != PHASE_END:
            return False, "❌ La revancha solo está disponible al terminar la partida."
        if user_id in lobby.rematch_votes:
            return False, f"✅ Ya votaste revancha. {rematch_vote_status(lobby)}."
        lobby.rematch_votes.add(user_id)
        needed = rematch_votes_needed(lobby)
        have = len(lobby.rematch_votes)
        return True, f"👍 Voto registrado ({have}/{needed}). Si llegan a **{needed}**, arranca la revancha."

    async def try_rematch_if_majority(self, lobby: GameState) -> tuple[bool, str]:
        needed = rematch_votes_needed(lobby)
        if len(lobby.rematch_votes) < needed:
            return False, ""
        return await self._do_rematch(lobby, by_host_id=lobby.host_id)

    async def trigger_rematch(self, lobby: GameState, requester_id: int) -> tuple[bool, str]:
        """Reinicia el lobby (host directo o tras mayoría de votos)."""
        if lobby.host_id != requester_id:
            return False, "❌ Solo el **host** puede forzar revancha con el botón verde."
        if lobby.phase != PHASE_END:
            return False, "❌ La revancha solo está disponible al terminar la partida."
        return await self._do_rematch(lobby, by_host_id=requester_id)

    async def _do_rematch(self, lobby: GameState, *, by_host_id: int) -> tuple[bool, str]:
        if lobby.phase != PHASE_END:
            return False, "❌ La revancha solo está disponible al terminar la partida."

        channel = self.bot.get_channel(lobby.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return False, "❌ Canal del lobby no encontrado."

        if lobby._endgame_task and not lobby._endgame_task.done():
            lobby._endgame_task.cancel()
            lobby._endgame_task = None

        th_id = lobby.eliminated_thread_id
        async with lobby._lock:
            lobby.reset_for_rematch()

        await chat_guard.restore_channel_chat(self.bot, lobby)

        if th_id:
            th = channel.get_thread(th_id)
            if th:
                try:
                    await th.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass
            lobby.eliminated_thread_id = None

        try:
            purge_check = (
                (lambda m: m.id != lobby.hud_message_id) if lobby.hud_message_id else (lambda m: True)
            )
            await channel.purge(limit=100, check=purge_check)
        except (discord.Forbidden, discord.HTTPException):
            pass

        touch_lobby_activity(lobby)
        await feed.update_feed(self.bot)
        await queue_hud_update(lobby.channel_id)

        await channel.send(
            "🔁 **Revancha:** el lobby se reinició. Todos en **Ready** → host **Comenzar**.\n"
            + _lobby_howto_text()
        )
        log.info("Revancha iniciada C:%s (solicitante %s)", lobby.channel_id, by_host_id)
        return True, ""

    @app_commands.command(name="revancha", description="[Host] Reinicia el lobby para otra partida.")
    async def revancha_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.followup.send("❌ No estás en un lobby Impostor.", ephemeral=True)
        ok, msg = await self.trigger_rematch(lobby, interaction.user.id)
        if not ok:
            return await interaction.followup.send(msg, ephemeral=True)
        await interaction.followup.send("🔁 Revancha iniciada.", ephemeral=True)

    @commands.command(name="revancha")
    async def revancha_prefix(self, ctx: commands.Context):
        lobby = core.get_lobby_by_channel(ctx.channel.id)
        if not lobby:
            return await ctx.send("❌ Solo en un canal de lobby Impostor.")
        ok, msg = await self.trigger_rematch(lobby, ctx.author.id)
        if not ok:
            return await ctx.send(msg)
        await ctx.send("🔁 Revancha iniciada.")

    @commands.command(name="quierorevancha", aliases=["votarevancha", "revanchasi"])
    async def quiero_revancha_prefix(self, ctx: commands.Context):
        lobby = core.get_lobby_by_channel(ctx.channel.id)
        if not lobby:
            return await ctx.send("❌ Solo en un canal de lobby Impostor.")
        added, msg = await self.register_rematch_vote(lobby, ctx.author.id)
        if added:
            ok, _ = await self.try_rematch_if_majority(lobby)
            if ok:
                msg += "\n\n🔁 **¡Mayoría alcanzada!** Lobby reiniciado."
        await ctx.send(msg)

    @app_commands.command(name="quiero-revancha", description="Votá para reiniciar el lobby (mayoría).")
    async def quiero_revancha_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.followup.send("❌ Solo en un lobby Impostor.", ephemeral=True)
        added, msg = await self.register_rematch_vote(lobby, interaction.user.id)
        if added:
            ok, _ = await self.try_rematch_if_majority(lobby)
            if ok:
                msg += "\n\n🔁 **¡Mayoría alcanzada!** Lobby reiniciado."
        await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorEndgameCog(bot))