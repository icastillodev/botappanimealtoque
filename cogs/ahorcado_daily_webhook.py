from __future__ import annotations

import datetime as _dt
import logging
import os
import re
from typing import Any, Dict, Optional

import discord
from discord.ext import commands

from aiohttp import web

log = logging.getLogger(__name__)

def _extract_share_stats(text: str) -> Optional[dict]:
    """
    Parse tolerante del share (multilínea) sin depender de que los emojis/códigos sean idénticos.
    """
    t = (text or "").strip()
    if not t:
        return None
    if "Ahorcado #AnimeAlToque" not in t:
        return None
    day_m = re.search(r"(?is)\bD[ií]a\s*#\s*(\d+)\b", t)
    if not day_m:
        return None
    out: dict = {"day": int(day_m.group(1) or 0)}
    m_err = re.search(r"(?is)Errores:\s*(\d+)\s*/\s*(\d+)", t)
    if m_err:
        out["err"] = int(m_err.group(1) or 0)
        out["errmax"] = int(m_err.group(2) or 0)
    m_h = re.search(r"(?is)Pistas:\s*(\d+)", t)
    if m_h:
        out["hints"] = int(m_h.group(1) or 0)
    m_p = re.search(r"(?is)Puntos:\s*(\d+)", t)
    if m_p:
        out["pts"] = int(m_p.group(1) or 0)
    # Extraer cuadrito (líneas con 🟩/⬜)
    grid_lines = []
    for ln in t.splitlines():
        s = ln.strip()
        if not s:
            continue
        # Mantener solo líneas que sean “cuadraditos” (con espacios opcionales).
        compact = s.replace(" ", "")
        if compact and all(ch in ("🟩", "⬜") for ch in compact):
            grid_lines.append(s)
    if grid_lines:
        # Evitar spam: máximo 6 líneas (suele ser 1–3).
        out["grid"] = grid_lines[:6]
    return out


class _AhorcadoShareView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=240)
        self.add_item(
            discord.ui.Button(
                label="Jugar ahorcado",
                style=discord.ButtonStyle.link,
                url="https://www.animealtoque.com/ahorcado",
                row=0,
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Ver ranking",
                style=discord.ButtonStyle.link,
                url="https://www.animealtoque.com/ahorcado",
                row=0,
            )
        )

    @discord.ui.button(label="¿Cómo cobra la diaria?", style=discord.ButtonStyle.secondary, row=1)
    async def how_claim(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        await interaction.response.send_message(
            "Para que cuente la **diaria 5 (ahorcado)** tenés que jugar en la web con Discord y terminar la partida.\n"
            "Cuando llega el webhook, el bot lo marca y después podés cobrar con **`?reclamar diaria 5`** "
            "(o botón en `?diaria`).",
            ephemeral=True,
        )


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
    Recibe el resultado del ahorcado diario desde la web y lo publica en Discord.

    Config (.env del bot):
    - AHORCADO_WEBHOOK_SECRET: secreto compartido (Bearer).
    - AHORCADO_WEBHOOK_HOST: por defecto 0.0.0.0
    - AHORCADO_WEBHOOK_PORT: puerto (ej 8099)
    - AHORCADO_DAILY_CHANNEL_ID: canal donde publicar el resultado (si falta, usa GENERAL_CHANNEL_ID)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._share_seen: set[int] = set()

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
            categoria = str(data.get("categoria") or "").strip()

            if uid <= 0 or id_dia <= 0:
                return web.json_response({"ok": False, "error": "bad_request"}, status=400)

            # Antireplay: tiene que coincidir con el ahorcado "de hoy" (hora Uruguay).
            today_id = _calc_ahorcado_id_dia_now_uy()
            if id_dia != today_id:
                return web.json_response(
                    {"ok": False, "error": "wrong_day", "expected_id_dia": today_id, "got": id_dia},
                    status=400,
                )

            # Marcar diaria 5 en el bot (siempre): habilita `?reclamar diaria 5`.
            db = getattr(self.bot, "economia_db", None)
            if not db:
                return web.json_response({"ok": False, "error": "db_unavailable"}, status=503)
            prog = db.get_progress_diaria(uid)
            if int(prog.get("dia_ahorcado") or 0) >= 1 and int(prog.get("dia_ahorcado_id") or 0) == id_dia:
                return web.json_response({"ok": False, "error": "already_submitted"}, status=409)
            db.mark_diaria_ahorcado_result(uid, id_dia)

            # Publicar en Discord (por defecto, #general)
            ch_id = _env_int("AHORCADO_DAILY_CHANNEL_ID", 0) or _env_int("GENERAL_CHANNEL_ID", 0)
            if ch_id > 0:
                ch = self.bot.get_channel(ch_id)
                if isinstance(ch, (discord.TextChannel, discord.Thread)):
                    title = "🪢 Ahorcado del día"
                    who = f"<@{uid}>" if uid else (username or "Jugador")
                    status = "✅ Ganó" if ganado else "❌ Perdió"
                    cat_line = f"**Categoría:** {categoria}\n" if categoria else ""
                    desc = (
                        f"**Jugador:** {who}\n"
                        f"{cat_line}"
                        f"**Resultado:** {status}\n"
                        f"**Pistas:** {pistas}\n"
                        f"**Errores:** {errores}\n"
                        f"**Puntos (web):** {puntos}\n"
                        f"**ID día:** {id_dia}\n"
                        "Web: `www.animealtoque.com/ahorcado`"
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Cuando alguien pega el cuadrito del share del ahorcado, respondemos con embed + botones.
        if message.author.bot or not message.guild:
            return
        txt = (message.content or "").strip()
        if len(txt) < 30:
            return
        stats = _extract_share_stats(txt)
        if not stats:
            return
        if message.id in self._share_seen:
            return
        self._share_seen.add(message.id)
        if len(self._share_seen) > 600:
            # Bound simple (memoria).
            self._share_seen = set(list(self._share_seen)[-300:])

        day = int(stats.get("day") or 0)
        err = stats.get("err")
        hints = stats.get("hints")
        pts = stats.get("pts")
        grid = stats.get("grid") if isinstance(stats.get("grid"), list) else None
        # Heurística: si llegó a 5 errores en el share, asumimos derrota; si no, victoria.
        status = None
        try:
            if err is not None and int(err) >= 5:
                status = "❌ Perdió"
            elif err is not None:
                status = "✅ Ganó"
        except Exception:
            status = None

        parts = [f"**Jugador:** {message.author.mention}"]
        if day > 0:
            parts.append(f"**Día:** **{day}**")
        if status:
            parts.append(f"**Resultado:** {status}")
        if grid:
            # Bloque visual principal (como el share original).
            parts.append("```" + "\n".join(str(x) for x in grid) + "```")
        if pts is not None:
            parts.append(f"**Puntos:** **{pts}**")
        if err is not None:
            parts.append(f"**Errores:** **{err}**/5")
        if hints is not None:
            parts.append(f"**Pistas:** **{hints}**")
        parts.append("Web: `www.animealtoque.com/ahorcado`")
        parts.append("Tip: ranking del bot → **`?ahorcadotop`**")
        emb = discord.Embed(
            title="🪢 Ahorcado compartido",
            description="\n".join(parts)[:4096],
            color=discord.Color.dark_gold(),
        )
        try:
            await message.reply(
                embed=emb,
                view=_AhorcadoShareView(),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
        except Exception:
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AhorcadoDailyWebhookCog(bot))

