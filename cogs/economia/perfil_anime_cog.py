# Wishlist (1–33), animes odiados (1–10), personajes favoritos (1–10) — visibles para todos.
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .db_manager import EconomiaDBManagerV2

log = logging.getLogger(__name__)


def _esc(s: str) -> str:
    return discord.utils.escape_markdown((s or "").strip()) or "—"


def _fmt_wishlist(rows: List[Dict[str, Any]], max_pos: int = 33) -> str:
    lines: List[str] = []
    for r in sorted(rows, key=lambda x: int(x["pos"])):
        p = int(r["pos"])
        if p > max_pos:
            continue
        t = str(r.get("title") or "").strip()
        if not t:
            continue
        lines.append(f"**{p}.** {_esc(t)}")
    return "\n".join(lines)


def _fmt_hated(rows: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for r in sorted(rows, key=lambda x: int(x["pos"])):
        t = str(r.get("title") or "").strip()
        if not t:
            continue
        lines.append(f"**{int(r['pos'])}.** {_esc(t)}")
    return "\n".join(lines)


def _fmt_chars(rows: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for r in sorted(rows, key=lambda x: int(x["pos"])):
        cn = str(r.get("char_name") or "").strip()
        an = str(r.get("anime_title") or "").strip()
        if not cn:
            continue
        lines.append(f"**{int(r['pos'])}.** {_esc(cn)} — *{_esc(an)}*")
    return "\n".join(lines)


class PerfilAnimeCog(commands.Cog, name="Perfil anime"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db

    # --- Wishlist ---
    @app_commands.command(name="aat-wishlist-ver", description="Ver la wishlist de anime de alguien (público).")
    @app_commands.describe(usuario="Usuario (por defecto vos)")
    async def wishlist_ver(self, interaction: discord.Interaction, usuario: Optional[discord.User] = None):
        target = usuario or interaction.user
        rows = self.db.wishlist_list(target.id)
        body = _fmt_wishlist(rows)
        emb = discord.Embed(
            title=f"Wishlist — {target.display_name}",
            description=body or "Sin entradas todavía.",
            color=discord.Color.fuchsia(),
        )
        emb.set_footer(text="Hasta 33 títulos · ordená por posición (1 = lo que más querés ver)")
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="aat-wishlist-set", description="Guardar o cambiar un título en tu wishlist (1–33).")
    @app_commands.describe(posicion="1 = el que más querés ver", titulo="Nombre del anime o manga")
    async def wishlist_set(
        self,
        interaction: discord.Interaction,
        posicion: app_commands.Range[int, 1, 33],
        titulo: str,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            self.db.wishlist_set(interaction.user.id, int(posicion), titulo)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        await interaction.followup.send("Guardado en tu wishlist.", ephemeral=True)

    @app_commands.command(name="aat-wishlist-quitar", description="Vaciar una posición de tu wishlist.")
    async def wishlist_quitar(self, interaction: discord.Interaction, posicion: app_commands.Range[int, 1, 33]):
        self.db.wishlist_remove(interaction.user.id, int(posicion))
        await interaction.response.send_message(f"Posición **{posicion}** vaciada.", ephemeral=True)

    # --- Odiados ---
    @app_commands.command(name="aat-hated-ver", description="Ver los animes que más odia alguien (público).")
    @app_commands.describe(usuario="Usuario (por defecto vos)")
    async def hated_ver(self, interaction: discord.Interaction, usuario: Optional[discord.User] = None):
        target = usuario or interaction.user
        rows = self.db.hated_list(target.id)
        body = _fmt_hated(rows)
        emb = discord.Embed(
            title=f"Animes odiados — {target.display_name}",
            description=body or "Sin entradas todavía.",
            color=discord.Color.dark_red(),
        )
        emb.set_footer(text="Hasta 10 títulos")
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="aat-hated-set", description="Guardar o cambiar un anime odiado (1–10).")
    async def hated_set(
        self,
        interaction: discord.Interaction,
        posicion: app_commands.Range[int, 1, 10],
        titulo: str,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            self.db.hated_set(interaction.user.id, int(posicion), titulo)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        await interaction.followup.send("Guardado.", ephemeral=True)

    @app_commands.command(name="aat-hated-quitar", description="Vaciar una posición de odiados.")
    async def hated_quitar(self, interaction: discord.Interaction, posicion: app_commands.Range[int, 1, 10]):
        self.db.hated_remove(interaction.user.id, int(posicion))
        await interaction.response.send_message(f"Posición **{posicion}** vaciada.", ephemeral=True)

    # --- Personajes ---
    @app_commands.command(name="aat-chars-ver", description="Ver el top de personajes favoritos (público).")
    @app_commands.describe(usuario="Usuario (por defecto vos)")
    async def chars_ver(self, interaction: discord.Interaction, usuario: Optional[discord.User] = None):
        target = usuario or interaction.user
        rows = self.db.fav_char_list(target.id)
        body = _fmt_chars(rows)
        emb = discord.Embed(
            title=f"Personajes favoritos — {target.display_name}",
            description=body or "Sin entradas todavía.",
            color=discord.Color.teal(),
        )
        emb.set_footer(text="Hasta 10 · en cada fila: personaje — anime")
        await interaction.response.send_message(embed=emb)

    @app_commands.command(
        name="aat-chars-set",
        description="Guardar personaje favorito en una posición (1–10) + anime de origen.",
    )
    async def chars_set(
        self,
        interaction: discord.Interaction,
        posicion: app_commands.Range[int, 1, 10],
        personaje: str,
        anime: str,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            self.db.fav_char_set(interaction.user.id, int(posicion), personaje, anime)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        await interaction.followup.send("Guardado.", ephemeral=True)

    @app_commands.command(name="aat-chars-quitar", description="Vaciar una posición de personajes.")
    async def chars_quitar(self, interaction: discord.Interaction, posicion: app_commands.Range[int, 1, 10]):
        self.db.fav_char_remove(interaction.user.id, int(posicion))
        await interaction.response.send_message(f"Posición **{posicion}** vaciada.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PerfilAnimeCog(bot))
