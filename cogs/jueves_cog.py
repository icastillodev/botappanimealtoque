# Feliz jueves: post semanal en #general y respuestas a quien conteste.
from __future__ import annotations

import logging
import os
import random
from datetime import date, datetime, time, timezone
from typing import List, Optional

import discord
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

_JUEVES_URL = "https://www.youtube.com/shorts/QfGJSCMWMzU"

try:
    from zoneinfo import ZoneInfo

    UY = ZoneInfo("America/Montevideo")
except Exception:  # pragma: no cover
    UY = None

_FELIZ_JUEVES_REPLIES: List[str] = [
    "¡Qué fachero/a estás hoy! Feliz jueves 🎉",
    "Feliz jueves, leyenda del servidor.",
    "Hoy brilla distinto. Feliz jueves ✨",
    "Jueves nivel boss desbloqueado. ¡Vamos!",
    "Tu vibe de jueves está aprobada por el consejo ninja.",
    "Feliz jueves — que el café te acompañe.",
    "Se nota que es jueves y vos lo sabés usar.",
    "Feliz jueves, main character del chat.",
    "Hoy es jueves y vos sos el plot twist bueno.",
    "Aprobado: fachero/a confirmado. Feliz jueves.",
    "El jueves te queda demasiado bien, no voy a mentir.",
    "Feliz jueves — que no te toque gente con pala.",
    "Tu outfit de jueves (mental) está impecable.",
    "Feliz jueves, campeón/a del rollo.",
    "Jueves con power-up activado. ¡Disfrutá!",
    "Hoy el universo dijo: feliz jueves para vos.",
    "Feliz jueves — seguí así de fachero/a.",
    "El chat necesitaba tu energía de jueves.",
    "Feliz jueves, ícono del servidor.",
    "Jueves mode: ON. Vos: legendario/a.",
    "Qué presencia. Feliz jueves de verdad.",
    "Feliz jueves — que sea meme bueno, no reunión.",
    "Hoy es jueves y vos lo estás llevando con estilo.",
    "Feliz jueves, héroe/a del hilo.",
    "Tu jueves tiene rating 5 estrellas.",
    "Feliz jueves — el rollo te queda natural.",
    "Confirmado: sos la razón por la que el jueves existe.",
    "Feliz jueves, estrella del general.",
    "Jueves aprobado por el bot con sello de facha.",
    "Hoy brillas más que un opening de temporada.",
    "Feliz jueves — que no te interrumpan con laburo.",
    "Tu jueves está cargado de aura positiva.",
    "Feliz jueves, capo/a del chat.",
    "Jueves premium desbloqueado gracias a vos.",
    "Feliz jueves — seguí dominando el día.",
    "Qué energía. Feliz jueves, crack.",
    "El jueves te saluda con respeto.",
    "Feliz jueves — que el RNG te sonría.",
    "Hoy el servidor está más fachero por tu culpa.",
    "Feliz jueves, leyenda viviente.",
    "Jueves con buff de carisma. Aprovechá.",
    "Feliz jueves — que no aparezca la pala.",
    "Tu presencia de jueves es contenido de calidad.",
    "Feliz jueves, ídolo/a del Discord.",
    "Hoy es jueves y vos sos el evento especial.",
    "Feliz jueves — que sea corto el lunes.",
    "Aprobado por estética: feliz jueves.",
    "Feliz jueves, campeón/a del buen humor.",
    "Jueves con estilo. Vos con más.",
    "Feliz jueves — el chat te banca.",
    "Hoy el jueves te hizo un fan club.",
]


def _uy_now() -> datetime:
    if UY:
        return datetime.now(tz=UY)
    return datetime.now(tz=timezone.utc)


def _general_channel_id() -> int:
    try:
        return int(os.getenv("GENERAL_CHANNEL_ID", "0") or 0)
    except ValueError:
        return 0


class JuevesCog(commands.Cog, name="Jueves"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._db = getattr(bot, "economia_db", None)

    async def cog_load(self) -> None:
        if UY and not self._jueves_loop.is_running():
            self._jueves_loop.start()

    async def cog_unload(self) -> None:
        self._jueves_loop.cancel()

    def _meta_key_post(self, week: str) -> str:
        return f"jueves_post_{week}"

    def _meta_key_msg(self, week: str) -> str:
        return f"jueves_msg_{week}"

    def _week_id(self, d: date) -> str:
        iso = d.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    async def _post_feliz_jueves(self, guild: discord.Guild) -> None:
        ch_id = _general_channel_id()
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if not ch or not isinstance(ch, discord.TextChannel):
            return
        now = _uy_now()
        week = self._week_id(now.date())
        if self._db and self._db.bot_meta_get(self._meta_key_post(week)):
            return
        text = f"**FELIZ JUEVES!** 🎉\n{_JUEVES_URL}"
        try:
            msg = await ch.send(text)
            if self._db:
                self._db.bot_meta_set(self._meta_key_post(week), "1")
                self._db.bot_meta_set(self._meta_key_msg(week), str(msg.id))
        except discord.HTTPException as e:
            log.warning("No se pudo publicar Feliz Jueves: %s", e)

    @tasks.loop(minutes=1)
    async def _jueves_loop(self) -> None:
        if not UY:
            return
        now = _uy_now()
        if now.weekday() != 3:  # jueves
            return
        if now.hour != 8 or now.minute != 0:
            return
        for guild in self.bot.guilds:
            try:
                await self._post_feliz_jueves(guild)
            except Exception:
                log.exception("jueves post guild %s", guild.id)

    @_jueves_loop.before_loop
    async def _before_jueves(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild or not message.reference:
            return
        if not self._db:
            return
        ref = message.reference
        if not ref or not ref.message_id:
            return
        now = _uy_now()
        if now.weekday() != 3:
            return
        week = self._week_id(now.date())
        stored = self._db.bot_meta_get(self._meta_key_msg(week))
        if not stored or str(ref.message_id) != stored:
            return
        try:
            await message.reply(random.choice(_FELIZ_JUEVES_REPLIES), mention_author=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(JuevesCog(bot))
