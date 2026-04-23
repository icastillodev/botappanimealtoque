# Trivia anime: N sorteos al día entre 12:00 y 22:00 (America/Montevideo), tiempo configurable (por defecto 5 min).
# Primera respuesta correcta (?r, ?respuestapregunta o línea corta / responder …) gana puntos y suma al ranking.
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
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


def _strip_trivia_answer_prefixes(text: str) -> str:
    """Quita `responder …` / `respuesta …` al inicio (con o sin `?`)."""
    s = (text or "").strip()
    for rx in (
        r"(?is)^responder[:\s,;.\-]+(.+)$",
        r"(?is)^respondiendo[:\s,;.\-]+(.+)$",
        r"(?is)^respuesta[:\s,;.\-]+(.+)$",
    ):
        m = re.match(rx, s)
        if m:
            return m.group(1).strip()
    return s


def _expand_accepted_norms_for_one(answer: str) -> Set[str]:
    """
    Acepta la frase completa sin espacios y también tokens sueltos (nombre, apellido,
    primer+último pegado) para que cuente `?r Nombre` o solo el apellido.
    """
    out: Set[str] = set()
    a = str(answer or "").strip()
    if not a:
        return out
    for chunk in re.split(r"[,;|/]+", a):
        chunk = chunk.strip()
        if not chunk:
            continue
        full = _norm_answer(chunk)
        if full:
            out.add(full)
        words = re.findall(r"[\wáéíóúÁÉÍÓÚñÑ]+", chunk, flags=re.I)
        meaningful: List[str] = []
        for w in words:
            nw = _norm_answer(w)
            if len(nw) >= 2:
                meaningful.append(w)
                out.add(nw)
        if len(meaningful) >= 2:
            out.add(_norm_answer(meaningful[0]))
            out.add(_norm_answer(meaningful[-1]))
            # "Nombre Apellido" o "Apellido Nombre" pegado (mismo resultado que sin espacios)
            out.add(_norm_answer(meaningful[0] + meaningful[-1]))
            out.add(_norm_answer(meaningful[-1] + meaningful[0]))
    return out


def _expand_all_accepted_norms(answers: List[str]) -> Set[str]:
    acc: Set[str] = set()
    for a in answers:
        acc.update(_expand_accepted_norms_for_one(a))
    return {x for x in acc if x}


