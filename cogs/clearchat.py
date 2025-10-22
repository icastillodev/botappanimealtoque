# cogs/clearchat.py
from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
import logging # Importar logging para mensajes de error

log = logging.getLogger(__name__) # Crear un logger

def is_admin(member: discord.Member) -> bool:
    if member.guild is None:
        return False
    # Usar manage_messages como permiso mínimo requerido ahora
    perms = member.guild_permissions
    return perms.manage_messages or perms.administrator 

class ClearChatCog(commands.Cog):
    """Herramienta admin para limpiar mensajes de un canal."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="clearchatadmin",
        description="(Admin) Borrar todos los mensajes recientes de este canal." 
    )
    # Cambiar el permiso por defecto a manage_messages, aunque admin también funciona
    @app_commands.default_permissions(manage_messages=True) 
    async def clearchatadmin(self, interaction: discord.Interaction):
        # Validaciones básicas
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message(
                "Usá este comando dentro de un servidor.", ephemeral=True
            )

        # Usar la misma función is_admin, que ahora chequea manage_messages o admin
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                "Necesitas permiso de 'Gestionar Mensajes' o ser Admin.", ephemeral=True
            )

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Este comando solo funciona en canales de texto.", ephemeral=True
            )

        # Chequeo de permisos del bot (ahora necesita manage_messages)
        bot_member = interaction.guild.me
        if not bot_member:
             # Esto es raro, pero puede pasar si el bot fue kickeado justo ahora
             log.warning(f"No se pudo obtener el Member del bot en {interaction.guild.name}")
             return await interaction.response.send_message(
                 "Error: No pude validar mis propios permisos.", ephemeral=True
             )
        bot_perms = channel.permissions_for(bot_member)
        if not bot_perms.manage_messages:
            return await interaction.response.send_message(
                "Necesito permiso de **Gestionar mensajes** para limpiar este canal.", ephemeral=True
            )
        # También necesita leer el historial para poder borrar
        if not bot_perms.read_message_history:
             return await interaction.response.send_message(
                "Necesito permiso de **Leer historial de mensajes** para limpiar.", ephemeral=True
            )

        # Aviso inicial (cambiado)
        await interaction.response.send_message(
            f"🧹 Borrando mensajes recientes de **#{channel.name}**… (Esto puede tardar)",
            ephemeral=True
        )

        deleted_count = 0
        try:
            # Intentar borrar todos los mensajes posibles (limit=None intenta borrar los últimos 100 por defecto)
            # Pasamos check=lambda m: True para asegurar que intente borrar todos
            # NOTA: Esto NO borrará mensajes > 14 días
            deleted_messages = await channel.purge(limit=None, check=lambda m: True)
            deleted_count = len(deleted_messages)

            # Mensaje de confirmación en el canal (temporal) y en el followup
            confirmation_msg = await channel.send(f"✅ {deleted_count} mensajes borrados por <@{interaction.user.id}>.")
            
            # Borrar el mensaje de confirmación después de unos segundos
            await asyncio.sleep(5) # Esperar 5 segundos
            await confirmation_msg.delete()

            await interaction.followup.send(
                f"Listo ✅ — Se borraron {deleted_count} mensajes recientes de {channel.mention}.", ephemeral=True
            )

        except discord.Forbidden:
            log.error(f"Error de permisos al intentar purgar C:{channel.id}")
            await interaction.followup.send(
                "Error: No tengo permisos suficientes para borrar mensajes aquí.", ephemeral=True
            )
        except discord.HTTPException as e:
            log.exception(f"Error HTTP al purgar C:{channel.id}: {e}")
            await interaction.followup.send(
                f"Ocurrió un error de Discord al intentar borrar ({e.status}). Se borraron {deleted_count} mensajes antes del error.", ephemeral=True
            )
        except Exception as e:
             log.exception(f"Error inesperado al purgar C:{channel.id}: {e}")
             await interaction.followup.send(
                 f"Ocurrió un error inesperado. Se borraron {deleted_count} mensajes antes del error.", ephemeral=True
             )

# No olvides importar asyncio si no lo tienes ya en este archivo
import asyncio 

async def setup(bot: commands.Bot):
    # Añadir importación de asyncio si es necesario al principio del archivo
    # import asyncio 
    await bot.add_cog(ClearChatCog(bot))