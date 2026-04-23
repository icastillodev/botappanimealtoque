from __future__ import annotations

import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from .guia_contenido import build_guia_embeds, chunk_guia_embeds_for_send

log = logging.getLogger(__name__)


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
        # Responder antes de 3 s; el envío de varios mensajes va en followups.
        await interaction.response.defer(thinking=False)
        try:
            chunks = chunk_guia_embeds_for_send(self.bot)
        except Exception:
            log.exception("aat-guia: chunk_guia_embeds_for_send")
            await interaction.followup.send(
                "No pude armar la guía ahora (error interno). Probá `?guia` o avisá al staff.",
                ephemeral=True,
            )
            return
        if not chunks or any(len(part) == 0 for part in chunks):
            await interaction.followup.send(
                "La guía salió vacía (revisá la configuración del bot).",
                ephemeral=True,
            )
            return
        n = len(chunks)
        try:
            for i, part in enumerate(chunks):
                head = f"📚 **Guía ({i + 1}/{n})**" if n > 1 else None
                await interaction.followup.send(content=head, embeds=part, ephemeral=False)
        except discord.HTTPException as e:
            log.warning("aat-guia: envío falló: %s", e)
            hint = ""
            raw_bc = (os.getenv("BOT_CHANNEL_ID") or "").strip()
            if raw_bc.isdigit():
                hint = f" Probá también en <#{raw_bc}> (canal de comandos del bot)."
            await interaction.followup.send(
                "Discord rechazó parte del envío (faltan **Incrustar enlaces** / **Insertar enlaces** en este canal, "
                "o el mensaje supera límites). Pedí al staff que revise permisos del rol del bot."
                + hint,
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoPublicaCog(bot))

