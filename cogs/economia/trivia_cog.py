# Trivia anime: 2 sorteos al día entre 12:00 y 22:00 (America/Montevideo), 30 s para responder.
# Primera respuesta correcta con !respuestapregunta gana puntos (REWARD_TRIVIA_WIN_POINTS).
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import discord
from discord.ext import commands

from .db_manager import EconomiaDBManagerV2

log = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo

    UY = ZoneInfo("America/Montevideo")
except Exception:  # pragma: no cover
    UY = None


def _uy_now() -> datetime:
    if UY:
        return datetime.now(tz=UY)
    return datetime.now(tz=timezone.utc)


def _norm_answer(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return "".join(s.split())


def _load_questions(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        log.warning("Archivo de trivia no encontrado: %s", path)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            q = str(item.get("q") or item.get("question") or "").strip()
            if not q:
                continue
            a_raw = item.get("a", item.get("answers", item.get("answer")))
            accepts: List[str] = []
            if isinstance(a_raw, list):
                accepts = [str(x).strip() for x in a_raw if str(x).strip()]
            elif isinstance(a_raw, str) and a_raw.strip():
                accepts = [a_raw.strip()]
            if not accepts:
                continue
            out.append({"q": q, "answers": accepts})
        return out
    except Exception as e:
        log.exception("Error leyendo trivia JSON: %s", e)
        return []


@dataclass
class ActiveRound:
    channel_id: int
    question: str
    answers_norm: Set[str]
    display_answers: str
    deadline: datetime
    winner_id: Optional[int] = None


class AnimeTriviaCog(commands.Cog, name="Trivia anime"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self._questions: List[Dict[str, Any]] = []
        self._questions_path_mtime: float = 0.0
        self._runner_task: Optional[asyncio.Task] = None
        self._timeout_task: Optional[asyncio.Task] = None
        self._round: Optional[ActiveRound] = None
        self._start_lock = asyncio.Lock()
        self._answer_lock = asyncio.Lock()

    def _questions_path(self) -> Path:
        raw = (os.getenv("TRIVIA_QUESTIONS_PATH") or "data/anime_trivia.json").strip()
        p = Path(raw)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[2] / p
        return p

    def _reload_questions_if_needed(self) -> None:
        path = self._questions_path()
        try:
            m = path.stat().st_mtime
        except OSError:
            return
        if m != self._questions_path_mtime or not self._questions:
            self._questions = _load_questions(path)
            self._questions_path_mtime = m
            log.info("Trivia: cargadas %s preguntas desde %s", len(self._questions), path)

    def _general_channel_id(self) -> int:
        """La trivia solo se publica en #general (GENERAL_CHANNEL_ID / task_config)."""
        ch = int(os.getenv("GENERAL_CHANNEL_ID", "0") or 0)
        if ch:
            return ch
        tc = getattr(self.bot, "task_config", None) or {}
        return int((tc.get("channels") or {}).get("general") or 0)

    def _win_points(self) -> int:
        return max(0, int(os.getenv("REWARD_TRIVIA_WIN_POINTS", "25") or 0))

    def _seconds(self) -> int:
        return max(5, min(120, int(os.getenv("TRIVIA_SECONDS", "30") or 30)))

    async def cog_load(self) -> None:
        self._reload_questions_if_needed()
        self._runner_task = asyncio.create_task(self._scheduler_loop(), name="trivia_scheduler")

    async def cog_unload(self) -> None:
        if self._runner_task:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

    def _ensure_daily_schedule(self, day: date) -> List[datetime]:
        k_fire = f"trivia_uy_fires_{day.isoformat()}"
        raw = self.db.bot_meta_get(k_fire)
        if raw and UY:
            try:
                ts_list = json.loads(raw)
                if isinstance(ts_list, list) and len(ts_list) == 2:
                    out: List[datetime] = []
                    for x in ts_list:
                        ts = float(x)
                        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(UY)
                        out.append(dt)
                    return sorted(out)
            except Exception:
                pass
        if not UY:
            return []
        noon = datetime.combine(day, time(12, 0), tzinfo=UY)
        end = datetime.combine(day, time(22, 0), tzinfo=UY)
        span = int((end - noon).total_seconds())
        if span < 600:
            return []
        a = random.randint(0, span)
        b = random.randint(0, span)
        for _ in range(80):
            if abs(a - b) >= 300:
                break
            b = random.randint(0, span)
        t1 = noon + timedelta(seconds=min(a, b))
        t2 = noon + timedelta(seconds=max(a, b))
        fires = sorted([t1, t2])
        self.db.bot_meta_set(
            k_fire,
            json.dumps([t.astimezone(timezone.utc).timestamp() for t in fires]),
        )
        return fires

    def _done_count(self, day: date) -> int:
        raw = self.db.bot_meta_get(f"trivia_uy_done_{day.isoformat()}")
        try:
            return max(0, min(2, int(raw or "0")))
        except ValueError:
            return 0

    def _inc_done(self, day: date) -> None:
        n = self._done_count(day) + 1
        self.db.bot_meta_set(f"trivia_uy_done_{day.isoformat()}", str(n))

    async def _scheduler_loop(self) -> None:
        await self.bot.wait_until_ready()
        while True:
            try:
                await asyncio.sleep(5)
                if not UY:
                    continue
                now = _uy_now()
                day = now.date()
                if self._round:
                    continue
                done = self._done_count(day)
                if done >= 2:
                    continue
                fires = self._ensure_daily_schedule(day)
                if len(fires) < 2:
                    continue
                next_fire = fires[done]
                if now >= next_fire:
                    async with self._start_lock:
                        if self._round:
                            continue
                        await self._start_round(day)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("trivia scheduler")

    async def _start_round(self, day: date) -> None:
        self._reload_questions_if_needed()
        if not self._questions:
            log.warning("Trivia: sin preguntas; se marca ronda como hecha.")
            self._inc_done(day)
            return

        ch_id = self._general_channel_id()
        if not ch_id:
            log.warning("Trivia: falta GENERAL_CHANNEL_ID en .env (solo se publica ahí).")
            return

        channel = self.bot.get_channel(ch_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(ch_id)
            except Exception:
                log.warning("Trivia: no se pudo resolver el canal %s", ch_id)
                return
        if not isinstance(channel, discord.TextChannel):
            return

        pick = random.choice(self._questions)
        q = pick["q"]
        answers: List[str] = pick["answers"]
        norm_set = {_norm_answer(a) for a in answers if _norm_answer(a)}
        if not norm_set:
            self._inc_done(day)
            return

        sec = self._seconds()
        now = _uy_now()
        deadline = now + timedelta(seconds=sec)
        pts = self._win_points()

        emb = discord.Embed(
            title=f"Trivia anime — {sec} segundos",
            description=f"{q}\n\nEscribí: `!respuestapregunta` + tu respuesta\n"
            f"Primer acierto: **+{pts}** pts",
            color=discord.Color.orange(),
        )
        emb.set_footer(text="#general · America/Montevideo · primera respuesta correcta")

        try:
            await channel.send(embed=emb)
        except Exception as e:
            log.warning("Trivia: no se pudo enviar al canal: %s", e)
            return

        self._round = ActiveRound(
            channel_id=channel.id,
            question=q,
            answers_norm=norm_set,
            display_answers=answers[0],
            deadline=deadline,
        )
        self._inc_done(day)

        if self._timeout_task:
            self._timeout_task.cancel()
        self._timeout_task = asyncio.create_task(self._timeout_after(sec), name="trivia_timeout")

    async def _timeout_after(self, sec: float) -> None:
        try:
            await asyncio.sleep(sec + 0.5)
        except asyncio.CancelledError:
            return
        rnd = self._round
        if not rnd or rnd.winner_id:
            return
        ch = self.bot.get_channel(rnd.channel_id)
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(
                    f"⏱️ **Se acabó el tiempo.** Nadie acertó a tiempo.\n"
                    f"Respuesta aceptada: **{discord.utils.escape_markdown(rnd.display_answers)}**"
                )
            except Exception:
                pass
        self._round = None

    @commands.command(name="respuestapregunta", aliases=["triviaresp", "rtrivia"])
    async def respuesta_pregunta(self, ctx: commands.Context, *, texto: Optional[str] = None):
        if ctx.author.bot or not ctx.guild:
            return
        async with self._answer_lock:
            rnd = self._round
            if not rnd:
                await ctx.reply("No hay trivia activa en este momento.", mention_author=False)
                return
            if ctx.channel.id != rnd.channel_id:
                return
            if rnd.winner_id:
                await ctx.reply("Ya hubo un ganador en esta ronda.", mention_author=False)
                return
            if _uy_now() > rnd.deadline:
                await ctx.reply("Se acabó el tiempo para esta pregunta.", mention_author=False)
                return
            guess = (texto or "").strip()
            if not guess:
                await ctx.reply("Usá: `!respuestapregunta` seguido de tu respuesta.", mention_author=False)
                return

            g_norm = _norm_answer(guess)
            if not g_norm or g_norm not in rnd.answers_norm:
                await ctx.send(f"❌ **{ctx.author.display_name}** falló.")
                return

            rnd.winner_id = ctx.author.id
            pts = self._win_points()
            if pts > 0:
                self.db.modify_points(ctx.author.id, pts)
            if self._timeout_task:
                self._timeout_task.cancel()
                self._timeout_task = None
            self._round = None

        await ctx.send(
            f"✅ **{ctx.author.mention}** respondió bien primero."
            + (f" +**{pts}** puntos." if pts > 0 else "")
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnimeTriviaCog(bot))
