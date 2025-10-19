# cogs/impostor/feed.py
import os
from typing import Optional, List

import discord

from .core import FEED_CHANNEL_ID, MAX_PLAYERS, manager, Lobby

class FeedBoard:
    """Mantiene un mensaje fijo por guild con la cartelera de lobbys."""
    def __init__(self):
        self._msg_by_guild: dict[int, int] = {}

    async def update(self, guild: discord.Guild):
        if not FEED_CHANNEL_ID:
            return
        ch = guild.get_channel(FEED_CHANNEL_ID)
        if not isinstance(ch, discord.TextChannel):
            return

        # Filtrar lobbies NO en partida y que no estén marcados como ocultos
        lobbies: List[Lobby] = [
            lob for lob in manager.all_in_guild(guild.id)
            if not getattr(lob, "_hidden", False)
        ]

        open_lines, closed_lines = [], []
        for lob in lobbies:
            line = f"• **{lob.name}** — {lob.slots()} — {'abierto' if lob.is_open else 'cerrado'} — host: <@{lob.host_id}>"
            (open_lines if lob.is_open else closed_lines).append(line)

        parts = []
        parts.append("🎭 **Lobbys de IMPOSITOR** (5 jugadores)\n")
        parts.append("🟢 **Abiertos**" if open_lines else "🟢 **Abiertos**\n*(no hay por ahora)*")
        parts.extend(open_lines)
        parts.append("")
        parts.append("🔒 **Cerrados**" if closed_lines else "🔒 **Cerrados**\n*(no hay por ahora)*")
        parts.extend(closed_lines)
        parts.append("\n**Comandos rápidos**")
        parts.append("• `/crearimpostor nombre:... tipo:(abierto|cerrado)`")
        parts.append("• `/entrar nombre:...`  (si es abierto)  |  `/invitar usuario:...` (si sos host)")
        parts.append("• `/abrirlobby` / `/cerrarlobby`  |  `/kick usuario:...`  |  `/ready` / `/leave`")
        parts.append("• **Partida**: `/comenzar` → luego `/palabra` y `/votar` por rondas")
        parts.append("• **Revancha**: `/revancha` (host/admin) dentro de 60s post-partida")
        parts.append("• **Ayuda**: `/ayuda` (contextual)  |  `/ayudacrearimp` (crear e invitar)")
        parts.append("• **Admin**: `/feed_refresh`")

        content = "\n".join(parts)

        try:
            msg_id = self._msg_by_guild.get(guild.id)
            if msg_id:
                msg = await ch.fetch_message(msg_id)
                await msg.edit(content=content)
            else:
                msg = await ch.send(content)
                self._msg_by_guild[guild.id] = msg.id
        except Exception:
            try:
                msg = await ch.send(content)
                self._msg_by_guild[guild.id] = msg.id
            except Exception:
                pass

feed = FeedBoard()
