# cogs/impostor/feed.py

import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List, Set # <-- 1. 'Set' AÑADIDO

from . import core
from .engine import GameState

log = logging.getLogger(__name__)

# --- Configuración ---

def get_feed_channel_id() -> Optional[int]:
    val = os.getenv("IMPOSTOR_FEED_CHANNEL_ID")
    return int(val) if val else None

def get_max_players() -> int:
    val = os.getenv("IMPOSTOR_MAX_PLAYERS", "5")
    return int(val)

# --- 2. FUNCIÓN DE ADMIN AÑADIDA ---
def get_admin_role_ids() -> Set[int]:
    """Función de utilidad para obtener roles admin (evita importación circular)."""
    ids_str = os.getenv("IMPOSTOR_ADMIN_ROLE_IDS", "")
    return {int(id.strip()) for id in ids_str.split(',') if id.strip()}
# --- FIN DE FUNCIÓN AÑADIDA ---

# ID del mensaje del feed que estamos editando
_LAST_FEED_MESSAGE_ID: Optional[int] = None


# --- Lógica del Embed ---

async def _generate_feed_embed(bot: commands.Bot) -> discord.Embed:
    """Crea el embed actualizado de la cartelera de lobbys."""
    
    all_lobbies = core.get_all_lobbies()
    open_lobbies: List[GameState] = []
    closed_lobbies: List[GameState] = []
    playing_lobbies: List[GameState] = [] # <-- NUEVA LISTA

    for lobby in all_lobbies:
        if lobby.in_progress:
            playing_lobbies.append(lobby) # <-- NUEVA LÓGICA
        elif lobby.is_open:
            open_lobbies.append(lobby)
        else:
            closed_lobbies.append(lobby)

    max_players = get_max_players()
    embed = discord.Embed(
        title=f"Lobbys de IMPOSTOR ({max_players} jugadores)",
        description="Encuentra una partida o crea la tuya con `/crearsimpostor`.\nUsa `/helpimpostor` para ver las reglas.",
        color=discord.Color.blue()
    )

    # --- Lobbys Abiertos ---
    open_field_value = ""
    if not open_lobbies:
        open_field_value = "No hay lobbys abiertos en este momento."
    else:
        for lobby in open_lobbies:
            host_mention = f"<@{lobby.host_id}>"
            player_count = lobby.all_players_count
            
            line = f"• **{lobby.lobby_name}** — {player_count}/{max_players} — Host: {host_mention}\n"
            line += f"  └ `/entrar nombre:{lobby.lobby_name}`\n"
            open_field_value += line

    embed.add_field(name="🟢 Lobbys Abiertos", value=open_field_value, inline=False)

    # --- Lobbys Cerrados ---
    closed_field_value = ""
    if not closed_lobbies:
        closed_field_value = "No hay lobbys cerrados."
    else:
        for lobby in closed_lobbies:
            host_mention = f"<@{lobby.host_id}>"
            player_count = lobby.all_players_count
            
            line = f"• **{lobby.lobby_name}** — {player_count}/{max_players} — Host: {host_mention}\n"
            closed_field_value += line
            
    embed.add_field(name="🔒 Lobbys Cerrados", value=closed_field_value, inline=False)
    
    # --- NUEVO CAMPO: EN PARTIDA ---
    playing_field_value = ""
    if not playing_lobbies:
        playing_field_value = "No hay partidas en curso."
    else:
        for lobby in playing_lobbies:
            host_mention = f"<@{lobby.host_id}>"
            player_count = lobby.all_players_count
            
            line = f"• **{lobby.lobby_name}** — {player_count}/{max_players} — Host: {host_mention}\n"
            playing_field_value += line
            
    embed.add_field(name="🔴 En Partida", value=playing_field_value, inline=False)
    # --- FIN NUEVO CAMPO ---
    
    embed.set_footer(text="Este panel se actualiza automáticamente.")
    return embed

# --- Función Pública de Actualización ---

