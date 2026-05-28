# Silencio en canal de partida: turnos, eliminados (hilo), fin de partida.
from __future__ import annotations

import logging
from typing import Optional, Set

import discord

from .engine import GameState, PHASE_END, PHASE_TURNS

log = logging.getLogger(__name__)


async def _set_send_messages(
    channel: discord.TextChannel,
    member: discord.Member,
    allowed: bool,
) -> None:
    try:
        if allowed:
            await channel.set_permissions(member, overwrite=None)
        else:
            await channel.set_permissions(
                member,
                overwrite=discord.PermissionOverwrite(send_messages=False),
            )
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning("chat_guard permisos C:%s U:%s: %s", channel.id, member.id, e)


async def ensure_eliminated_thread(
    bot: discord.Client,
    lobby: GameState,
    channel: discord.TextChannel,
) -> Optional[discord.Thread]:
    if lobby.eliminated_thread_id:
        th = channel.get_thread(lobby.eliminated_thread_id)
        if th:
            return th
    try:
        th = await channel.create_thread(
            name=f"Eliminados — ronda {lobby.round_num}",
            type=discord.ChannelType.public_thread,
            reason="Jugadores eliminados Impostor",
        )
        lobby.eliminated_thread_id = th.id
        await th.send(
            "💀 **Zona de eliminados.** Podés hablar acá; el canal principal queda solo para vivos."
        )
        return th
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning("No se pudo crear hilo eliminados C:%s: %s", channel.id, e)
        return None


async def on_player_eliminated(
    bot: discord.Client,
    lobby: GameState,
    user_id: int,
) -> None:
    channel = bot.get_channel(lobby.channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    guild = channel.guild
    member = guild.get_member(user_id)
    if not member:
        return
    lobby.eliminated_user_ids.add(user_id)
    await _set_send_messages(channel, member, False)
    th = await ensure_eliminated_thread(bot, lobby, channel)
    if th:
        try:
            await th.add_user(member)
        except (discord.Forbidden, discord.HTTPException):
            pass


async def restore_channel_chat(bot: discord.Client, lobby: GameState) -> None:
    channel = bot.get_channel(lobby.channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    guild = channel.guild
    for uid in list(lobby.eliminated_user_ids):
        member = guild.get_member(uid)
        if member:
            await _set_send_messages(channel, member, True)
    lobby.eliminated_user_ids.clear()
    lobby.eliminated_thread_id = None


def is_message_allowed_during_turns(lobby: GameState, author_id: int) -> bool:
    if lobby.phase != PHASE_TURNS:
        return True
    if author_id in lobby.eliminated_user_ids:
        return False
    if lobby.current_turn_idx < 0 or lobby.current_turn_idx >= len(lobby.alive_order):
        return False
    return author_id == lobby.alive_order[lobby.current_turn_idx]
