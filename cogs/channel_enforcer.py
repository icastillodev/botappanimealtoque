# cogs/channel_enforcer.py
import discord
from discord.ext import commands
import os
import asyncio

# Comandos ! permitidos en #general (primer token tras "!")
PUBLIC_GENERAL_PREFIX_COMMANDS = frozenset(
    {
        "comandos",
        "aat",
        "cmds",
        "cmd",
        "ayudabot",
        "ayuda",
        "puntos",
        "inventario",
        "top",
        "rank",
        "ranking",
        "reclamar",
        "progreso",
        "diaria",
        "daily",
        "semanal",
        "weekly",
        "inicial",
        "starter",
        "iniciacion",
        "abrir",
        "miscartas",
        "catalogo",
        "usar",
        "usarcarta",
        "impostor",
        "buscoimpostor",
        "busco",
        "lobbys",
        "cartelera",
        "pregunta",
        "consulta",
        "8ball",
        "bola",
        "oraculo",
        "animetop",
        # Trivia (en #general)
        "respuestapregunta",
        "triviaresp",
        "rtrivia",
        # Rolls + guías públicas
        "roll",
        "canjes",
        "tienda",
        "recompensas",
        "ganarpuntos",
        "comoganar",
        "guia",
    }
)


class ChannelEnforcerCog(commands.Cog, name="Limpieza de Chat"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        try:
            self.general_id = int(os.getenv("GENERAL_CHANNEL_ID"))
            self.bot_channel_id = int(os.getenv("BOT_CHANNEL_ID"))
        except (TypeError, ValueError):
            print("❌ Error: Faltan GENERAL_CHANNEL_ID o BOT_CHANNEL_ID en el .env")
            self.general_id = 0
            self.bot_channel_id = 0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if self.general_id == 0 or self.bot_channel_id == 0:
            return

        # Si estamos en el canal General
        if message.channel.id == self.general_id:
            
            # Verificar si es un comando de prefijo
            if message.content.startswith("!") and len(message.content) > 1 and not message.content.startswith("! "):
                first = message.content[1:].split()[0].lower()
                if first in PUBLIC_GENERAL_PREFIX_COMMANDS:
                    return
                # 1. Borrar el mensaje del usuario
                try:
                    await message.delete()
                except discord.Forbidden:
                    return

                # 2. Enviar Embed al CANAL (no DM)
                embed = discord.Embed(
                    description=(
                        f"🚫 **{message.author.mention}, en #general no se usan comandos con `!`.**\n"
                        f"Usá los **comandos /** en <#{self.bot_channel_id}> o donde el staff indique "
                        f"(economía: `/aat_ayuda`, cartas: `/usar`)."
                    ),
                    color=discord.Color.red()
                )
                
                # 3. Borrar la advertencia después de 5 segundos
                await message.channel.send(embed=embed, delete_after=5)

async def setup(bot):
    await bot.add_cog(ChannelEnforcerCog(bot))