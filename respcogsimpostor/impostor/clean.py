# cogs/impostor/clean.py

import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Set, Tuple

# Importaciones locales
from . import core
from . import feed

log = logging.getLogger(__name__)

# --- Configuración ---

def get_category_id() -> int | None:
    val = os.getenv("IMPOSTOR_CATEGORY_ID")
    return int(val) if val else None

def get_admin_role_ids() -> Set[int]:
    ids_str = os.getenv("IMPOSTOR_ADMIN_ROLE_IDS", "")
    return {int(id) for id in ids_str.split(',') if id.strip()}

def get_startup_cleanup_mode() -> str | None:
    return os.getenv("IMPOSTOR_STARTUP_CLEANUP")

# --- Lógica de Limpieza ---

async def _clean_channels_logic(bot: commands.Bot) -> Tuple[int, int]:
    """
    Lógica centralizada para limpiar canales huérfanos y estado en memoria.
    Devuelve (canales_borrados, lobbies_en_memoria_limpiados).
    """
    log.info("Iniciando lógica de limpieza de Impostor...")
    
    # 1. Limpiar estado en memoria
    lobbies_in_memory = len(core.get_all_lobbies())
    core.clear_all_lobbies()
    log.info(f"Se limpiaron {lobbies_in_memory} lobbies del estado en memoria.")

    # 2. Limpiar canales huérfanos
    deleted_channels = 0
    category_id = get_category_id()
    if not category_id:
        log.error("No se puede limpiar canales huérfanos: IMPOSTOR_CATEGORY_ID no está configurado.")
        return (deleted_channels, lobbies_in_memory)
        
    category = bot.get_channel(category_id)
    if not isinstance(category, discord.CategoryChannel):
        log.error(f"IMPOSTOR_CATEGORY_ID ({category_id}) no es una categoría válida.")
        return (deleted_channels, lobbies_in_memory)
        
    admin_roles = get_admin_role_ids()
    
    # Iterar sobre una copia de la lista de canales
    for channel in list(category.channels):
        if not isinstance(channel, discord.TextChannel) or not channel.name.startswith("impostor-"):
            continue

        # Definición de "Huérfano":
        # Un canal donde solo quedan el bot y/o admins.
        is_orphaned = True
        
        # Ojo: channel.members puede no estar completo sin 'intents.members'
        # o si la caché no está llena. Es más seguro iterar 'members'.
        try:
            members = channel.members
        except AttributeError:
             # Si `members` no está disponible (p.ej. intents bajos), 
             # asumimos que no podemos verificar y lo saltamos.
             log.warning(f"No se pudo obtener la lista de miembros de {channel.name}, saltando limpieza.")
             continue
             
        if not members:
            # Vacío (ni siquiera el bot está)
            is_orphaned = True
        
        for member in members:
            if member.id == bot.user.id:
                continue # Es el bot
                
            # Chequear si es admin
            is_admin = any(role.id in admin_roles for role in member.roles)
            if is_admin:
                continue # Es un admin
                
            # Si llegó aquí, es un usuario normal
            is_orphaned = False
            break
            
        if is_orphaned:
            log.info(f"Canal huérfano detectado: {channel.name} (ID: {channel.id}). Eliminando...")
            try:
                await channel.delete(reason="Limpieza de Impostor (Canal huérfano)")
                deleted_channels += 1
            except discord.Forbidden:
                log.error(f"No tengo permisos para borrar el canal huérfano: {channel.name}")
            except discord.NotFound:
                log.warning(f"El canal {channel.name} ya no existía al intentar borrarlo.")
            except Exception as e:
                log.exception(f"Error borrando canal {channel.name}: {e}")

    log.info(f"Limpieza de canales completada. {deleted_channels} canales eliminados.")
    return (deleted_channels, lobbies_in_memory)


# --- Cog: Comandos y Listeners ---

class ImpostorCleanCog(commands.Cog, name="ImpostorClean"):
    """
    Comandos de administración y limpieza automática para Impostor.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._startup_cleanup_done = False

    @commands.Cog.listener()
    async def on_ready(self):
        """Ejecuta la limpieza al arrancar si está configurado."""
        if self._startup_cleanup_done:
            return
            
        await self.bot.wait_until_ready()
        
        if get_startup_cleanup_mode() == "all":
            log.info("IMPOSTOR_STARTUP_CLEANUP=all detectado. Ejecutando limpieza de arranque...")
            await _clean_channels_logic(self.bot)
            # Actualizar el feed después de limpiar
            await feed.update_feed(self.bot)
        
        self._startup_cleanup_done = True
        log.info("Limpieza de arranque de Impostor completada.")

    @app_commands.command(name="cleanimpostor", description="[Admin] Limpia lobbies y canales huérfanos de Impostor.")
    @app_commands.checks.has_any_role(
        int(role_id.strip()) for role_id in os.getenv("IMPOSTOR_ADMIN_ROLE_IDS", "").split(',') if role_id.strip()
    )
    async def cleanimpostor(self, interaction: discord.Interaction):
        """
        Limpia forzosamente todos los lobbies en memoria y borra
        canales de 'impostor-*' donde solo queden el bot y/o admins.
        """
        await interaction.response.defer(ephemeral=True)
        
        deleted, cleared = await _clean_channels_logic(self.bot)
        
        # Actualizar el feed (debería quedar vacío)
        await feed.update_feed(self.bot)
        
        await interaction.followup.send(
            f"✅ **Limpieza completada.**\n"
            f"• Lobbies en memoria reseteados: **{cleared}**\n"
            f"• Canales huérfanos eliminados: **{deleted}**",
            ephemeral=True
        )

    @cleanimpostor.error
    async def cleanimpostor_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "❌ No tienes permisos para usar este comando.",
                ephemeral=True
            )
        else:
            log.error(f"Error en /cleanimpostor: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Ocurrió un error inesperado.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Ocurrió un error inesperado.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorCleanCog(bot))