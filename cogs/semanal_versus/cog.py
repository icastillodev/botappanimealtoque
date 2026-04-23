# cogs/semanal_versus/cog.py
from __future__ import annotations

import logging
import os
import random
from datetime import date, datetime, time as dtime, timedelta
from typing import List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks
from zoneinfo import ZoneInfo

from cogs.impostor.chars import fetch_characters

from .db import VersusDB

log = logging.getLogger(__name__)


def _tz() -> ZoneInfo:
    name = os.getenv("VERSUS_TIMEZONE", "Europe/Madrid")
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def _close_dt_for_iso_week(year: int, week: int, tz: ZoneInfo) -> datetime:
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return datetime.combine(sunday, dtime(21, 0), tzinfo=tz)


def _active_week_and_close(now: datetime) -> Tuple[str, datetime]:
    tz = now.tzinfo or _tz()
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    y, w, _ = now.isocalendar()
    end = _close_dt_for_iso_week(y, w, tz)
    if now >= end:
        monday = date.fromisocalendar(y, w, 1)
        nxt = monday + timedelta(days=7)
        ny, nw, _ = nxt.isocalendar()
        return f"{ny}-W{nw:02d}", _close_dt_for_iso_week(ny, nw, tz)
    return f"{y}-W{w:02d}", end


def _parse_custom_id(cid: str) -> Optional[Tuple[str, int]]:
    parts = cid.split(":")
    if len(parts) != 3 or parts[0] != "versus":
        return None
    try:
        return parts[1], int(parts[2])
    except ValueError:
        return None


async def _pick_pair_from_api() -> Tuple[str, str]:
    """Personajes desde la misma fuente JSON que Impostor (IMPOSTOR_CHAR_SOURCE)."""
    chars = await fetch_characters()
    pool = [str(c.get("name") or "").strip() for c in chars if str(c.get("name") or "").strip()]
    pool = list(dict.fromkeys(pool))
    if len(pool) < 2:
        pool = ["Personaje A", "Personaje B"]
    return random.sample(pool, 2)


class VersusVoteView(discord.ui.View):
    def __init__(self, week_key: str, label_a: str, label_b: str):
        super().__init__(timeout=None)
        self.week_key = week_key
        self.label_a = label_a
        self.label_b = label_b

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary, custom_id="versus:wk:0")
    async def btn_a(self, interaction: discord.Interaction, button: discord.Button):
        await self._vote(interaction, button, 0)

    @discord.ui.button(label="B", style=discord.ButtonStyle.success, custom_id="versus:wk:1")
    async def btn_b(self, interaction: discord.Interaction, button: discord.Button):
        await self._vote(interaction, button, 1)

    async def _vote(self, interaction: discord.Interaction, button: discord.Button, side: int) -> None:
        cog = interaction.client.get_cog("SemanalVersus")
        if not cog:
            return await interaction.response.send_message("Módulo VERSUS no disponible.", ephemeral=True)
        parsed = _parse_custom_id(button.custom_id)
        week = parsed[0] if parsed else self.week_key
        poll = cog.db.get_poll(week)
        if not poll or poll.get("closed"):
            return await interaction.response.send_message("Esta votación ya cerró o no existe.", ephemeral=True)
        cog.db.set_vote(week, interaction.user.id, side)
        counts = cog._count_sides(week)
        label = self.label_a if side == 0 else self.label_b
        await interaction.response.send_message(
            f"✅ Voto: **{label}**\nMarcador — {self.label_a}: **{counts[0]}** · {self.label_b}: **{counts[1]}**",
            ephemeral=True,
        )


def _make_view(week_key: str, a: str, b: str) -> VersusVoteView:
    v = VersusVoteView(week_key, a, b)
    v.btn_a.custom_id = f"versus:{week_key}:0"
    v.btn_b.custom_id = f"versus:{week_key}:1"
    v.btn_a.label = a[:75] if len(a) <= 75 else a[:72] + "..."
    v.btn_b.label = b[:75] if len(b) <= 75 else b[:72] + "..."
    return v


def _week_end_from_key(week_key: str) -> Optional[datetime]:
    try:
        y_str, w_str = week_key.split("-W")
        y, w = int(y_str), int(w_str)
        return _close_dt_for_iso_week(y, w, _tz())
    except Exception:
        return None


