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
    """
    Vista persistente con el botón 'Salir del lobby'.
    """
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None) # Vista persistente
        self.bot = bot

    @discord.ui.button(label="Salir del lobby", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="imp:leave_now")
    async def leave_now_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Saca al jugador del lobby y gestiona la limpieza del canal."""
        
        # 1. Obtener el Cog de Lobby (que tiene la lógica de 'leave')
        lobby_cog = self.bot.get_cog("ImpostorLobby")
        if not lobby_cog:
            log.error(f"FATAL: No se pudo encontrar 'ImpostorLobby' para manejar la salida en C:{interaction.channel_id}")
            return await interaction.response.send_message("❌ Error: Módulo de Lobby no cargado.", ephemeral=True)
            
        # 2. Obtener el lobby (puede que el usuario ya haya salido)
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            # El lobby ya no existe, pero el canal sí. Damos permisos al usuario para borrar.
             try:
                await interaction.channel.set_permissions(interaction.user, overwrite=None)
                await interaction.channel.send(f"<@{interaction.user.id}> ha salido. El canal debería borrarse si está vacío.")
             except (discord.Forbidden, discord.NotFound):
                pass
             return await interaction.response.send_message("Has salido. Este canal se borrará pronto.", ephemeral=True)

        # 3. Informar al usuario
        await interaction.response.send_message("Saliendo del lobby...", ephemeral=True)
        
        # 4. Usar la lógica centralizada de 'leave'
        # Esta función (en lobby.py) quita al usuario y borra el canal si es el último humano.
        await lobby_cog.handle_leave_logic(interaction.user, lobby)


# --- Cog: Lógica de Fin de Partida ---

class ImpostorEndgameCog(commands.Cog, name="ImpostorEndgame"):
    """
    Gestiona el final de la partida, el anuncio de ganadores y la limpieza.
    """
    
    _view_registered = False

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Registrar la vista persistente una sola vez
        if not ImpostorEndgameCog._view_registered:
            bot.add_view(EndgameView(self.bot))
            ImpostorEndgameCog._view_registered = True
            log.info("Vista 'EndgameView' registrada persistentemente.")

    async def _lock_channel(self, channel: discord.TextChannel, lobby: GameState):
        """Pone el canal en modo solo-lectura para los jugadores."""
        try:
            # Sobreescribir permisos para todos los jugadores
            overwrites = channel.overwrites
            for player_id in lobby.get_player_ids():
                if player_id < 0: continue # Ignorar bots
                member = channel.guild.get_member(player_id)
                if member:
                    # Negar envío de mensajes, permitir ver historial
                    overwrites[member] = discord.PermissionOverwrite(send_messages=False, read_messages=True)
            
            # Asegurar que el bot pueda seguir hablando
            overwrites[channel.guild.me] = discord.PermissionOverwrite(send_messages=True, read_messages=True, manage_channels=True)
            
            await channel.edit(overwrites=overwrites)
        except discord.Forbidden:
            log.error(f"No tengo permisos para bloquear C:{channel.id} al final de la partida.")
        except Exception as e:
            log.exception(f"Error al bloquear C:{channel.id}: {e}")

    async def _endgame_cleanup_task(self, channel_id: int):
        """
        Tarea que se ejecuta N segundos después de terminar la partida.
        Limpia a los jugadores restantes que no pulsaron 'Salir'.
        """
        rematch_seconds = get_rematch_window_seconds()
        log.debug(f"Iniciando cleanup task ({rematch_seconds}s) para C:{channel_id}")
        
        await asyncio.sleep(rematch_seconds)
        
        log.info(f"Tiempo de revancha finalizado. Limpiando C:{channel_id}")
        
        lobby = core.get_lobby_by_channel(channel_id)
        if not lobby:
            log.warning(f"Cleanup C:{channel_id}: Lobby ya no existe (probablemente se limpió).")
            return
            
        lobby_cog = self.bot.get_cog("ImpostorLobby")
        if not lobby_cog:
            log.error(f"FATAL: No se pudo encontrar 'ImpostorLobby' durante el cleanup de C:{channel_id}")
            return

        # Obtener una copia de los IDs de los jugadores humanos
        human_ids = list(lobby.human_player_ids)
        if not human_ids:
            log.debug(f"Cleanup C:{channel_id}: No quedaban humanos en el estado.")
            # Forzar limpieza por si acaso
            await lobby_cog.handle_leave_logic(self.bot.user, lobby)
            return

        log.info(f"Cleanup C:{channel_id}: Removiendo a {len(human_ids)} jugadores restantes...")
        
        channel = self.bot.get_channel(channel_id)
        
        # Iterar y sacar a cada uno
        for user_id in human_ids:
            user = self.bot.get_user(user_id) # Puede ser None si el bot no lo cachea
            if user:
                # La lógica de 'leave' gestionará la limpieza del último jugador
                await lobby_cog.handle_leave_logic(user, lobby)
            else:
                # Si no encontramos al usuario, forzamos la salida desde 'core'
                core.remove_user_from_lobby(user_id)
                log.debug(f"Cleanup C:{channel_id}: Usuario {user_id} no encontrado, removido del estado.")
        
        # Si después de eso el lobby AÚN existe (p.ej. solo quedaban bots)
        if core.get_lobby_by_channel(channel_id):
            log.warning(f"Cleanup C:{channel_id}: Lobby AÚN existe, forzando borrado.")
            core.remove_lobby(channel_id)

            # --- AÑADE ESTA LÍNEA ---
            await feed.update_feed(self.bot)
            # --- FIN DE LA MODIFICACIÓN ---
            
            if channel:
                try:
                    await channel.delete(reason="Fin de partida Impostor (Cleanup)")
                except (discord.Forbidden, discord.NotFound):
                    pass


    async def trigger_end_game(self, lobby: GameState, winner_role: str, reason: str):
        """
        Punto de entrada principal para finalizar la partida.
        """
        channel = self.bot.get_channel(lobby.channel_id)
        if not channel:
            log.error(f"Endgame C:{lobby.channel_id}: Canal no encontrado.")
            return

        async with lobby._lock:
            # Evitar doble 'endgame'
            if lobby.phase == PHASE_END:
                log.warning(f"C:{lobby.channel_id}: Se intentó terminar una partida que ya había finalizado.")
                return
            
            log.info(f"Fin de partida en C:{lobby.channel_id}. Ganador: {winner_role}. Razón: {reason}")
            
            lobby.phase = PHASE_END
            lobby.in_progress = False
            
            # --- ¡AÑADE ESTA LÍNEA! ---
            await feed.update_feed(self.bot) 
            # --- FIN DE LA MODIFICACIÓN ---

            # Cancelar tareas activas...
            if lobby._turn_task: lobby._turn_task.cancel()
            if lobby._vote_task: lobby._vote_task.cancel()

        # 1. Bloquear el canal
        await self._lock_channel(channel, lobby)
        
        # 2. Preparar el Embed final
        if winner_role == ROLE_SOCIAL:
            embed = discord.Embed(
                title="🏁 ¡Partida Finalizada! 🏁",
                description=f"**¡Ganan los SOCIALES!**\n{reason}",
                color=discord.Color.green()
            )
        else: # ROLE_IMPOSTOR
            embed = discord.Embed(
                title="🏁 ¡Partida Finalizada! 🏁",
                description=f"**¡Gana el IMPOSTOR!**\n{reason}",
                color=discord.Color.red()
            )
            
        # Revelar roles
        impostor_mention = f"<@{lobby.impostor_id}>"
        social_mentions = [f"<@{p.user_id}>" for p in lobby.players.values() if p.role == ROLE_SOCIAL and not p.is_bot]
        
        embed.add_field(name="🕵️ Impostor", value=impostor_mention, inline=False)
        embed.add_field(name="🧑‍🤝‍🧑 Sociales", value=", ".join(social_mentions) or "Ninguno", inline=False)
        embed.add_field(name="🧩 Personaje", value=f"{lobby.character_name}", inline=False)

        # 3. Enviar mensaje final y botones
        view = EndgameView(self.bot)
        cleanup_seconds = get_rematch_window_seconds()
        await channel.send(
            content=f"Gracias por jugar. Presiona 'Salir' o espera {cleanup_seconds}s para la limpieza automática.",
            embed=embed,
            view=view
        )
        
        # 4. Iniciar la tarea de limpieza automática
        asyncio.create_task(self._endgame_cleanup_task(lobby.channel_id))


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorEndgameCog(bot))