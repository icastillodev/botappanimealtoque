# Mensaje fijo en BOT_GUIA_CHANNEL_ID (canal dedicado, distinto de BOT_CHANNEL_ID / #general / votación).
# Se vuelve a generar al conectar (on_ready / reconexión) y al unirse a un servidor que contiene ese canal,
# para que comandos nuevos, textos de guía y reglas en código reemplacen el mensaje guardado.
from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional

import discord
from discord.ext import commands

from .db_manager import EconomiaDBManagerV2
from .guia_contenido import chunk_guia_embeds_for_send

META_KEY = "guia_bot_message_id"

log = logging.getLogger(__name__)


def _parse_guia_message_ids(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    s = str(raw).strip()
    if "|" in s:
        parts = s.split("|")
    elif "," in s:
        parts = s.split(",")
    else:
        parts = [s]
    out: List[int] = []
    for p in parts:
        p = p.strip()
        if p.isdigit():
            out.append(int(p))
    return out


class GuiaCanalCog(commands.Cog, name="Guía canal fijo"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self._guia_sync_lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self.bot.user:
            return
        asyncio.create_task(self._sync_after_delay("on_ready"))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        tc = getattr(self.bot, "task_config", None) or {}
        bot_channel_id = int(os.getenv("BOT_CHANNEL_ID") or 0)
        guia_channel_id = int((tc.get("channels") or {}).get("guia_bot") or 0)
        ch_id = bot_channel_id or guia_channel_id
        if ch_id <= 0:
            return
        if guild.get_channel(ch_id) is not None:
            asyncio.create_task(self._sync_after_delay("on_guild_join"))

    async def _sync_after_delay(self, reason: str) -> None:
        await asyncio.sleep(3)
        try:
            await self._sync_guia_message(reason)
        except Exception:
            log.exception("Fallo sync guía (%s)", reason)

    async def _sync_guia_message(self, reason: str = "sync") -> None:
        async with self._guia_sync_lock:
            await self._sync_guia_message_unlocked(reason)

    async def _sync_guia_message_unlocked(self, reason: str) -> None:
        tc = getattr(self.bot, "task_config", None) or {}
        # Publicar SIEMPRE en el canal del bot (canal de comandos), porque es donde la gente lo usa.
        # Si no está configurado, caer al canal guía dedicado (si existe).
        bot_channel_id = int(os.getenv("BOT_CHANNEL_ID") or 0)
        guia_channel_id = int((tc.get("channels") or {}).get("guia_bot") or 0)
        ch_id = bot_channel_id or guia_channel_id
        if ch_id <= 0:
            log.debug("No hay canal configurado para publicar la guía (BOT_CHANNEL_ID / BOT_GUIA_CHANNEL_ID).")
            return

        channel = self.bot.get_channel(ch_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(ch_id)
            except Exception as e:
                log.warning("No se pudo obtener el canal de guía %s: %s", ch_id, e)
                return

        if not isinstance(channel, discord.TextChannel):
            log.warning("BOT_GUIA_CHANNEL_ID no es un canal de texto: %s", ch_id)
            return

        perms = channel.permissions_for(channel.guild.me) if channel.guild else None
        if perms and (not perms.send_messages or not perms.embed_links):
            log.warning("Faltan permisos send_messages/embed_links en canal guía %s", ch_id)
            return

        if not self.bot.user:
            return

        chunks = chunk_guia_embeds_for_send(self.bot)
        n = len(chunks)
        old_ids = _parse_guia_message_ids(self.db.bot_meta_get(META_KEY))
        old_msgs: List[Optional[discord.Message]] = []
        for mid in old_ids:
            try:
                m = await channel.fetch_message(mid)
                old_msgs.append(m if m.author.id == self.bot.user.id else None)
            except discord.NotFound:
                old_msgs.append(None)
            except Exception as e:
                log.warning("No se pudo fetch el mensaje guía %s: %s", mid, e)
                old_msgs.append(None)

        new_ids: List[int] = []

        for i, part in enumerate(chunks):
            content = f"📚 **Guía del bot ({i + 1}/{n})**" if n > 1 else None
            m_old = old_msgs[i] if i < len(old_msgs) else None
            if m_old is not None:
                try:
                    await m_old.edit(content=content, embeds=part)
                    new_ids.append(m_old.id)
                    continue
                except discord.Forbidden as e:
                    log.warning("Sin permiso para editar el mensaje de guía %s en %s: %s", m_old.id, channel.id, e)
                except Exception as e:
                    log.warning("Error editando mensaje guía %s: %s", m_old.id, e)
                try:
                    await m_old.delete()
                except Exception:
                    pass

            try:
                m = await channel.send(content=content, embeds=part)
                new_ids.append(m.id)
            except Exception as e:
                log.exception("No se pudo enviar el mensaje de guía (parte %s): %s", i + 1, e)
                return

        for j in range(len(chunks), len(old_msgs)):
            m = old_msgs[j]
            if m is None:
                continue
            try:
                await m.delete()
            except Exception as e:
                log.debug("No se pudo borrar mensaje guía sobrante %s: %s", m.id, e)

        self.db.bot_meta_set(META_KEY, "|".join(str(x) for x in new_ids))
        log.info("Guía sincronizada (%s) en canal %s — %s mensaje(s).", reason, channel.id, len(new_ids))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GuiaCanalCog(bot))
