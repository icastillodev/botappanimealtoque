from __future__ import annotations

import datetime as _dt
import logging
import os
from typing import Any, Dict, Optional

import discord
from discord.ext import commands

from aiohttp import web

log = logging.getLogger(__name__)


def _env_int(key: str, default: int = 0) -> int:
    raw = (os.getenv(key) or "").strip()
    return int(raw) if raw.isdigit() else default


def _calc_ahorcado_id_dia_now_uy() -> int:
    try:
        from zoneinfo import ZoneInfo  # py3.9+

        tz = ZoneInfo("America/Montevideo")
        now = _dt.datetime.now(tz=tz)
    except Exception:
        # Fallback: hora local del server (si no hay zoneinfo)
        now = _dt.datetime.now()
    inicio = _dt.date(2026, 1, 1)
    days = (now.date() - inicio).days
    return int(days) + 1


class AhorcadoDailyWebhookCog(commands.Cog):
    """
    Recibe el resultado del ahorcado diario desde la web y lo registra como diaria del bot.

    Config (.env del bot):
    - AHORCADO_WEBHOOK_SECRET: secreto compartido (Bearer).
    - AHORCADO_WEBHOOK_HOST: por defecto 0.0.0.0
    - AHORCADO_WEBHOOK_PORT: puerto (ej 8099)
    - AHORCADO_DAILY_CHANNEL_ID: canal donde publicar el resultado (opcional)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def cog_load(self) -> None:
        secret = (os.getenv("AHORCADO_WEBHOOK_SECRET") or "").strip()
        port = _env_int("AHORCADO_WEBHOOK_PORT", 0)
        if not secret or port <= 0:
            log.info("Ahorcado webhook: deshabilitado (faltan AHORCADO_WEBHOOK_SECRET o AHORCADO_WEBHOOK_PORT).")
            return
        host = (os.getenv("AHORCADO_WEBHOOK_HOST") or "0.0.0.0").strip()

        app = web.Application()
        app["secret"] = secret
        app.add_routes([web.post("/ahorcado/daily", self._handle_daily)])

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=host, port=port)
        await self._site.start()
        log.info("Ahorcado webhook: escuchando en http://%s:%s/ahorcado/daily", host, port)

    async def cog_unload(self) -> None:
        try:
            if self._site:
                await self._site.stop()
        finally:
            self._site = None
        try:
            if self._runner:
                await self._runner.cleanup()
        finally:
            self._runner = None

    async def _handle_daily(self, request: web.Request) -> web.Response:
        try:
            auth = (request.headers.get("Authorization") or "").strip()
            expected = str(request.app.get("secret") or "")
            if auth != f"Bearer {expected}":
                return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

            data: Dict[str, Any] = await request.json()
            uid = int(data.get("discord_id") or 0)
            id_dia = int(data.get("id_dia") or 0)
            puntos = int(data.get("puntos") or 0)
            errores = int(data.get("errores") or 0)
            pistas = int(data.get("pistas") or 0)
            ganado = bool(data.get("ganado"))
            username = str(data.get("username") or "").strip()

            if uid <= 0 or id_dia <= 0:
                return web.json_response({"ok": False, "error": "bad_request"}, status=400)

            # Antireplay: tiene que coincidir con el ahorcado "de hoy" (hora Uruguay).
            today_id = _calc_ahorcado_id_dia_now_uy()
            if id_dia != today_id:
                return web.json_response(
                    {"ok": False, "error": "wrong_day", "expected_id_dia": today_id, "got": id_dia},
                    status=400,
                )

            db = getattr(self.bot, "economia_db", None)
            if not db:
                return web.json_response({"ok": False, "error": "db_unavailable"}, status=503)

            prog = db.get_progress_diaria(uid)
            if int(prog.get("dia_ahorcado") or 0) >= 1 and int(prog.get("dia_ahorcado_id") or 0) == id_dia:
                return web.json_response({"ok": False, "error": "already_submitted"}, status=409)

            db.mark_diaria_ahorcado_result(uid, id_dia)

            # Publicar en Discord (opcional)
            ch_id = _env_int("AHORCADO_DAILY_CHANNEL_ID", 0)
            if ch_id > 0:
                ch = self.bot.get_channel(ch_id)
                if isinstance(ch, (discord.TextChannel, discord.Thread)):
                    title = "🪢 Ahorcado del día"
                    who = f"<@{uid}>" if uid else (username or "Jugador")
                    status = "✅ Ganó" if ganado else "❌ Perdió"
                    desc = (
                        f"**Jugador:** {who}\n"
                        f"**Resultado:** {status}\n"
                        f"**Pistas:** {pistas}\n"
                        f"**Errores:** {errores}\n"
                        f"**Puntos (web):** {puntos}\n"
                        f"**ID día:** {id_dia}\n"
                        "Web: `animealtoque.com/ahorcado`"
                    )
                    emb = discord.Embed(title=title, description=desc[:4096], color=discord.Color.dark_gold())
                    try:
                        await ch.send(embed=emb, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
                    except Exception:
                        log.warning("Ahorcado webhook: no se pudo enviar al canal %s", ch_id, exc_info=True)

            return web.json_response({"ok": True})
        except web.HTTPException:
            raise
        except Exception:
            log.exception("Ahorcado webhook: error inesperado")
            return web.json_response({"ok": False, "error": "internal_error"}, status=500)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AhorcadoDailyWebhookCog(bot))

