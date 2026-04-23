# Mensaje fijo: prioridad BOT_GUIA_CHANNEL_ID (guía larga fija); si falta, BOT_CHANNEL_ID (#general / votación no).
# Se vuelve a generar al conectar (on_ready / reconexión) y al unirse a un servidor que contiene ese canal,
# para que comandos nuevos, textos de guía y reglas en código reemplacen el mensaje guardado.
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any, List, Optional, Union

import discord
from discord.ext import commands

from .db_manager import EconomiaDBManagerV2
from .guia_contenido import chunk_guia_embeds_for_send

META_KEY = "guia_bot_message_id"
META_FORUM_THREAD = "guia_bot_forum_thread_id"
META_HASH = "guia_bot_sync_sha256"
# Discord limita PATCH seguidos al mismo canal; la guía son muchas páginas.
_GUIA_CHANNEL_EDIT_DELAY_SEC = 1.15

log = logging.getLogger(__name__)


def _guia_chunks_signature(chunks: List[List[discord.Embed]]) -> str:
    """Firma estable del contenido a publicar (si coincide con la guardada, no tocar Discord)."""
    payload: List[Any] = []
    for part in chunks:
        for emb in part:
            payload.append(emb.to_dict())
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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

    async def _ensure_forum_guide_thread(self, forum: discord.ForumChannel) -> Optional[discord.Thread]:
        """Un hilo fijo dentro del foro para los mensajes con embeds (Discord no permite texto suelto en el foro)."""
        guild = forum.guild
        me = guild.me
        if not me:
            return None
        if not forum.permissions_for(me).create_public_threads:
            log.warning("Foro de guía %s: falta permiso create_public_threads", forum.id)
            return None
        raw = self.db.bot_meta_get(META_FORUM_THREAD)
        thread: Optional[discord.Thread] = None
        if raw and str(raw).strip().isdigit():
            ch = self.bot.get_channel(int(raw))
            if isinstance(ch, discord.Thread) and ch.parent_id == forum.id:
                thread = ch
        if thread is None:
            try:
                created = await forum.create_thread(
                    name="Guía y reglas del bot",
                    content="📚 **Guía fija** — el bot edita o reenvía los mensajes de abajo solo.",
                    auto_archive_duration=10080,
                )
                # discord.py: en foros suele devolver ThreadWithMessage (thread, message) o similar.
                if isinstance(created, discord.Thread):
                    thread = created
                else:
                    thread = getattr(created, "thread", None)
                    if thread is None and isinstance(created, tuple) and created:
                        thread = created[0]  # type: ignore[assignment]
                if thread is None or not isinstance(thread, discord.Thread):
                    log.warning("Foro guía %s: create_thread no devolvió un hilo reconocible.", forum.id)
                    return None
                self.db.bot_meta_set(META_FORUM_THREAD, str(thread.id))
                log.info("Creado hilo de guía en foro %s → %s", forum.id, thread.id)
            except Exception as e:
                log.warning("Foro de guía %s: no se pudo crear hilo: %s", forum.id, e)
                return None
        else:
            if thread.archived:
                try:
                    await thread.edit(archived=False)
                except Exception as e:
                    log.debug("No se pudo desarchivar hilo guía %s: %s", thread.id, e)
        return thread

    async def _resolve_guia_write_target(
        self, channel: discord.abc.GuildChannel
    ) -> Optional[Union[discord.TextChannel, discord.Thread]]:
        if isinstance(channel, discord.TextChannel):
            return channel
        if isinstance(channel, discord.ForumChannel):
            return await self._ensure_forum_guide_thread(channel)
        log.warning(
            "Canal de guía %s: tipo %s no soportado (usá canal de texto o un foro con permiso de hilos públicos).",
            channel.id,
            type(channel).__name__,
        )
        return None

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
        ch_id = guia_channel_id or bot_channel_id
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
        # Prioridad: canal dedicado de guía (BOT_GUIA_CHANNEL_ID / task_config guia_bot).
        # Si no hay, usar el canal de comandos slash (BOT_CHANNEL_ID).
        bot_channel_id = int(os.getenv("BOT_CHANNEL_ID") or 0)
        guia_channel_id = int((tc.get("channels") or {}).get("guia_bot") or 0)
        ch_id = guia_channel_id or bot_channel_id
        if ch_id <= 0:
            log.debug("No hay canal configurado para publicar la guía (BOT_GUIA_CHANNEL_ID / BOT_CHANNEL_ID).")
            return

        raw_channel = self.bot.get_channel(ch_id)
        if raw_channel is None:
            try:
                raw_channel = await self.bot.fetch_channel(ch_id)
            except Exception as e:
                log.warning("No se pudo obtener el canal de guía %s: %s", ch_id, e)
                return

        if not isinstance(raw_channel, discord.abc.GuildChannel):
            log.warning("Canal de guía %s no es un canal de servidor válido.", ch_id)
            return

        write_ch = await self._resolve_guia_write_target(raw_channel)
        if write_ch is None:
            return

        guild = write_ch.guild
        me = guild.me if guild else None
        if not me:
            return
        perms = write_ch.permissions_for(me)
        can_send = perms.send_messages_in_threads if isinstance(write_ch, discord.Thread) else perms.send_messages
        if not can_send or not perms.embed_links:
            log.warning(
                "Faltan permisos en destino guía %s (send / send_in_threads + embed_links)",
                write_ch.id,
            )
            return

        if not self.bot.user:
            return

        chunks = chunk_guia_embeds_for_send(self.bot)
        n = len(chunks)
        if n == 0:
            log.debug("Guía: sin chunks, no se publica nada.")
            return

        content_sig = _guia_chunks_signature(chunks)
        old_ids = _parse_guia_message_ids(self.db.bot_meta_get(META_KEY))
        stored_sig = (self.db.bot_meta_get(META_HASH) or "").strip()
        if stored_sig == content_sig and len(old_ids) == n and n > 0:
            try:
                probe = await write_ch.fetch_message(old_ids[0])
            except (discord.NotFound, discord.HTTPException):
                probe = None
            if probe is not None and probe.author.id == self.bot.user.id:
                log.info("Guía sin cambios de contenido (%s), omitiendo sync en canal %s.", reason, write_ch.id)
                return

        old_msgs: List[Optional[discord.Message]] = []
        for mid in old_ids:
            try:
                m = await write_ch.fetch_message(mid)
                old_msgs.append(m if m.author.id == self.bot.user.id else None)
            except discord.NotFound:
                old_msgs.append(None)
            except Exception as e:
                log.warning("No se pudo fetch el mensaje guía %s: %s", mid, e)
                old_msgs.append(None)

        new_ids: List[int] = []

        for i, part in enumerate(chunks):
            if i > 0:
                await asyncio.sleep(_GUIA_CHANNEL_EDIT_DELAY_SEC)
            content = f"📚 **Guía del bot ({i + 1}/{n})**" if n > 1 else None
            m_old = old_msgs[i] if i < len(old_msgs) else None
            if m_old is not None:
                try:
                    await m_old.edit(content=content, embeds=part)
                    new_ids.append(m_old.id)
                    continue
                except discord.Forbidden as e:
                    log.warning("Sin permiso para editar el mensaje de guía %s en %s: %s", m_old.id, write_ch.id, e)
                except Exception as e:
                    log.warning("Error editando mensaje guía %s: %s", m_old.id, e)
                try:
                    await m_old.delete()
                except Exception:
                    pass

            try:
                m = await write_ch.send(content=content, embeds=part)
                new_ids.append(m.id)
            except Exception as e:
                log.exception("No se pudo enviar el mensaje de guía (parte %s): %s", i + 1, e)
                return

        for j in range(len(chunks), len(old_msgs)):
            await asyncio.sleep(_GUIA_CHANNEL_EDIT_DELAY_SEC)
            m = old_msgs[j]
            if m is None:
                continue
            try:
                await m.delete()
            except Exception as e:
                log.debug("No se pudo borrar mensaje guía sobrante %s: %s", m.id, e)

        self.db.bot_meta_set(META_KEY, "|".join(str(x) for x in new_ids))
        self.db.bot_meta_set(META_HASH, content_sig)
        log.info("Guía sincronizada (%s) en destino %s — %s mensaje(s).", reason, write_ch.id, len(new_ids))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GuiaCanalCog(bot))
