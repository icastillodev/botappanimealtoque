from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from .guia_contenido import build_guia_embeds, chunk_guia_embeds_for_send


class InfoPublicaCog(commands.Cog, name="Economía info pública"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="aat-canjes", description="Qué podés canjear con Toque points (público).")
    async def aat_canjes(self, interaction: discord.Interaction):
        embeds = build_guia_embeds(self.bot)
        e = embeds[1]
        e.set_footer(text="Tip: guía completa con /aat-guia o ?guia; interactiva: /aat-ayuda.")
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="aat-ganar-puntos", description="Cómo ganar Toque points + qué te falta (público).")
    async def aat_ganar_puntos(self, interaction: discord.Interaction):
        embeds = build_guia_embeds(self.bot)
        e0 = embeds[0]
        extra = discord.Embed(title="📋 Ver qué te falta y reclamar", color=discord.Color.blurple())
        extra.description = (
            "**Público:** `?progreso` · `?diaria` · `?semanal` · `?inicial` · `?reclamar`\n"
            "**Privado (slash):** `/aat-progreso-iniciacion` · `/aat-progreso-diaria` · `/aat-progreso-semanal` · `/aat-reclamar`\n\n"
            "Si querés reclamar **solo** una categoría: `/aat-reclamar` eligiendo "
            "`inicial` / `diaria` / `semanal` / `semanal_especial` / `semanal_minijuegos`.\n"
            "Guía completa (embeds): `/aat-guia` · `?guia`. Interactiva: `/aat-ayuda`."
        )
        await interaction.response.send_message(embeds=[e0, extra])

    @app_commands.command(
        name="aat-guia",
        description="Guía completa del bot: recompensas, tienda, cartas y lista de comandos (público).",
    )
    async def aat_guia(self, interaction: discord.Interaction):
        chunks = chunk_guia_embeds_for_send(self.bot)
        n = len(chunks)
        head0 = f"📚 **Guía ({1}/{n})**" if n > 1 else None
        await interaction.response.send_message(content=head0, embeds=chunks[0])
        for i in range(1, n):
            await interaction.followup.send(
                content=f"📚 **Guía ({i + 1}/{n})**",
                embeds=chunks[i],
                ephemeral=False,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoPublicaCog(bot))