def _plain_line_as_trivia_guess(content: str) -> Optional[str]:
    """
    Mensaje sin `?`: una línea corta o que empiece por `responder`/`respuesta`.
    Evita enganchar charla larga de #general.
    """
    raw = (content or "").strip()
    if not raw or raw.lstrip().startswith("?"):
        return None
    if "\n" in raw:
        return None
    low = raw.lower()
    if low.startswith("responder") or low.startswith("respondiendo") or low.startswith("respuesta"):
        return _strip_trivia_answer_prefixes(raw)
    if len(raw) > 72:
        return None
    parts = raw.split()
    if len(parts) > 8:
        return None
    return raw


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
        """Tiempo para responder (por defecto 300 s = 5 min)."""
        return max(30, min(600, int(os.getenv("TRIVIA_SECONDS", "300") or 300)))

    def _rounds_per_day(self) -> int:
        return max(1, min(8, int(os.getenv("TRIVIA_ROUNDS_PER_DAY", "3") or 3)))

    def _min_gap_seconds(self) -> int:
        return max(120, min(3600, int(os.getenv("TRIVIA_MIN_GAP_SECONDS", "300") or 300)))

    def _plain_messages_allowed(self) -> bool:
        """
        Si es False (TRIVIA_PLAIN_MESSAGE=0), no se escanean mensajes sin `?` en #general:
        menos trabajo en on_message; hay que usar `?r` / `?respuestapregunta`.
        """
        raw = (os.getenv("TRIVIA_PLAIN_MESSAGE") or "1").strip().lower()
        return raw not in ("0", "false", "no", "off")

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
        r = self._rounds_per_day()
        k_fire = f"trivia_uy_fires_{day.isoformat()}"
        raw = self.db.bot_meta_get(k_fire)
        if raw and UY:
            try:
                ts_list = json.loads(raw)
                if isinstance(ts_list, list) and len(ts_list) == r:
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
        gap = self._min_gap_seconds()
        if span < gap * (r - 1) + 60:
            return []
        pts: Optional[List[int]] = None
        for _ in range(500):
            cand = sorted(random.randint(0, span) for _ in range(r))
            if all(cand[i + 1] - cand[i] >= gap for i in range(r - 1)):
                pts = cand
                break
        if not pts:
            return []
        fires = [noon + timedelta(seconds=p) for p in pts]
        self.db.bot_meta_set(
            k_fire,
            json.dumps([t.astimezone(timezone.utc).timestamp() for t in fires]),
        )
        return fires

    def _done_count(self, day: date) -> int:
        r = self._rounds_per_day()
        raw = self.db.bot_meta_get(f"trivia_uy_done_{day.isoformat()}")
        try:
            return max(0, min(r, int(raw or "0")))
        except ValueError:
            return 0

    def _inc_done(self, day: date) -> None:
        r = self._rounds_per_day()
        n = min(r, self._done_count(day) + 1)
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
                r = self._rounds_per_day()
                done = self._done_count(day)
                if done >= r:
                    continue
                fires = self._ensure_daily_schedule(day)
                if len(fires) < r:
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
        norm_set = _expand_all_accepted_norms(answers)
        if not norm_set:
            self._inc_done(day)
            return

        sec = self._seconds()
        now = _uy_now()
        deadline = now + timedelta(seconds=sec)
        pts = self._win_points()
        rday = self._rounds_per_day()
        hecho = self._done_count(day)

        plain = self._plain_messages_allowed()
        formas = (
            f"**Formas válidas:**\n"
            f"• `?r` + respuesta — *ejemplo:* `?r Kaneki`\n"
            f"• `?respuestapregunta` / `?rtrivia` + respuesta\n"
            f"• Podés poner **solo nombre, solo apellido, nombre+apellido** (en cualquier orden pegado) si alcanza.\n"
        )
        if plain:
            formas += (
                "• **Sin `?`:** una línea corta o `responder …` / `respuesta …` en el mismo canal.\n"
            )
        else:
            formas += (
                "• En este servidor las respuestas van **con `?`** (`?r …`) para no leer todo el chat.\n"
            )
        emb = discord.Embed(
            title="Trivia anime",
            description=(
                f"{q}\n\n"
                f"⏱️ **{sec}s** — el **primero** en acertar gana.\n"
                f"{formas}\n"
                f"📅 Hoy van **{rday}** preguntas programadas; esta es la **{hecho + 1}ª**.\n"
                f"🏆 Ranking: `?triviatop` · tu puesto: `?triviami`"
                + (f"\n🎁 El ganador suma **{pts}** Toque points." if pts > 0 else "")
            ),
            color=discord.Color.orange(),
        )
        foot = f"{sec}s · ?r" + (" · línea sin `?`" if plain else " · solo comandos con `?`")
        emb.set_footer(text=f"{foot} · primera respuesta correcta gana")

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

    @commands.command(name="respuestapregunta", aliases=["triviaresp", "rtrivia", "r"])
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

            guess_raw = _strip_trivia_answer_prefixes((texto or "").strip())
            if not guess_raw:
                await ctx.reply(
                    "Usá **`?r`** + respuesta (ej. `?r Kaneki`) o `?respuestapregunta` + respuesta.",
                    mention_author=False,
                )
                return
            g_norm = _norm_answer(guess_raw)
            if not g_norm:
                await ctx.reply("Escribí una respuesta con letras o números.", mention_author=False)
                return

            if g_norm not in rnd.answers_norm:
                await ctx.send(f"❌ **{ctx.author.display_name}** falló.")
                return

            rnd.winner_id = ctx.author.id
            pts = self._win_points()
            if pts > 0:
                self.db.modify_points(ctx.author.id, pts)
            self.db.trivia_wins_increment(ctx.author.id)
            rank, wins = self.db.trivia_stats_rank_user(ctx.author.id)
            if self._timeout_task:
                self._timeout_task.cancel()
                self._timeout_task = None
            self._round = None

        extra = f" 🏆 **#{rank}** en trivia del servidor (**{wins}** victorias)." if wins > 0 else ""
        pts_part = f" Sumás **{pts}** {self._tq_emoji()}." if pts > 0 else ""
        await ctx.send(f"✅ **{ctx.author.mention}** respondió bien primero.{pts_part}{extra}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """En #general, durante la ronda: mensaje corto o `responder …` sin `?` (si TRIVIA_PLAIN_MESSAGE)."""
        if message.author.bot or not message.guild:
            return
        if not self._plain_messages_allowed():
            return
        rnd = self._round
        if not rnd or message.channel.id != rnd.channel_id:
            return
        raw = (message.content or "").strip()
        if not raw or raw.lstrip().startswith("?"):
            return
        maybe = _plain_line_as_trivia_guess(raw)
        if not maybe:
            return
        guess_raw = _strip_trivia_answer_prefixes(maybe.strip())
        g_norm = _norm_answer(guess_raw)
        if not g_norm:
            return

        async with self._answer_lock:
            rnd = self._round
            if not rnd or rnd.channel_id != message.channel.id or rnd.winner_id:
                return
            if _uy_now() > rnd.deadline:
                return
            if g_norm not in rnd.answers_norm:
                return
            rnd.winner_id = message.author.id
            pts = self._win_points()
            if pts > 0:
                self.db.modify_points(message.author.id, pts)
            self.db.trivia_wins_increment(message.author.id)
            rank, wins = self.db.trivia_stats_rank_user(message.author.id)
            if self._timeout_task:
                self._timeout_task.cancel()
                self._timeout_task = None
            self._round = None

        extra = f" 🏆 **#{rank}** en trivia del servidor (**{wins}** victorias)." if wins > 0 else ""
        pts_part = f" Sumás **{pts}** {self._tq_emoji()}." if pts > 0 else ""
        try:
            await message.channel.send(
                f"✅ **{message.author.mention}** respondió bien primero.{pts_part}{extra}"
            )
        except discord.HTTPException:
            pass

    def _tq_emoji(self) -> str:
        try:
            from .toque_labels import toque_emote

            return str(toque_emote())
        except Exception:
            return "Toque points"

    @commands.command(name="triviatop", aliases=["toptrivia", "ranktrivia"])
    async def trivia_top(self, ctx: commands.Context, lim: Optional[int] = None):
        if not ctx.guild:
            return
        rows = self.db.trivia_stats_top(lim or 10)
        if not rows:
            await ctx.reply(
                "Todavía no hay victorias en trivia anime (hay que ser el **primero** en acertar cuando sale la pregunta).",
                mention_author=False,
            )
            return
        lines: List[str] = []
        for i, (uid, w) in enumerate(rows, start=1):
            m = ctx.guild.get_member(uid)
            name = m.display_name if m else f"ID {uid}"
            suf = "victoria" if w == 1 else "victorias"
            lines.append(f"`{i}.` **{discord.utils.escape_markdown(name)}** — {w} {suf}")
        emb = discord.Embed(
            title="🏆 Top trivia anime (primer acierto por ronda)",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )
        emb.set_footer(text="Solo cuenta ser el primero en acertar a tiempo · `?triviami`")
        await ctx.reply(embed=emb, mention_author=False)

    @commands.command(name="triviami", aliases=["mitrivia", "posiciontrivia"])
    async def trivia_me(self, ctx: commands.Context):
        if ctx.author.bot or not ctx.guild:
            return
        rank, wins = self.db.trivia_stats_rank_user(ctx.author.id)
        if wins <= 0:
            await ctx.reply(
                "No tenés victorias en trivia todavía: cuando el bot publique la pregunta en **#general**, "
                "tenés que ser **el primero** en acertar a tiempo (`?r`, `?respuestapregunta`, o `responder …` / una línea corta en **#general**).",
                mention_author=False,
            )
            return
        await ctx.reply(
            f"🎯 Tenés **{wins}** victorias en trivia anime → puesto **#{rank}** en el servidor. "
            f"Usá `?triviatop` para ver el ranking completo.",
            mention_author=False,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnimeTriviaCog(bot))
