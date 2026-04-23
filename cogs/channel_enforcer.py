# cogs/channel_enforcer.py
import asyncio
import os
import unicodedata

import discord
from discord.ext import commands


def _general_prefix_command_token(message: discord.Message) -> str:
    """Primer token tras '?' (sin acentos, minúsculas). Ej.: guía → guia."""
    raw = (message.content or "").strip()
    if not raw.startswith("?") or len(raw) <= 1:
        return ""
    rest = raw[1:].strip()
    if not rest:
        return ""
    first = rest.split()[0]
    nk = unicodedata.normalize("NFKD", first)
    ascii_fold = "".join(ch for ch in nk if not unicodedata.combining(ch))
    return ascii_fold.lower()

# Comandos ? permitidos en #general (primer token tras "?").
# No: reclamar, progreso, diarias, tienda, guía larga, rankings, etc. (van al canal del bot o slash).
# Sí: juego en vivo (roll, cartas), oráculo, trivia, impostor, resumen corto de comandos.
PUBLIC_GENERAL_PREFIX_COMMANDS = frozenset(
    {
        "comandos",
        "aat",
        "cmds",
        "cmd",
        "ayudabot",
        "roll",
        "rollp",
        "rollc",
        "rollpaceptar",
        "rollp_aceptar",
        "abrir",
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
        "r",
        "triviatop",
        "toptrivia",
        "ranktrivia",
        "triviami",
        "mitrivia",
        "posiciontrivia",
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
            if message.content.startswith("?") and len(message.content) > 1 and not message.content.startswith("? "):
                first = _general_prefix_command_token(message)
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
                        f"🚫 **{message.author.mention}, en #general solo algunos `?`** (roll, rollp/rollc, abrir/usar cartas, oráculo, trivia, impostor, `?comandos`).\n"
                        f"**Reclamar, progreso, diaria, tienda, guía…** → canal de comandos <#{self.bot_channel_id}> "
                        f"o slash (`/aat-reclamar`, `/aat-progreso-*`, `/aat-guia`, etc.)."
                    ),
                    color=discord.Color.red()
                )
                
                # 3. Borrar la advertencia después de 5 segundos
                await message.channel.send(embed=embed, delete_after=5)

async def setup(bot):
    await bot.add_cog(ChannelEnforcerCog(bot))