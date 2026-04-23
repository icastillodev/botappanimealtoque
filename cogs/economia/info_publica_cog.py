from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from .guia_contenido import build_guia_embeds


class InfoPublicaCog(commands.Cog, name="Economía info pública"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="aat_canjes", description="Qué podés canjear con puntos (público).")
    async def aat_canjes(self, interaction: discord.Interaction):
        embeds = build_guia_embeds(self.bot)
        e = embeds[1]
        e.set_footer(text="Tip: para la guía completa usá /aat_ayuda (se puede usar en #general).")
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="aat_ganar_puntos", description="Cómo ganar puntos + cómo ver qué te falta (público).")
    async def aat_ganar_puntos(self, interaction: discord.Interaction):
        embeds = build_guia_embeds(self.bot)
        e0 = embeds[0]
        extra = discord.Embed(title="📋 Ver qué te falta y reclamar", color=discord.Color.blurple())
        extra.description = (
            "**Público:** `!progreso` · `!diaria` · `!semanal` · `!inicial` · `!reclamar`\n"
            "**Privado (slash):** `/aat_progreso_iniciacion` · `/aat_progreso_diaria` · `/aat_progreso_semanal` · `/aat_reclamar`\n\n"
            "Si querés reclamar **solo** una categoría: `/aat_reclamar` eligiendo "
            "`inicial` / `diaria` / `semanal` / `semanal_especial` / `semanal_minijuegos`.\n"
            "Guía completa: `/aat_ayuda`."
        )
        await interaction.response.send_message(embeds=[e0, extra])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoPublicaCog(bot))

