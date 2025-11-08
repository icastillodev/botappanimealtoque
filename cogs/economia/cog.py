# cogs/economia/cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List, Dict, Any

from .db_manager import EconomiaDBManager
# --- Importamos nuestros grupos ---
from .tareas_group import TareasGroup
from .admin_group import AdminGroup 
# --- ¡Importamos el Listener para poder cargarlo! ---
from .listeners import EconomiaListenersCog

class EconomiaCog(commands.Cog):
    
    # --- La definición del grupo se movió de aquí ---

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManager = bot.economia_db
        self.log = logging.getLogger(self.__class__.__name__)
        
        # --- ¡¡¡AQUÍ ESTÁ EL ARREGLO!!! ---
        # Definimos 'aat_group' como una variable de INSTANCIA (con 'self.')
        # Esto evita que discord.py la registre automáticamente.
        self.aat_group = app_commands.Group(name="aat", description="Comandos de economía y cartas")
        
        # --- Adjuntamos los grupos al GRUPO PADRE 'aat' ---
        self.aat_group.add_command(TareasGroup(bot, self.db))
        self.aat_group.add_command(AdminGroup(bot, self.db)) 
        
        # (Aquí es donde añadiremos cartas_group, tienda_group, etc.)

    # --- Lógica de Carga ---
    async def cog_load(self):
        """Esta función se llama cuando el cog se carga."""
        # 1. Carga el cog "espía" (listeners)
        if self.bot.task_config: 
            await self.bot.add_cog(EconomiaListenersCog(self.bot))
        else:
            self.log.error("No se pudo cargar EconomiaListenersCog porque la task_config es None.")
        
        # 2. Añade el grupo /aat al árbol de comandos
        #    (Esta es ahora la ÚNICA vez que se registra)
        self.bot.tree.add_command(self.aat_group)
        self.log.info("EconomiaCog cargado y comando /aat añadido al árbol.")

    # --- Lógica de Descarga ---
    async def cog_unload(self):
        """Esta función se llama cuando el cog se descarga (o recarga)."""
        # 1. Descarga el cog "espía"
        try:
            await self.bot.remove_cog("EconomiaListenersCog")
        except Exception:
            pass # Si hay un error (ej: no estaba cargado), lo ignoramos

        # 2. Borra el grupo /aat del árbol de comandos
        self.bot.tree.remove_command(self.aat_group.name, type=discord.AppCommandType.chat_input)
        self.log.info("EconomiaCog descargado y comando /aat quitado del árbol.")