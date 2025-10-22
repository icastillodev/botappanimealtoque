# cogs/impostor/clean.py

import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Set, Tuple, cast

# Importaciones locales
from . import core
from . import feed

log = logging.getLogger(__name__)

# --- Configuración ---

def get_category_id() -> int | None:
    val = os.getenv("IMPOSTOR_CATEGORY_ID")
    return int(val) if val else None

# Roles específicos usados para determinar si un canal está huérfano
def get_admin_role_ids() -> Set[int]:
    ids_str = os.getenv("IMPOSTOR_ADMIN_ROLE_IDS", "")
    # Asegurarse de manejar IDs vacíos o mal formateados
    valid_ids = set()
    for id_str in ids_str.split(','):
         id_str = id_str.strip()
         if id_str.isdigit():
              valid_ids.add(int(id_str))
         elif id_str: # Logear si no está vacío pero no es dígito
              log.warning(f"Invalid ID found in IMPOSTOR_ADMIN_ROLE_IDS: '{id_str}'")
    return valid_ids


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
        log.error("No se puede limpiar canales: IMPOSTOR_CATEGORY_ID no configurado.")
        return (deleted_channels, lobbies_in_memory)
        
    category = bot.get_channel(category_id)
    if not isinstance(category, discord.CategoryChannel):
        log.error(f"IMPOSTOR_CATEGORY_ID ({category_id}) no es una categoría válida.")
        return (deleted_channels, lobbies_in_memory)
        
    # Roles específicos del .env para la lógica de "huérfano"
    env_admin_roles = get_admin_role_ids()
    log.debug(f"Roles de admin (env) para chequeo de canal huérfano: {env_admin_roles}")
    
    # Crear copia para iterar seguro si borramos canales
    channel_list_copy = list(category.channels) 
    log.debug(f"Revisando {len(channel_list_copy)} canales en la categoría '{category.name}'...")

    for channel in channel_list_copy:
         # Verificar si el canal aún existe en la categoría (por si fue borrado mientras iterábamos)
        current_category = bot.get_channel(category_id) # Refrescar categoría
        if not isinstance(current_category, discord.CategoryChannel) or \
           not discord.utils.get(current_category.channels, id=channel.id):
             log.debug(f"Canal {channel.name} ({channel.id}) ya no existe en la categoría, saltando.")
             continue

        if not isinstance(channel, discord.TextChannel) or not channel.name.startswith("impostor-"):
            log.debug(f"Saltando canal '{channel.name}' (no es texto o no empieza con 'impostor-').")
            continue

        log.debug(f"Revisando canal '{channel.name}' ({channel.id})...")
        is_orphaned = True # Asumir huérfano por defecto
        
        try:
            # channel.members puede estar incompleto sin intents.members o caché llena.
            # Es más seguro iterar y verificar permisos/roles individualmente si es posible,
            # pero channel.members es la forma más directa si la caché está poblada.
            
            # Usar channel.members como primera opción (más eficiente si está poblada)
            members_in_channel = channel.members 
            log.debug(f"'{channel.name}' tiene {len(members_in_channel)} miembros cacheados.")

            if not members_in_channel:
                 log.debug(f"'{channel.name}' está vacío según caché. Marcado como huérfano.")
                 is_orphaned = True
            else:
                 found_normal_user = False
                 for member in members_in_channel:
                     # Ignorar al bot
                     if member.id == bot.user.id:
                         log.debug(f" -> Miembro {member.id} es el bot.")
                         continue 
                     
                     # Ignorar si tiene rol admin del .env
                     # member.roles solo existe en discord.Member
                     is_env_admin = False
                     if hasattr(member, 'roles'): # Asegurarse que es Member
                          member = cast(discord.Member, member) # Ayuda a type hints
                          member_role_ids = {role.id for role in member.roles}
                          if env_admin_roles.intersection(member_role_ids):
                               log.debug(f" -> Miembro {member.id} ({member.display_name}) tiene rol admin del env.")
                               is_env_admin = True
                               continue # Es admin del env, ignorar

                     # Si NO es el bot Y NO es admin del env => es usuario normal
                     log.debug(f" -> Miembro {member.id} ({member.display_name}) es un usuario normal.")
                     is_orphaned = False
                     found_normal_user = True
                     break # Encontramos uno normal, el canal no está huérfano

                 if not found_normal_user:
                      log.debug(f"No se encontraron usuarios normales en '{channel.name}'. Marcado como huérfano.")
                      is_orphaned = True # Confirmar si solo había bot/admins env

        except AttributeError:
            # channel.members no disponible (puede pasar con intents bajos o fallos de caché)
            log.warning(f"Atributo 'members' no disponible para {channel.name}. No se puede determinar si es huérfano.")
            is_orphaned = False # No borrar por seguridad si no podemos verificar
        except Exception as e:
            log.exception(f"Error inesperado al verificar miembros de {channel.name}: {e}")
            is_orphaned = False # No borrar por seguridad

        # Borrar si se determinó que es huérfano
        if is_orphaned:
            log.info(f"Canal huérfano confirmado: {channel.name} ({channel.id}). Eliminando...")
            try:
                await channel.delete(reason="Limpieza de Impostor (Canal huérfano)")
                deleted_channels += 1
                log.info(f"Canal {channel.name} eliminado.")
            except discord.Forbidden:
                log.error(f"Sin permisos para borrar canal huérfano: {channel.name}")
            except discord.NotFound:
                log.warning(f"Canal {channel.name} no encontrado al intentar borrar (ya borrado?).")
            except Exception as e:
                log.exception(f"Error borrando canal huérfano {channel.name}: {e}")
        else:
             log.debug(f"Canal '{channel.name}' no es huérfano.")


    log.info(f"Limpieza de canales completada. {deleted_channels} canales eliminados.")
    return (deleted_channels, lobbies_in_memory)