async def update_feed(bot: commands.Bot):
    """
    Función principal para publicar o editar la cartelera de lobbys.
    Esta función es llamada por otros cogs.
    """
    global _LAST_FEED_MESSAGE_ID
    
    channel_id = get_feed_channel_id()
    if not channel_id:
        log.warning("IMPOSTOR_FEED_CHANNEL_ID no está configurado. No se puede actualizar el feed.")
        return

    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        log.error(f"No se pudo encontrar el canal de feed (ID: {channel_id}) o no es un canal de texto.")
        return

    try:
        embed = await _generate_feed_embed(bot)
        
        # --- Estrategia 1: Editar mensaje existente si conocemos su ID ---
        if _LAST_FEED_MESSAGE_ID:
            try:
                msg = await channel.fetch_message(_LAST_FEED_MESSAGE_ID)
                await msg.edit(embed=embed, view=None)
                # log.debug(f"Feed actualizado (Editado por ID): {msg.id}")
                return
            except discord.NotFound:
                log.warning(f"El mensaje del feed (ID: {_LAST_FEED_MESSAGE_ID}) no fue encontrado. Buscando...")
                _LAST_FEED_MESSAGE_ID = None
            except discord.Forbidden:
                log.error(f"No tengo permisos para editar el mensaje del feed en {channel.name}")
                return
            except Exception as e:
                log.exception(f"Error inesperado al editar el feed: {e}")
                _LAST_FEED_MESSAGE_ID = None # Forzar re-búsqueda

        # --- Estrategia 2: Buscar último mensaje del bot en el canal ---
        # (Si _LAST_FEED_MESSAGE_ID es None o falló fetch_message)
        try:
            async for msg in channel.history(limit=50):
                if msg.author.id == bot.user.id:
                    _LAST_FEED_MESSAGE_ID = msg.id
                    await msg.edit(embed=embed, view=None)
                    # log.debug(f"Feed actualizado (Editado por Búsqueda): {msg.id}")
                    return
        except discord.Forbidden:
            log.error(f"No tengo permisos para leer el historial de {channel.name}")
            return
        except Exception as e:
            log.exception(f"Error inesperado al buscar en el historial del feed: {e}")
            
        # --- Estrategia 3: Enviar mensaje nuevo ---
        # (Si no se encontró ningún mensaje para editar)
        try:
            new_msg = await channel.send(embed=embed)
            _LAST_FEED_MESSAGE_ID = new_msg.id
            log.info(f"Nuevo feed publicado en {channel.name} (ID: {new_msg.id})")
        except discord.Forbidden:
            log.error(f"No tengo permisos para enviar mensajes en {channel.name}")

    except Exception as e:
        log.exception(f"Error mayor en la función update_feed: {e}")


# --- Cog: Comandos y Listeners ---

class ImpostorFeedCog(commands.Cog, name="ImpostorFeed"):
    """
    Gestiona la publicación y actualización de la cartelera de lobbys.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Asegura que el feed esté publicado al iniciar el bot."""
        # Esperamos un segundo para que el bot esté 100% listo
        await asyncio.sleep(1) 
        await update_feed(self.bot)

    @app_commands.command(name="feed_refresh", description="[Admin] Fuerza la actualización de la cartelera de Impostor.")
    @app_commands.checks.has_any_role(
        int(role_id.strip()) for role_id in os.getenv("IMPOSTOR_ADMIN_ROLE_IDS", "").split(',') if role_id.strip()
    )
    async def feed_refresh_command(self, interaction: discord.Interaction):
        """Comando admin para forzar la actualización del feed."""
        await interaction.response.defer(ephemeral=True)
        log.info(f"Actualización de feed forzada por {interaction.user.name}")
        await update_feed(self.bot)
        await interaction.followup.send("✅ Cartelera actualizada.", ephemeral=True)

    @feed_refresh_command.error
    async def feed_refresh_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "❌ No tienes permisos para usar este comando.",
                ephemeral=True
            )
        else:
            log.error(f"Error en /feed_refresh: {error}")
            await interaction.response.send_message(
                "❌ Ocurrió un error inesperado.",
                ephemeral=True
            )

    # --- 3. LISTENER DE MENSAJES AÑADIDO ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        feed_channel_id = get_feed_channel_id()
        
        # No procesar DMs o mensajes de otros canales
        if not message.guild or message.channel.id != feed_channel_id:
            return
        
        # No borrar al bot
        if message.author.id == self.bot.user.id:
            return
        
        # No borrar a los admins
        try:
            # Asegurarse de que el autor es un Miembro (para obtener roles)
            if not isinstance(message.author, discord.Member):
                return 

            admin_roles = get_admin_role_ids()
            if any(role.id in admin_roles for role in message.author.roles):
                return
        except Exception as e:
            log.warning(f"Error al chequear permisos de admin en on_message del feed: {e}")
            # Continuar y borrar por seguridad

        # Si llegó aquí, es un usuario normal escribiendo
        try:
            await message.delete()
        except discord.Forbidden:
            log.warning(f"No tengo permisos para borrar mensajes en el canal de feed C:{message.channel.id}")
        except discord.NotFound:
            pass # El mensaje ya fue borrado
    # --- FIN DEL LISTENER AÑADIDO ---

async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorFeedCog(bot))