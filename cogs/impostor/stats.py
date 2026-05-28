# Ranking y estadísticas personales de Impostor.
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from . import core
from .engine import PHASE_END, PHASE_IDLE, PHASE_ROLES, PHASE_TURNS, PHASE_VOTE
from .slots import format_slots_label

log = logging.getLogger(__name__)


def _lobby_status_label(lobby) -> str:
    if lobby.phase == PHASE_END:
        return "fin de partida"
    if lobby.in_progress:
        if lobby.phase == PHASE_ROLES:
            return "roles"
        if lobby.phase == PHASE_TURNS:
            return f"ronda {lobby.round_num} (pistas)"
        if lobby.phase == PHASE_VOTE:
            return f"ronda {lobby.round_num} (voto)"
        return "en partida"
    if lobby.phase == PHASE_IDLE:
        return "lobby (esperando)"
    return lobby.phase or "—"


def _build_activos_embed(lobbies: List) -> discord.Embed:
    embed = discord.Embed(
        title="🎭 Lobbies Impostor activos",
        color=discord.Color.blurple(),
    )
    if not lobbies:
        embed.description = "No hay salas activas en este momento."
        return embed
    lines = []
    for lb in sorted(lobbies, key=lambda x: (x.in_progress, x.lobby_name)):
        slots = format_slots_label(lb.all_players_count, lb.max_slots)
        open_txt = "abierto" if lb.is_open else "cerrado"
        lines.append(
            f"• **{lb.lobby_name}** ({slots}, {open_txt}) — {_lobby_status_label(lb)} — <#{lb.channel_id}>"
        )
    embed.description = "\n".join(lines[:20])
    if len(lobbies) > 20:
        embed.set_footer(text=f"Mostrando 20 de {len(lobbies)} lobbies.")
    return embed


