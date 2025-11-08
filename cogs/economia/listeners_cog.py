# cogs/economia/listeners_cog.py
import discord
from discord.ext import commands
import datetime
import logging

from .db_manager import EconomiaDBManagerV2 # <--- MODIFICADO

class EconomiaListenersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db # <--- MODIFICADO
        self.config = bot.task_config
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.info("Cog de Listeners de Economía cargado.")

    def cog_unload(self):
        self.log.info("EconomiaListenersCog descargado.")

    def _get_channel_id(self, name: str) -> int:
        return self.config.get("channels", {}).get(name, 0)
        
    def _get_message_id(self, name: str) -> int:
        return self.config.get("messages", {}).get(name, 0)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        user_id = message.author.id
        channel_id = message.channel.id
        
        if not hasattr(self, 'db'): return

        fecha, semana = self.db.get_current_date_keys()

        if channel_id == self._get_channel_id("presentacion"):
            self.db.update_task_inicial(user_id, "presentacion")
        if channel_id == self._get_channel_id("general"):
            self.db.update_task_inicial(user_id, "general_mensaje")
            self.db.update_task_diaria(user_id, "general_mensajes", fecha, 1)
        if channel_id in [self._get_channel_id("anime_debate"), self._get_channel_id("manga_debate")]:
            self.db.update_task_diaria(user_id, "debate_actividad", fecha, 1)
        if channel_id in [self._get_channel_id("fanarts"), self._get_channel_id("cosplays"), self._get_channel_id("memes")]:
            self.db.update_task_diaria(user_id, "media_actividad", fecha, 1)
            self.db.update_task_semanal(user_id, "media_escrito", semana, 1)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or (payload.member and payload.member.bot):
            return
        if not hasattr(self, 'db'): return
            
        user_id = payload.user_id
        channel_id = payload.channel_id
        message_id = payload.message_id
        fecha, semana = self.db.get_current_date_keys()

        if channel_id == self._get_channel_id("autorol"):
            if message_id == self._get_message_id("pais"):
                self.db.update_task_inicial(user_id, "reaccion_pais")
            elif message_id == self._get_message_id("rol"):
                self.db.update_task_inicial(user_id, "reaccion_rol")
        if channel_id == self._get_channel_id("social"):
            self.db.update_task_inicial(user_id, "reaccion_social")
        if channel_id == self._get_channel_id("reglas"):
            self.db.update_task_inicial(user_id, "reaccion_reglas")
        if channel_id in [self._get_channel_id("anime_debate"), self._get_channel_id("manga_debate")]:
            self.db.update_task_diaria(user_id, "debate_actividad", fecha, 1)
        if channel_id in [self._get_channel_id("fanarts"), self._get_channel_id("cosplays"), self._get_channel_id("memes")]:
            self.db.update_task_diaria(user_id, "media_actividad", fecha, 1)
        if channel_id == self._get_channel_id("videos"):
            self.db.update_task_semanal(user_id, "videos_reaccion", semana, 1)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if not hasattr(self, 'db'): return
        if thread.owner.bot:
            return
            
        user_id = thread.owner_id
        channel_id = thread.parent_id
        fecha, semana = self.db.get_current_date_keys()
        if channel_id in [self._get_channel_id("anime_debate"), self._get_channel_id("manga_debate")]:
            self.db.update_task_diaria(user_id, "debate_actividad", fecha, 1)
            self.db.update_task_semanal(user_id, "debate_post", semana, 1)

async def setup(bot):
    if not bot.task_config:
        logging.getLogger("cogs.economia.listeners_cog").error("No se pudo cargar EconomiaListenersCog, falta task_config.")
        return
    await bot.add_cog(EconomiaListenersCog(bot))