def _versus_embed(week_key: str, a: str, b: str, end: datetime) -> discord.Embed:
    end_ts = int(end.timestamp())
    return discord.Embed(
        title=f"⚔️ VERSUS semanal `{week_key}`",
        description=(
            f"**{a}** vs **{b}**\n\n"
            "Votá con los botones (podés cambiar votando el otro).\n"
            f"Cierre: **domingo 21:00** ({os.getenv('VERSUS_TIMEZONE', 'Europe/Madrid')}) · <t:{end_ts}:F>\n"
            "Staff: `/aat_versus_votos` para ver quién votó qué."
        ),
        color=discord.Color.gold(),
    )


class SemanalVersusCog(commands.Cog, name="SemanalVersus"):
    """VERSUS semanal; cierra domingo 21:00 (VERSUS_TIMEZONE)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = VersusDB()
        self.channel_id = (
            int(os.getenv("VERSUS_WEEKLY_CHANNEL_ID", "0") or 0)
            or int(os.getenv("VOTACION_CHANNEL_ID", "0") or 0)
            or int(os.getenv("VOTING_CHANNEL_ID", "0") or 0)
        )
        self.general_announce_id = int(os.getenv("GENERAL_CHANNEL_ID", "0") or 0)
        self.log = logging.getLogger(self.__class__.__name__)

    def cog_unload(self):
        self.versus_tick.cancel()

    def _count_sides(self, week_key: str) -> Tuple[int, int]:
        rows = self.db.get_votes(week_key)
        c0 = sum(1 for r in rows if r["side"] == 0)
        c1 = len(rows) - c0
        return c0, c1

    def _register_view_safe(self, view: discord.ui.View) -> None:
        try:
            self.bot.add_view(view)
        except Exception:
            log.debug("add_view versus (posible duplicado)", exc_info=True)

    async def _sync_open_poll_after_restart(self, week_key: str, poll: dict) -> None:
        """
        Tras apagar/prender el bot: vuelve a registrar la vista persistente.
        Si el mensaje de Discord ya no existe, republica la misma pareja en el canal configurado.
        """
        if not self.channel_id:
            return
        ch_out = self.bot.get_channel(self.channel_id)
        if not isinstance(ch_out, discord.TextChannel):
            return

        stored_ch = int(poll.get("channel_id") or 0)
        msg_id = int(poll.get("message_id") or 0)
        ch = self.bot.get_channel(stored_ch) if stored_ch else None
        if not isinstance(ch, discord.TextChannel):
            try:
                fetched = await self.bot.fetch_channel(stored_ch)
                ch = fetched if isinstance(fetched, discord.TextChannel) else ch_out
            except Exception:
                ch = ch_out

        msg_ok = False
        if isinstance(ch, discord.TextChannel) and msg_id:
            try:
                await ch.fetch_message(msg_id)
                msg_ok = True
            except (discord.NotFound, discord.Forbidden):
                msg_ok = False
            except Exception:
                msg_ok = False

        end = _week_end_from_key(week_key)
        if end is None:
            return
        a, b = poll["char_a"], poll["char_b"]

        if msg_ok:
            self._register_view_safe(_make_view(week_key, a, b))
            return

        embed = _versus_embed(week_key, a, b, end)
        view = _make_view(week_key, a, b)
        try:
            msg = await ch_out.send(embed=embed, view=view)
        except Exception:
            self.log.exception("No se pudo repostear el versus %s", week_key)
            return
        self.db.update_poll_message(week_key, msg.id, ch_out.id)
        self._register_view_safe(view)
        self.log.warning("Versus %s: mensaje %s no encontrado; reposteado como %s", week_key, msg_id, msg.id)

    async def _register_persistent_views(self) -> None:
        for p in self.db.get_open_polls():
            await self._sync_open_poll_after_restart(p["week_key"], p)

    @commands.Cog.listener()
    async def on_ready(self):
        await self._register_persistent_views()
        if not self.versus_tick.is_running():
            self.versus_tick.start()

    @tasks.loop(minutes=2)
    async def versus_tick(self):
        try:
            await self._close_due_polls()
            await self._ensure_current_poll()
        except Exception:
            self.log.exception("versus_tick error")

    @versus_tick.before_loop
    async def versus_tick_before(self):
        await self.bot.wait_until_ready()

    async def _close_due_polls(self) -> None:
        tz = _tz()
        now = datetime.now(tz)
        for p in list(self.db.get_open_polls()):
            wk = p["week_key"]
            try:
                y_str, w_str = wk.split("-W")
                y, w = int(y_str), int(w_str)
                end = _close_dt_for_iso_week(y, w, tz)
            except Exception:
                continue
            if now >= end:
                await self._finalize_poll(wk, p)

    async def _finalize_poll(self, week_key: str, poll: dict) -> None:
        ch = self.bot.get_channel(int(poll["channel_id"]))
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(poll["channel_id"]))
            except Exception:
                self.db.mark_closed(week_key)
                return
        msg = None
        if isinstance(ch, discord.TextChannel):
            try:
                msg = await ch.fetch_message(int(poll["message_id"]))
            except Exception:
                pass
        c0, c1 = self._count_sides(week_key)
        char_a, char_b = poll["char_a"], poll["char_b"]
        if c0 == c1:
            winner, win_votes, loser_name, lose_votes = "Empate", c0, char_b, c1
            resumen = f"**Empate** entre **{char_a}** y **{char_b}** — **{c0}** votos cada uno."
        elif c0 > c1:
            winner, win_votes, loser_name, lose_votes = char_a, c0, char_b, c1
            resumen = f"El ganador de la votación fue **{winner}** con **{win_votes}** votos frente a **{lose_votes}** de **{loser_name}**."
        else:
            winner, win_votes, loser_name, lose_votes = char_b, c1, char_a, c0
            resumen = f"El ganador de la votación fue **{winner}** con **{win_votes}** votos frente a **{lose_votes}** de **{loser_name}**."
        self.db.mark_closed(week_key)
        if msg:
            try:
                await msg.edit(view=None)
                embed = msg.embeds[0] if msg.embeds else discord.Embed(title="VERSUS")
                embed.color = discord.Color.dark_gray()
                embed.set_footer(text=f"Cerrado — {char_a}: {c0} · {char_b}: {c1}")
                await msg.edit(embed=embed)
            except Exception:
                pass
        linea_canal = (
            f"🏁 **VERSUS semanal** `{week_key}` — cierre domingo **21:00** ({os.getenv('VERSUS_TIMEZONE', 'Europe/Madrid')}).\n"
            f"{resumen}\n"
            f"Marcador final: **{char_a}** {c0} — **{char_b}** {c1}"
        )
        try:
            if isinstance(ch, discord.TextChannel):
                await ch.send(linea_canal)
        except Exception:
            pass
        if self.general_announce_id and self.general_announce_id != getattr(ch, "id", 0):
            try:
                gch = self.bot.get_channel(self.general_announce_id)
                if gch is None:
                    gch = await self.bot.fetch_channel(self.general_announce_id)
                if isinstance(gch, discord.TextChannel):
                    await gch.send(linea_canal)
            except Exception:
                self.log.debug("No se pudo anunciar el versus en #general", exc_info=True)

    async def _ensure_current_poll(self) -> None:
        if not self.channel_id:
            return
        tz = _tz()
        now = datetime.now(tz)
        week_key, end = _active_week_and_close(now)
        row = self.db.get_poll(week_key)
        if row and not int(row.get("closed") or 0):
            await self._sync_open_poll_after_restart(week_key, row)
            return
        ch = self.bot.get_channel(self.channel_id)
        if not ch or not isinstance(ch, discord.TextChannel):
            return
        a, b = await _pick_pair_from_api()
        embed = _versus_embed(week_key, a, b, end)
        view = _make_view(week_key, a, b)
        msg = await ch.send(embed=embed, view=view)
        inserted = self.db.insert_poll_new(week_key, msg.id, ch.id, a, b)
        if not inserted:
            try:
                await msg.delete()
            except Exception:
                pass
            return
        self.bot.add_view(view)

    def _is_staff(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return True
        hid = getattr(self.bot, "hokage_role_id", None)
        if hid and member.get_role(int(hid)):
            return True
        return False

    @app_commands.command(name="aat_versus_votos", description="Lista quién votó a cada opción (VERSUS semanal actual).")
    async def versus_votos(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Solo en servidor.", ephemeral=True)
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("Solo staff / Hokage.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        tz = _tz()
        week_key, _ = _active_week_and_close(datetime.now(tz))
        poll = self.db.get_poll(week_key)
        if not poll:
            return await interaction.followup.send("No hay encuesta para esta semana.", ephemeral=True)
        votes = self.db.get_votes(week_key)
        team_a: List[str] = []
        team_b: List[str] = []
        for v in votes:
            uid = v["user_id"]
            try:
                u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                name = u.display_name
            except Exception:
                name = str(uid)
            if v["side"] == 0:
                team_a.append(name)
            else:
                team_b.append(name)
        embed = discord.Embed(title=f"Votos {week_key}", color=discord.Color.blurple())
        embed.add_field(name=poll["char_a"], value="\n".join(team_a) or "—", inline=False)
        embed.add_field(name=poll["char_b"], value="\n".join(team_b) or "—", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SemanalVersusCog(bot))