# --- Cog: Comandos y Listeners ---

class ImpostorCleanCog(commands.Cog, name="ImpostorClean"):
    """Comandos de administración y limpieza automática para Impostor."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._startup_cleanup_done = False

    @commands.Cog.listener()
    async def on_ready(self):
        """Ejecuta la limpieza al arrancar si está configurado."""
        if self._startup_cleanup_done:
            return
            
        await self.bot.wait_until_ready() # Esperar a que el bot esté listo
        
        mode = get_startup_cleanup_mode()
        log.info(f"Modo de limpieza de arranque: {mode}")
        if mode == "all":
            log.info("IMPOSTOR_STARTUP_CLEANUP=all detectado. Ejecutando limpieza...")
            try:
                 await _clean_channels_logic(self.bot)
                 # Actualizar el feed DESPUÉS de limpiar
                 await feed.update_feed(self.bot)
                 log.info("Limpieza de arranque y actualización de feed completadas.")
            except Exception as e:
                 log.exception(f"Error durante la limpieza de arranque: {e}")
        
        self._startup_cleanup_done = True
        log.info("Proceso de limpieza de arranque finalizado.")

    @app_commands.command(name="cleanimpostor", description="[Admin Server] Limpia lobbies memoria y canales impostor-* huérfanos.")
    @app_commands.default_permissions(administrator=True) # Requiere permiso Admin del servidor
    async def cleanimpostor(self, interaction: discord.Interaction):
        """
        Comando para administradores del servidor. Limpia estado en memoria 
        y borra canales 'impostor-*' donde solo queden el bot y/o admins del env.
        """
        # Check manual de permiso Admin por seguridad
        if not interaction.permissions.administrator:
             return await interaction.response.send_message(
                 "❌ Solo Admins del servidor pueden usar esto.", ephemeral=True
             )

        await interaction.response.defer(ephemeral=True)
        log.info(f"/cleanimpostor ejecutado por {interaction.user} (ID: {interaction.user.id})")
        
        try:
             deleted, cleared = await _clean_channels_logic(self.bot)
             
             # Actualizar el feed (debería quedar vacío)
             await feed.update_feed(self.bot)
             
             await interaction.followup.send(
                 f"✅ **Limpieza completada.**\n"
                 f"• Lobbies en memoria reseteados: **{cleared}**\n"
                 f"• Canales huérfanos eliminados: **{deleted}**",
                 ephemeral=True
             )
        except Exception as e:
             log.exception(f"Error durante ejecución de /cleanimpostor: {e}")
             await interaction.followup.send("❌ Ocurrió un error grave durante la limpieza.", ephemeral=True)


    @cleanimpostor.error
    async def cleanimpostor_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Manejar error si el usuario no tiene permiso Admin
        if isinstance(error, app_commands.MissingPermissions): 
            await interaction.response.send_message(
                "❌ No tienes permiso de 'Administrador' para usar esto.", 
                ephemeral=True
            )
        else:
            log.error(f"Error inesperado en /cleanimpostor: {error}")
            # Intentar responder si aún no se hizo
            if not interaction.response.is_done():
                 await interaction.response.send_message("❌ Ocurrió un error inesperado.", ephemeral=True)
            else:
                 # Si ya hubo defer, usar followup
                 try:
                      await interaction.followup.send("❌ Ocurrió un error inesperado.", ephemeral=True)
                 except discord.NotFound: # Interacción expiró
                      log.warning("Interacción expiró antes de poder enviar error de /cleanimpostor.")


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorCleanCog(bot))