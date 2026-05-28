# Actividad de lobby, cierre por inactividad y log staff.
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import discord
from discord.ext import commands

from .engine import GameState, PHASE_END, PHASE_IDLE

log = logging.getLogger(__name__)


def touch_lobby_activity(lobby: GameState) -> None:
    lobby.last_activity_ts = time.time()


def get_lobby_idle_close_seconds() -> int:
    raw = (os.getenv("IMPOSTOR_LOBBY_IDLE_CLOSE_SECONDS") or "300").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 300


def get_staff_log_channel_id() -> Optional[int]:
    raw = (os.getenv("IMPOSTOR_STAFF_LOG_CHANNEL_ID") or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


async def post_staff_log(bot: commands.Bot, embed: discord.Embed) -> None:
    ch_id = get_staff_log_channel_id()
    if not ch_id:
        return
    ch = bot.get_channel(ch_id)
    if not ch or not isinstance(ch, discord.TextChannel):
        return
    try:
        await ch.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning("staff log impostor: %s", e)


async def sweep_idle_lobbies(bot: commands.Bot) -> int:
    """
    Cierra lobbies en espera sin actividad reciente.
    Devuelve cantidad de canales cerrados.
    """
    from . import core
    from .lobby import close_lobby_channel

    idle_sec = get_lobby_idle_close_seconds()
    if idle_sec <= 0:
        return 0

    now = time.time()
    closed = 0
    for lobby in list(core.get_all_lobbies()):
        if lobby.in_progress or lobby.phase != PHASE_IDLE:
            continue
        last = getattr(lobby, "last_activity_ts", 0) or 0
        if now - last < idle_sec:
            continue
        ch = bot.get_channel(lobby.channel_id)
        if isinstance(ch, discord.TextChannel):
            mins = max(1, idle_sec // 60)
            try:
                await ch.send(
                    f"⏱️ Lobby cerrado por **inactividad** ({mins} min sin mensajes ni acciones en el panel)."
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
        try:
            idle_embed = discord.Embed(
                title="Impostor — lobby cerrado (inactividad)",
                description=f"Sala **{lobby.lobby_name}** sin actividad.",
                color=discord.Color.orange(),
            )
            idle_embed.add_field(name="Canal", value=f"<#{lobby.channel_id}>", inline=True)
            idle_embed.add_field(name="Host", value=f"<@{lobby.host_id}>", inline=True)
            idle_embed.add_field(
                name="Jugadores",
                value=str(lobby.all_players_count),
                inline=True,
            )
            await post_staff_log(bot, idle_embed)
        except Exception as e:
            log.warning("staff log idle lobby: %s", e)
        if await close_lobby_channel(bot, lobby, reason="Lobby Impostor inactivo"):
            closed += 1
            log.info("Lobby inactivo cerrado: %s C:%s", lobby.lobby_name, lobby.channel_id)
    return closed
