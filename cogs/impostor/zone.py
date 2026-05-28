# Detección de canales/zona Impostor (lobbies, cartelera, categoría).
from __future__ import annotations

import os
from typing import Optional

import discord

from . import core


def _env_int(key: str) -> Optional[int]:
    val = (os.getenv(key) or "").strip()
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def get_impostor_category_id() -> Optional[int]:
    return _env_int("IMPOSTOR_CATEGORY_ID")


def get_impostor_feed_channel_id() -> Optional[int]:
    return _env_int("IMPOSTOR_FEED_CHANNEL_ID")


def get_bot_channel_id() -> Optional[int]:
    return _env_int("BOT_CHANNEL_ID")


def is_impostor_lobby_channel(channel_id: int) -> bool:
    return core.get_lobby_by_channel(channel_id) is not None


def is_impostor_zone(channel: discord.abc.GuildChannel) -> bool:
    """True en canal de lobby activo, cartelera o categoría Impostor."""
    if not isinstance(channel, discord.TextChannel):
        return False
    if is_impostor_lobby_channel(channel.id):
        return True
    feed_id = get_impostor_feed_channel_id()
    if feed_id and channel.id == feed_id:
        return True
    cat_id = get_impostor_category_id()
    if cat_id and channel.category_id == cat_id:
        return True
    return False


def economy_blocked_in_impostor_zone_message() -> str:
    """Mensaje legacy; preferir `economia.progress_zone_guard.economy_progress_blocked_message`."""
    from cogs.economia.progress_zone_guard import economy_progress_blocked_message

    return economy_progress_blocked_message()
