# cogs/check_tareas/cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
from cogs.economia.db_manager import EconomiaDBManagerV2
from typing import Dict, Any

class CheckTareasCog(commands.Cog, name="Check Tareas Antiguas"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(self.__class__.__name__)
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self.config = bot.task_config
        self.log.info("Cog de Check Tareas cargado.")

    def _get_channel_id(self, name: str) -> int:
        return self.config.get("channels", {}).get(name, 0)
        
    def _get_message_id(self, name: str) -> int:
        return self.config.get("messages", {}).get(name, 0)

    # --- ¡¡¡FUNCIÓN QUE FALTABA (ARREGLO 1)!!! ---
    def _check_task(self, progress_value: int, required_value: int = 1) -> str:
        """Devuelve un emoji de check o cross si se alcanzó el valor requerido."""
        return "✅" if progress_value >= required_value else "❌"

    # --- Funciones de Escaneo ---
    
    async def _check_reaction_on_message(self, channel_id: int, message_id: int, user_id: int) -> bool:
        """Comprueba si un usuario reaccionó a un mensaje específico."""
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            message = await channel.fetch_message(message_id)
            for reaction in message.reactions:
                async for user in reaction.users():
                    if user.id == user_id:
                        return True
        except (discord.NotFound, discord.Forbidden):
            self.log.warning(f"No se pudo verificar la reacción en el mensaje {message_id} del canal {channel_id}")
            return False
        return False

    async def _check_reaction_in_channel(self, channel_id: int, user_id: int) -> bool:
        """Comprueba si un usuario reaccionó a CUALQUIER mensaje en un canal (limite 20)."""
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            async for message in channel.history(limit=20): # Escanea los últimos 20 mensajes
                for reaction in message.reactions:
                    async for user in reaction.users():
                        if user.id == user_id:
                            return True
        except (discord.NotFound, discord.Forbidden):
            self.log.warning(f"No se pudo verificar reacciones en el canal {channel_id}")
            return False
        return False

    async def _check_message_in_channel(self, channel_id: int, user_id: int) -> bool:
        """Comprueba si un usuario escribió CUALQUIER mensaje en un canal (limite 200)."""
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            async for message in channel.history(limit=200): # Escanea los últimos 200 mensajes
                if message.author.id == user_id:
                    return True
        except (discord.NotFound, discord.Forbidden):
            self.log.warning(f"No se pudo verificar mensajes en el canal {channel_id}")
            return False
        return False

    # --- El Comando ---

    @app_commands.command(name="aat_verificar_antiguas", description="Escanea el historial para encontrar tus tareas de iniciación ya completadas.")
    @app_commands.checks.cooldown(1, 3600, key=lambda i: i.user.id) # 1 vez por hora por usuario
    async def verificar_antiguas(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        prog = self.db.get_progress_inicial(user_id)
        if prog['completado'] == 1:
            await interaction.followup.send("¡Ya has completado y reclamado tus tareas de iniciación!", ephemeral=True)
            return

        # 'followup' es necesario porque ya hicimos 'defer'
        await interaction.followup.send("Verificando tu historial... Esto puede tardar hasta un minuto.", ephemeral=True)
        
        # 1. Tarea 'presentacion'
        if prog['presentacion'] == 0:
            if await self._check_message_in_channel(self._get_channel_id("presentacion"), user_id):
                self.db.update_task_inicial(user_id, "presentacion")

        # 2. Tarea 'reaccion_pais'
        if prog['reaccion_pais'] == 0:
            if await self._check_reaction_on_message(self._get_channel_id("autorol"), self._get_message_id("pais"), user_id):
                self.db.update_task_inicial(user_id, "reaccion_pais")

        # 3. Tarea 'reaccion_rol'
        if prog['reaccion_rol'] == 0:
            if await self._check_reaction_on_message(self._get_channel_id("autorol"), self._get_message_id("rol"), user_id):
                self.db.update_task_inicial(user_id, "reaccion_rol")
        
        # 4. Tarea 'reaccion_social'
        if prog['reaccion_social'] == 0:
            if await self._check_reaction_in_channel(self._get_channel_id("social"), user_id):
                self.db.update_task_inicial(user_id, "reaccion_social")
        
        # 5. Tarea 'reaccion_reglas'
        if prog['reaccion_reglas'] == 0:
            if await self._check_reaction_in_channel(self._get_channel_id("reglas"), user_id):
                self.db.update_task_inicial(user_id, "reaccion_reglas")
        
        # 6. Tarea 'general_mensaje'
        if prog['general_mensaje'] == 0:
            if await self._check_message_in_channel(self._get_channel_id("general"), user_id):
                self.db.update_task_inicial(user_id, "general_mensaje")

        # --- Mostrar el reporte final ---
        new_prog = self.db.get_progress_inicial(user_id)
        
        embed_final = discord.Embed(title="Verificación de Tareas Completada", color=discord.Color.blue())
        desc_final = (
            f"{self._check_task(new_prog['presentacion'])} Escribir en `#presentacion`\n"
            f"{self._check_task(new_prog['reaccion_pais'])} Reaccionar al post de 'País' (`#autorol`)\n"
            f"{self._check_task(new_prog['reaccion_rol'])} Reaccionar al post de 'Rol' (`#autorol`)\n"
            f"{self._check_task(new_prog['reaccion_social'])} Reaccionar en `#redes-sociales`\n"
            f"{self._check_task(new_prog['reaccion_reglas'])} Reaccionar en `#reglas`\n"
            f"{self._check_task(new_prog['general_mensaje'])} Escribir 1 vez en `#general`\n\n"
        )
        
        if all(new_prog[key] >= 1 for key in ['presentacion', 'reaccion_pais', 'reaccion_rol', 'reaccion_social', 'reaccion_reglas', 'general_mensaje']):
            desc_final += "✅ **¡Felicidades!** Se ha verificado que completaste todas las tareas.\n"
            desc_final += "Ahora puedes usar `/aat_reclamar inicial` para obtener tu recompensa."
        else:
            desc_final += "Se han actualizado tus tareas. Sigue completando las que te faltan (marcadas con ❌)."

        embed_final.description = desc_final
        
        # Usamos 'edit_original_response' para editar el mensaje "Verificando..."
        await interaction.edit_original_response(content=None, embed=embed_final)

    @verificar_antiguas.error
    async def on_verificar_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Manejador de error para el cooldown."""
        
        # --- ¡¡¡ARREGLO 2!!! ---
        # Cambiado a 'followup.send' para evitar el 'InteractionResponded'
        if isinstance(error, app_commands.CommandOnCooldown):
            minutos = int(error.retry_after / 60)
            await interaction.followup.send(f"Este comando es muy pesado. Solo puedes usarlo una vez por hora. Inténtalo de nuevo en {minutos} minutos.", ephemeral=True)
        
        # Esto maneja el 'AttributeError' que vimos
        elif isinstance(error, app_commands.CommandInvokeError):
            self.log.error(f"Error en /aat_verificar_antiguas: {error.original}")
            await interaction.followup.send(f"Ocurrió un error inesperado al verificar: {error.original}", ephemeral=True)
        
        else:
            self.log.error(f"Error no manejado en /aat_verificar_antiguas: {error}")
            await interaction.followup.send("Ocurrió un error inesperado.", ephemeral=True)

# Función setup obligatoria
async def setup(bot):
    await bot.add_cog(CheckTareasCog(bot))