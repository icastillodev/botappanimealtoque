# Bloquea consulta de daily/misiones en #general y zona Impostor.
from __future__ import annotations

import os
from typing import Optional

import discord
from discord.ext import commands

from cogs.impostor.zone import get_bot_channel_id, is_impostor_zone


def _general_channel_id() -> Optional[int]:
    val = (os.getenv("GENERAL_CHANNEL_ID") or "").strip()
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def is_progress_blocked_channel(channel: discord.abc.GuildChannel) -> bool:
    """True en #general, lobbies Impostor, cartelera o categoría Impostor."""
    if not isinstance(channel, discord.TextChannel):
        return False
    gen_id = _general_channel_id()
    if gen_id and channel.id == gen_id:
        return True
    return is_impostor_zone(channel)


def economy_progress_blocked_message() -> str:
    bot_ch = get_bot_channel_id()
    dest = f"<#{bot_ch}>" if bot_ch else "el **canal del bot**"
    return (
        "🚫 En **#general** y en canales de **Impostor** no podés ver el **daily** "
        "ni el **progreso de misiones**.\n"
        f"Usá {dest} para `?diario`, `?progreso`, `?reclamar`, etc."
    )


async def reject_progress_in_impostor_zone(ctx: commands.Context) -> bool:
    """Si el comando debe abortarse, envía aviso y devuelve True."""
    ch = ctx.channel
    if ch is None or not isinstance(ch, discord.abc.GuildChannel):
        return False
    if not is_progress_blocked_channel(ch):
        return False
    await ctx.send(economy_progress_blocked_message(), delete_after=12)
    return True


async def reject_progress_interaction(interaction: discord.Interaction) -> bool:
    ch = interaction.channel
    if ch is None or not isinstance(ch, discord.abc.GuildChannel):
        return False
    if not is_progress_blocked_channel(ch):
        return False
    msg = economy_progress_blocked_message()
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)
    return True
