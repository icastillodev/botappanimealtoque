# Mensaje fijo en BOT_GUIA_CHANNEL_ID (canal dedicado, distinto de BOT_CHANNEL_ID / #general / votación).
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

from .db_manager import EconomiaDBManagerV2
from .guia_contenido import build_guia_embeds

META_KEY = "guia_bot_message_id"

log = logging.getLogger(__name__)


class GuiaCanalCog(commands.Cog, name="Guía canal fijo"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self._sync_started = False

    async def cog_load(self) -> None:
        if self._sync_started:
            return
        self._sync_started = True
        asyncio.create_task(self._sync_after_ready())

    async def _sync_after_ready(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(3)
        await self._sync_guia_message()

    async def _sync_guia_message(self) -> None:
        tc = getattr(self.bot, "task_config", None) or {}
        ch_id = int((tc.get("channels") or {}).get("guia_bot") or 0)
        if ch_id <= 0:
            log.debug("BOT_GUIA_CHANNEL_ID no configurado (canal aparte solo para la guía); se omite.")
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

        embeds = build_guia_embeds(self.bot)
        if len(embeds) > 10:
            embeds = embeds[:10]

        raw_id = self.db.bot_meta_get(META_KEY)
        msg: Optional[discord.Message] = None
        if raw_id and str(raw_id).isdigit():
            try:
                msg = await channel.fetch_message(int(raw_id))
            except discord.NotFound:
                msg = None
            except Exception as e:
                log.warning("No se pudo fetch el mensaje guía %s: %s", raw_id, e)
                msg = None

        try:
            if msg is not None and msg.author.id == self.bot.user.id:
                await msg.edit(content=None, embeds=embeds)
                log.info("Mensaje de guía actualizado en canal %s (id %s).", channel.id, msg.id)
                return
            if msg is not None and msg.author.id != self.bot.user.id:
                log.warning(
                    "El mensaje guardado en bot_meta no es del bot; se publica uno nuevo en %s.",
                    channel.id,
                )
        except discord.Forbidden:
            log.warning("Sin permiso para editar el mensaje de guía en %s", channel.id)
            return
        except Exception as e:
            log.warning("Error editando mensaje guía: %s", e)

        try:
            new_msg = await channel.send(embeds=embeds)
            self.db.bot_meta_set(META_KEY, str(new_msg.id))
            log.info("Mensaje de guía creado en canal %s (id %s).", channel.id, new_msg.id)
        except Exception as e:
            log.exception("No se pudo enviar el mensaje de guía: %s", e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GuiaCanalCog(bot))
