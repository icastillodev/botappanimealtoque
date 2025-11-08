# cogs/reaction_limiter.py
import discord
from discord.ext import commands
import logging

class ReactionLimiterCog(commands.Cog, name="Limitador de Reacciones"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(self.__class__.__name__)
        
        # Cargamos los IDs de la config del bot (que ya cargó main.py)
        try:
            self.target_channel_id = bot.task_config["channels"]["autorol"]
            self.target_message_id = bot.task_config["messages"]["pais"]
            self.log.info("Limitador de Reacciones cargado. Apuntando a la reacción de 'País'.")
        except KeyError:
            self.log.error("¡No se pudieron cargar los IDs para el Limitador de Reacciones! El cog no funcionará.")
            self.target_channel_id = 0
            self.target_message_id = 0

    @commands.Cog.listener("on_raw_reaction_add")
    async def on_reaction_add(self, payload: discord.RawReactionActionEvent):
        # 1. Ignorar bots, DMs, y si la config falló
        if not payload.guild_id or (payload.member and payload.member.bot):
            return
        if self.target_channel_id == 0 or self.target_message_id == 0:
            return

        # 2. Ignorar si no es el canal o el mensaje que nos importa
        if payload.channel_id != self.target_channel_id:
            return
        if payload.message_id != self.target_message_id:
            return
        
        # ¡Es el mensaje correcto!
        try:
            channel = self.bot.get_channel(payload.channel_id)
            if not channel:
                channel = await self.bot.fetch_channel(payload.channel_id)
                
            message = await channel.fetch_message(payload.message_id)
            
            # Asegurarnos de tener el objeto 'user'
            user = payload.member
            if not user:
                user = await message.guild.fetch_member(payload.user_id)

            # 3. Iterar sobre TODAS las reacciones del mensaje
            for reaction in message.reactions:
                # 4. Ignorar la reacción que el usuario ACABA de añadir
                if str(reaction.emoji) == str(payload.emoji):
                    continue

                # 5. Revisar si el usuario está en la lista de las OTRAS reacciones
                async for reactor in reaction.users():
                    if reactor.id == user.id:
                        # ¡Lo encontramos! Ya tenía otra reacción.
                        # Le quitamos la reacción VIEJA para que se quede la NUEVA.
                        self.log.debug(f"Usuario {user.name} cambió su reacción. Quitamos la vieja ({reaction.emoji}).")
                        await message.remove_reaction(reaction.emoji, user)
                        # Como solo puede tener una, terminamos
                        return 
                        
        except discord.NotFound:
            self.log.warning(f"No se pudo encontrar el mensaje {self.target_message_id} para limitar reacciones.")
        except discord.Forbidden:
            self.log.warning(f"No tengo permisos para 'Gestionar Mensajes' en <#{self.target_channel_id}> para quitar reacciones.")
        except Exception as e:
            self.log.exception(f"Error inesperado en el limitador de reacciones: {e}")

# --- ¡¡¡ESTA ES LA PARTE IMPORTANTE!!! ---
# Función setup obligatoria para este archivo
async def setup(bot):
    await bot.add_cog(ReactionLimiterCog(bot))