class ImpostorStatsCog(commands.Cog, name="ImpostorStats"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _db(self):
        return getattr(self.bot, "economia_db", None)

    def _embed_stats(self, target: discord.abc.User, s: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"📊 Impostor — {target.display_name}",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Partidas jugadas", value=str(s["games_played"]), inline=True)
        embed.add_field(name="Como social", value=str(s["games_social"]), inline=True)
        embed.add_field(name="Como impostor", value=str(s["games_impostor"]), inline=True)
        embed.add_field(name="Victorias social", value=str(s["wins_social"]), inline=True)
        embed.add_field(name="Victorias impostor", value=str(s["wins_impostor"]), inline=True)
        return embed

    @commands.command(name="impostorstats", aliases=["impstats", "misimpostor"])
    async def impostor_stats_prefix(self, ctx: commands.Context, miembro: Optional[discord.Member] = None):
        db = self._db()
        if not db:
            return await ctx.send("❌ Base de datos no disponible.")
        target = miembro or ctx.author
        s = db.get_impostor_stats(target.id)
        await ctx.send(embed=self._embed_stats(target, s))

    @app_commands.command(name="impostor-stats", description="Tus estadísticas en Impostor.")
    @app_commands.describe(usuario="Ver stats de otro usuario (opcional).")
    async def impostor_stats(
        self,
        interaction: discord.Interaction,
        usuario: Optional[discord.Member] = None,
    ):
        db = self._db()
        if not db:
            return await interaction.response.send_message(
                "❌ Base de datos no disponible.", ephemeral=True
            )
        target = usuario or interaction.user
        s = db.get_impostor_stats(target.id)
        await interaction.response.send_message(
            embed=self._embed_stats(target, s), ephemeral=True
        )

    @app_commands.command(name="impostor-ranking", description="Top global de Impostor.")
    @app_commands.describe(
        tipo="Qué ranking ver",
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Victorias como impostor", value="wins_impostor"),
            app_commands.Choice(name="Victorias como social", value="wins_social"),
            app_commands.Choice(name="Partidas jugadas", value="games_played"),
            app_commands.Choice(name="Partidas como impostor", value="games_impostor"),
            app_commands.Choice(name="Partidas como social", value="games_social"),
        ]
    )
    async def impostor_ranking(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
    ):
        db = self._db()
        if not db:
            return await interaction.response.send_message(
                "❌ Base de datos no disponible.", ephemeral=True
            )
        col = tipo.value
        rows = db.get_impostor_leaderboard(col, limit=15)
        labels = {
            "wins_impostor": "Victorias como impostor",
            "wins_social": "Victorias como social",
            "games_played": "Partidas jugadas",
            "games_impostor": "Partidas como impostor",
            "games_social": "Partidas como social",
        }
        if not rows:
            return await interaction.response.send_message(
                f"Aún no hay datos para **{labels.get(col, col)}**.",
                ephemeral=True,
            )
        await interaction.response.send_message(embed=self._embed_ranking(col, rows))

    def _embed_ranking(self, col: str, rows: list) -> discord.Embed:
        labels = {
            "wins_impostor": "Victorias como impostor",
            "wins_social": "Victorias como social",
            "games_played": "Partidas jugadas",
            "games_impostor": "Partidas como impostor",
            "games_social": "Partidas como social",
        }
        lines = []
        for i, (uid, val) in enumerate(rows, start=1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"**{i}.**")
            lines.append(f"{medal} <@{uid}> — **{val}**")
        return discord.Embed(
            title=f"🏆 Ranking — {labels.get(col, col)}",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )

    @commands.command(name="impostorrang", aliases=["impostorranking", "topimpostor", "rankingimpostor"])
    async def impostor_ranking_prefix(
        self, ctx: commands.Context, tipo: str = "wins_impostor"
    ):
        db = self._db()
        if not db:
            return await ctx.send("❌ Base de datos no disponible.")
        col = tipo.strip().lower()
        aliases = {
            "impostor": "wins_impostor",
            "social": "wins_social",
            "partidas": "games_played",
        }
        col = aliases.get(col, col)
        if col not in (
            "wins_impostor", "wins_social", "games_played", "games_impostor", "games_social"
        ):
            return await ctx.send(
                "Uso: `?impostorrang` [wins_impostor|wins_social|games_played|games_impostor|games_social]"
            )
        rows = db.get_impostor_leaderboard(col, limit=15)
        if not rows:
            return await ctx.send("Aún no hay datos para ese ranking.")
        await ctx.send(embed=self._embed_ranking(col, rows))

    @app_commands.command(name="impostor-activos", description="Lista salas Impostor activas en el servidor.")
    async def impostor_activos_slash(self, interaction: discord.Interaction):
        lobbies = core.get_all_lobbies()
        guild_id = interaction.guild_id if interaction.guild else None
        if guild_id is not None:
            lobbies = [lb for lb in lobbies if lb.guild_id == guild_id]
        await interaction.response.send_message(
            embed=_build_activos_embed(lobbies),
            ephemeral=True,
        )

    @commands.command(name="impostoractivos", aliases=["lobbysactivos", "salasimpostor"])
    async def impostor_activos_prefix(self, ctx: commands.Context):
        lobbies = core.get_all_lobbies()
        if ctx.guild:
            lobbies = [lb for lb in lobbies if lb.guild_id == ctx.guild.id]
        await ctx.send(embed=_build_activos_embed(lobbies))

    def _embed_historial(self, rows: list) -> discord.Embed:
        embed = discord.Embed(
            title="📜 Últimas partidas Impostor",
            color=discord.Color.dark_teal(),
        )
        if not rows:
            embed.description = "Aún no hay partidas registradas."
            return embed
        lines = []
        for r in rows:
            ts = datetime.fromtimestamp(r["ended_ts"], tz=timezone.utc)
            gan = "Sociales" if r["winner_role"] == "SOCIAL" else "Impostores"
            lines.append(
                f"• **{r['lobby_name']}** — {gan} — {r['human_count']}j/{r['impostor_count']}imp — "
                f"{r['secret_name'][:40]} ({ts.strftime('%d/%m %H:%M')} UTC)"
            )
        embed.description = "\n".join(lines[:15])
        return embed

    @app_commands.command(
        name="impostor-historial",
        description="Últimas partidas registradas (global).",
    )
    @app_commands.describe(limite="Cuántas partidas mostrar (máx. 15)")
    async def impostor_historial_slash(
        self, interaction: discord.Interaction, limite: Optional[int] = 10
    ):
        db = self._db()
        if not db:
            return await interaction.response.send_message(
                "❌ Base de datos no disponible.", ephemeral=True
            )
        rows = db.get_impostor_game_log_recent(limite or 10)
        await interaction.response.send_message(
            embed=self._embed_historial(rows), ephemeral=True
        )

    @commands.command(name="impostorhistorial", aliases=["imphist", "historialimpostor"])
    async def impostor_historial_prefix(self, ctx: commands.Context, limite: int = 10):
        db = self._db()
        if not db:
            return await ctx.send("❌ Base de datos no disponible.")
        rows = db.get_impostor_game_log_recent(limite)
        await ctx.send(embed=self._embed_historial(rows))


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorStatsCog(bot))
