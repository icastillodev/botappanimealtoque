# Top personal de anime/manga (1–30), bonos configurables por .env.
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from .db_manager import EconomiaDBManagerV2

log = logging.getLogger(__name__)


def _format_rows(rows: List[Dict[str, Any]], max_pos: int = 30) -> str:
    if not rows:
        return ""
    lines: List[str] = []
    for r in sorted(rows, key=lambda x: int(x["pos"])):
        p = int(r["pos"])
        if p > max_pos:
            continue
        t = str(r.get("title") or "").strip()
        if not t:
            continue
        lines.append(f"**{p}.** {t}")
    return "\n".join(lines)


def _embed_top_for(
    bot: commands.Bot,
    target: discord.User,
    rows: List[Dict[str, Any]],
    *,
    viewer_is_target: bool,
) -> discord.Embed:
    title = f"Top anime — {target.display_name}"
    if not rows:
        desc = (
            "Todavía **no cargó** ninguna entrada en el top."
            if not viewer_is_target
            else "Todavía **no cargaste** tu top. Usá `/aat_anime_top_set` o `/aat_anime_top_guia`."
        )
        return discord.Embed(title=title, description=desc, color=discord.Color.light_grey())

    body = _format_rows(rows)
    if len(body) > 3900:
        body = body[:3890] + "\n…"

    n = len(rows)
    embed = discord.Embed(
        title=title,
        description=body,
        color=discord.Color.dark_teal(),
    )
    embed.set_footer(text=f"{n} entrada(s) guardada(s) · máx. 30 posiciones")
    return embed


class AnimeTopCog(commands.Cog, name="Anime top"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db

    def _bonuses(self) -> Tuple[int, int]:
        rw = (getattr(self.bot, "task_config", None) or {}).get("rewards") or {}
        return int(rw.get("anime_top10_bonus") or 0), int(rw.get("anime_top30_bonus") or 0)

    @app_commands.command(name="aat_anime_top_ver", description="Ver el top anime de un usuario (por defecto vos).")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def anime_top_ver(self, interaction: discord.Interaction, usuario: Optional[discord.User] = None):
        target = usuario or interaction.user
        rows = self.db.anime_top_list(target.id)
        emb = _embed_top_for(self.bot, target, rows, viewer_is_target=target.id == interaction.user.id)
        await interaction.response.send_message(embed=emb, ephemeral=(target.id == interaction.user.id))

    @app_commands.command(name="aat_anime_top_set", description="Guardar o cambiar un título en una posición (1–30).")
    @app_commands.describe(posicion="Del 1 al 30 (1 = favorito)", titulo="Nombre del anime o manga")
    async def anime_top_set(
        self,
        interaction: discord.Interaction,
        posicion: app_commands.Range[int, 1, 30],
        titulo: str,
    ):
        t = (titulo or "").strip()
        if len(t) > 200:
            await interaction.response.send_message("El título es demasiado largo (máx. 200 caracteres).", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            self.db.anime_top_set(interaction.user.id, int(posicion), t)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        b10, b30 = self._bonuses()
        bonus_msgs = self.db.apply_anime_milestones(interaction.user.id, b10, b30)
        rows = self.db.anime_top_list(interaction.user.id)
        emb = _embed_top_for(self.bot, interaction.user, rows, viewer_is_target=True)
        extra = "\n".join(bonus_msgs) if bonus_msgs else ""
        await interaction.followup.send(
            content=("Guardado." + ("\n" + extra if extra else "")),
            embed=emb,
            ephemeral=True,
        )

    @app_commands.command(name="aat_anime_top_quitar", description="Borrar el título de una posición.")
    @app_commands.describe(posicion="Número de posición a vaciar (1–30)")
    async def anime_top_quitar(self, interaction: discord.Interaction, posicion: app_commands.Range[int, 1, 30]):
        self.db.anime_top_remove(interaction.user.id, int(posicion))
        await interaction.response.send_message(f"Posición **{posicion}** vaciada.", ephemeral=True)

    @app_commands.command(name="aat_anime_top_guia", description="Mini guía para armar tu top.")
    async def anime_top_guia(self, interaction: discord.Interaction):
        b10, b30 = self._bonuses()
        emb = discord.Embed(title="Guía rápida — Top anime", color=discord.Color.blue())
        emb.description = (
            "• Pensá **10** obras que más te gustaron (orden importa: **1** = la número uno).\n"
            "• Si querés, completá hasta **30** con el resto de favoritos.\n"
            "• Podés **cambiar** cualquier posición cuando quieras con `/aat_anime_top_set`.\n"
            "• `/aat_anime_top_quitar` deja vacía una casilla.\n"
            f"• **Bonos únicos**: top 10 completo → **{b10}** pts; top 30 completo → **{b30}** pts extra.\n"
            "• Ver el de otro: `/aat_anime_top_ver` eligiendo usuario (mensaje público)."
        )
        await interaction.response.send_message(embed=emb, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnimeTopCog(bot))
