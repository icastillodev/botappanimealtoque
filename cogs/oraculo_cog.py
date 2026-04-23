# Preguntas sí / no (40% sí, 40% no, 20% respuesta con % al azar).
# La IA local (Ollama) solo entra en preguntas “abiertas”; el resto siempre va al dado (más divertido).
# Cuenta para la diaria + puntos extra (config .env).
from __future__ import annotations

import os
import random
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Literal, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from cogs.oracle_llm import oracle_local_reply, oracle_local_reply_followup


# Preguntas que no son un sí/no claro: mejor “charla” que un porcentaje místico.
_OPEN_QUESTION_RE = re.compile(
    r"(?isx)"
    r"(\b(cuánt|cuant)\w*|"
    r"\bcuál\b|\bcuales\b|"
    r"\b(cómo|como)\s+(está|esta|va|será|sera|fue|iban|ibas|anduv|andaba)\b|"
    r"\bcuándo\b|\bcuando\b\s+(sale|va|llega|empieza|termina)|"
    r"\bdónde\b|\bdonde\b\s+(está|esta|ver|mirar|consigo)|"
    r"por\s*qué|"
    r"\b(temporadas?|caps?\.?|capítulos?|episodios?|ep\.?)\b|"
    r"\bqué\s+opinas\b|\bque\s+opinas\b|\b(opinás|opinas|recomendás|recomendas)\b)",
)


def _is_open_ended_question(pregunta: str) -> bool:
    q = (pregunta or "").strip()
    if len(q) < 4:
        return False
    return bool(_OPEN_QUESTION_RE.search(q))


def _extract_topic_for_oracle(q: str) -> str:
    """Recorte legible del tema (para plantillas), sin intentar ‘entender’ de verdad."""
    t = " ".join((q or "").split())
    t = t.strip("¿?").strip()
    for pat in (
        r"(?i)\bva\s+a\s+tener\s+(.+)$",
        r"(?i)\btendrá\s+(.+)$",
        r"(?i)\bsobre\s+(.+)$",
        r"(?i)\bde\s+la\s+serie\s+(.+)$",
        r"(?i)\bacerca\s+de\s+(.+)$",
    ):
        m = re.search(pat, t)
        if m:
            cand = m.group(1).strip("? ").strip()
            if len(cand) >= 2:
                return cand[:120]
    words = t.split()
    if len(words) > 8:
        return " ".join(words[-10:])[:120]
    return t[:120] if t else "eso"


def _oracle_open_answer(pregunta: str) -> str:
    """Respuesta ‘tipo IA básica’ pero 100 % plantillas + azar (sin API)."""
    raw_topic = _extract_topic_for_oracle(pregunta)
    topic = discord.utils.escape_markdown(raw_topic) if raw_topic else "eso"
    n1 = random.randint(2, 4)
    n2 = random.randint(5, 10)
    n3 = random.randint(1, 3)
    chaos = random.randint(40, 95)
    return random.choice(
        [
            f"Si fuera una IA **de verdad** te mandaría a buscar fuentes. Como soy **random con personalidad**: "
            f"sobre **{topic}** yo tiraría **{n1}** temporadas más… más o menos, con un **{chaos}%** de margen de error y cero responsabilidad civil.",
            f"Opinión **inventada** (pero con onda) sobre **{topic}**: anuncian **{n2}** cosas nuevas, **{n3}** son filler aprobado por el comité del caos, y el fandom discute igual.",
            f"Mi **cerebro de lata** interpreta **{topic}** así: el universo tira un dado, sale **{n1 + n3}**, y alguien en Twitter ya lo sabía desde el capítulo 1.",
            f"Sobre **{topic}**: ni idea real, pero para no quedar en silencio te digo que suena a **{n2}** en la escala de ‘confío en el estudio’ y **{n3}** en la de ‘me van a hacer llorar igual’.",
            f"Modo **charla de café**: **{topic}** me huele a **{n1}** vueltas de tuerca narrativas y **{chaos}%** de drama innecesario… o sea, entretenimiento asegurado.",
        ]
    )


def _oracle_echo_flavor(pregunta: str) -> str:
    """
    «Mini personalidad» sin API externa: devuelve una línea que nombra un recorte de la pregunta (o vacío).
    No interpreta de verdad; solo flavor para roleplay.
    """
    q = re.sub(r"\s+", " ", (pregunta or "").strip())
    if len(q) < 4:
        return ""
    clip = q[:100] + ("…" if len(q) > 100 else "")
    return random.choice(
        [
            f"_El eco de «{clip}» vibra un instante y se disuelve._",
            f"_Los astros archivan «{clip}» en un cajón sin etiqueta._",
            f"_Sobre «{clip}», el oráculo no firma cheques: solo tira el dado._",
            f"_Tu «{clip}» quedó registrada en el libro de las preguntas ruidosas._",
            f"_Ni el bot entiende del todo «{clip}», pero hace como que sí._",
        ]
    )


def _roll_oracle() -> Tuple[str, str, int]:
    """
    Devuelve (categoría, texto_respuesta, dado 1-100 usado).
    1-40 sí, 41-80 no, 81-100 probabilístico.
    """
    dado = random.randint(1, 100)
    si_msg = random.choice(
        [
            "Sí.",
            "¡Sí!",
            "Por supuesto que sí.",
            "El cosmos asiente.",
            "Afirmativo.",
            "Totalmente sí.",
        ]
    )
    no_msg = random.choice(
        [
            "No.",
            "¡No!",
            "Ni en pedo (no).",
            "Negativo.",
            "Mejor no contar con eso.",
            "El destino dice que no.",
        ]
    )
    if dado <= 40:
        return "Sí", si_msg, dado
    if dado <= 80:
        return "No", no_msg, dado
    pct = random.randint(5, 95)
    lean_si = random.choice([True, False])
    if lean_si:
        prob_msg = random.choice(
            [
                f"Ni sí ni no… tirando **{pct}%** a favor del **sí**.",
                f"Duda razonable: **{pct}%** de que termine en **sí**.",
                f"Las runas marcan **{pct}%** sí (o algo así).",
            ]
        )
    else:
        prob_msg = random.choice(
            [
                f"Ni sí ni no… **{pct}%** de inclinación al **no**.",
                f"Probabilidad estimada: **{pct}%** hacia el **no**.",
                f"El dado flojo: **{pct}%** no, **{100 - pct}%** sí (o al revés mañana).",
            ]
        )
    return "Probabilidad", prob_msg, dado


def _roll_oracle_for_question(pregunta: str) -> Tuple[str, str, int]:
    """
    Si la pregunta parece abierta (cuántas, cuándo, temporadas…), contesta en modo ‘opinión’.
    Si no, mantiene sí / no / % como antes.
    """
    if _is_open_ended_question(pregunta):
        return "open", _oracle_open_answer(pregunta), random.randint(1, 100)
    cat, body, dado = _roll_oracle()
    return cat, body, dado


_ORACLE_EMBED_TITLE = "🔮 Consulta al oráculo"

_ORACLE_THREAD_EXPIRED = [
    "⏳ **Se cerró la ventana** de esta consulta con el oráculo: el tiempo corrió y acá no queda “guardar partida”.\n"
    "Si querés seguir, abrí una **consulta nueva** con `?pregunta …` o arrobándome con la duda.",
    "⏳ **El velo bajó** — esta conversación con el oráculo ya no cuenta como activa.\n"
    "Tirá de nuevo con `?pregunta …` o mencionándome, y arrancamos otra lectura.",
    "⏳ **Pasó el tiempo** del hilo místico; no es que me enoje, es que el bot no archiva eternamente.\n"
    "Nueva consulta: `?pregunta …` o arrobándome con la duda.",
]

_ORACLE_QUIP_NOT_ORACLE = [
    "Ese mensaje mío **no** era el 🔮 del oráculo: acá no hay segunda lectura, solo ruido de fondo 😌",
    "La bola de cristal **no firma** ese mensaje… si querés charla con el oráculo, respondé al embed **Consulta al oráculo** o usá `?pregunta`.",
    "Jaja no—ahí estaba en **modo decoración**. El hilo serio es solo bajo el embed del oráculo o con `?pregunta`.",
    "Mi yo del pasado en ese mensaje no traía traje de oráculo; probá otra vez citando el **último** 🔮 o con `?pregunta`.",
]


def _looks_like_new_oracle_question(text: str) -> bool:
    """Si parece una consulta nueva, la procesamos aunque el reply no sea al embed del oráculo."""
    s = " ".join((text or "").split()).strip()
    if len(s) < 10:
        return False
    if "?" in s or "¿" in s:
        return True
    low = s.lower()
    if _is_open_ended_question(s):
        return True
    starters = (
        "qué ", "que ", "quién ", "quien ", "cuándo ", "cuando ", "dónde ", "donde ",
        "cuánt", "cuant", "por qué", "por que ", "va a ", "habrá ", "habra ",
        "debería ", "deberia ", "creés ", "crees ", "pensás ", "piensas ",
    )
    return any(low.startswith(st) for st in starters)


def _template_followup_no_llm(user_line: str) -> str:
    low = (user_line or "").lower()
    if any(w in low for w in ("gracias", "thank", "genial", "joya", "dale", "ok", "oki")):
        return random.choice(
            [
                "De nada; el cosmos cobra después, con intereses emocionales.",
                "No hay de qué — la próxima consulta sale con recargo místico.",
                "Servido; guardá el ticket por si el destino pide devolución.",
            ]
        )
    if any(w in low for w in ("no entend", "explic", "o sea", "osea", "pero")):
        return random.choice(
            [
                "Resumo: la primera tirada ya fue; si querés precision teatro, nueva `?pregunta`.",
                "En criollo: fue humo sagrado con firma; el detalle fino no entra en el presupuesto del bot.",
            ]
        )
    return random.choice(
        [
            "La bola ya habló una vez; si querés otra vuelta seria-ridícula, tirá `?pregunta` de nuevo.",
            "Seguimiento en modo **sin IA**: fue lindo el intento, pero acá corta el cable; consulta fresca con `?pregunta`.",
            "Mi segunda opinión gratis venció en el capítulo anterior — renová con una consulta nueva.",
        ]
    )


@dataclass
class OraclePending:
    """Estado para seguir la charla respondiendo al último mensaje del oráculo en un canal."""

    bot_message_id: int
    original_question: str
    last_answer: str
    response_kind: Literal["yesno", "open", "llm"]
    deadline_monotonic: float


class OraculoCog(commands.Cog, name="Oráculo"):
    """Preguntas al bot (sí / no / %)."""

    # Mismo criterio que @commands.cooldown(2, 5, commands.BucketType.user) en !pregunta
    _COOLDOWN_RATE = 2
    _COOLDOWN_PER_SEC = 5.0

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = getattr(bot, "economia_db", None)
        self.task_config = getattr(bot, "task_config", None) or {}
        self._oracle_times: dict[int, Deque[float]] = defaultdict(deque)
        # Seguimiento: (guild_id, channel_id, user_id) → última consulta respondible
        self._oracle_pending: Dict[Tuple[int, int, int], OraclePending] = {}
        self._followup_times: dict[int, Deque[float]] = defaultdict(deque)

    def _oracle_cooldown_retry_after(self, user_id: int) -> float:
        """Si está en cooldown, devuelve segundos restantes; si no, 0."""
        now = time.monotonic()
        dq = self._oracle_times[user_id]
        while dq and dq[0] < now - self._COOLDOWN_PER_SEC:
            dq.popleft()
        if len(dq) >= self._COOLDOWN_RATE:
            return max(0.1, self._COOLDOWN_PER_SEC - (now - dq[0]))
        return 0.0

    def _oracle_mark_use(self, user_id: int) -> None:
        self._oracle_times[user_id].append(time.monotonic())

    def _conversation_ttl_seconds(self) -> int:
        try:
            return max(60, min(3600, int(os.getenv("ORACLE_CONVERSATION_TTL_SECONDS", "300") or 300)))
        except ValueError:
            return 300

    def _followup_cooldown_retry_after(self, user_id: int) -> float:
        """Evita spam en el hilo del oráculo (más suave que la consulta inicial)."""
        window = 40.0
        max_msgs = 10
        now = time.monotonic()
        dq = self._followup_times[user_id]
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= max_msgs:
            return max(0.5, window - (now - dq[0]))
        return 0.0

    def _followup_mark(self, user_id: int) -> None:
        self._followup_times[user_id].append(time.monotonic())

    @staticmethod
    def _pending_key(message: discord.Message) -> Tuple[int, int, int]:
        return message.guild.id, message.channel.id, message.author.id

    def _register_oracle_pending(
        self,
        bot_message: discord.Message,
        user: discord.abc.User,
        *,
        original_question: str,
        last_answer: str,
        response_kind: Literal["yesno", "open", "llm"],
    ) -> None:
        g = bot_message.guild
        if not g:
            return
        key = (g.id, bot_message.channel.id, user.id)
        self._oracle_pending[key] = OraclePending(
            bot_message_id=bot_message.id,
            original_question=(original_question or "").strip()[:900],
            last_answer=(last_answer or "").strip()[:900],
            response_kind=response_kind,
            deadline_monotonic=time.monotonic() + float(self._conversation_ttl_seconds()),
        )

    def _refresh_oracle_pending(
        self,
        key: Tuple[int, int, int],
        *,
        new_bot_message: discord.Message,
        new_last_answer: str,
    ) -> None:
        cur = self._oracle_pending.get(key)
        if not cur:
            return
        self._oracle_pending[key] = OraclePending(
            bot_message_id=new_bot_message.id,
            original_question=cur.original_question,
            last_answer=(new_last_answer or "").strip()[:900],
            response_kind=cur.response_kind,
            deadline_monotonic=time.monotonic() + float(self._conversation_ttl_seconds()),
        )

    @staticmethod
    def _message_is_oracle_consulta(msg: discord.Message) -> bool:
        for e in msg.embeds or []:
            t = (e.title or "").strip()
            if t == _ORACLE_EMBED_TITLE or "Consulta al oráculo" in t:
                return True
            low = t.lower()
            if ("oráculo" in low or "oraculo" in low) and "seguimiento" in low:
                return True
        return False

    def _strip_mentions_for_question(self, content: str) -> str:
        s = re.sub(r"<@!?\d+>", " ", content or "")
        s = re.sub(r"<#\d+>", " ", s)
        return " ".join(s.split()).strip()

    async def _build_oracle_embed(
        self,
        *,
        nombre_visible: str,
        mencion: str,
        pregunta: str,
        author_id: int,
    ) -> Tuple[discord.Embed, str, Literal["yesno", "open", "llm"]]:
        assert self.db is not None
        self.db.ensure_user_exists(author_id)
        pq = pregunta.strip()
        if _is_open_ended_question(pq):
            llm = await oracle_local_reply(pq)
            if llm:
                body, response_kind = llm, "llm"
            else:
                kind, body, _ = _roll_oracle_for_question(pq)
                response_kind = "open" if kind == "open" else "yesno"
        else:
            kind, body, _ = _roll_oracle_for_question(pq)
            response_kind = "open" if kind == "open" else "yesno"
        self._record_oracle_use(author_id)
        emb = self._embed_respuesta(
            nombre_visible=nombre_visible,
            mencion=mencion,
            pregunta=pregunta.strip(),
            body=body,
            response_kind=response_kind,
        )
        return emb, body, response_kind

    async def _send_oracle_embed(
        self,
        channel: discord.abc.Messageable,
        *,
        author: discord.abc.User,
        nombre_visible: str,
        pregunta: str,
        reference: Optional[discord.Message] = None,
    ) -> Optional[discord.Message]:
        if not self.db:
            await channel.send("Economía no disponible.", reference=reference, mention_author=False)
            return None
        embed, body, response_kind = await self._build_oracle_embed(
            nombre_visible=nombre_visible,
            mencion=author.mention,
            pregunta=pregunta.strip(),
            author_id=author.id,
        )
        sent = await channel.send(embed=embed, reference=reference, mention_author=False)
        if isinstance(sent, discord.Message) and sent.guild:
            self._register_oracle_pending(
                sent,
                author,
                original_question=pregunta.strip(),
                last_answer=body,
                response_kind=response_kind,
            )
        return sent

    async def _send_oracle_followup(
        self,
        channel: discord.abc.Messageable,
        *,
        author: discord.abc.User,
        nombre_visible: str,
        user_line: str,
        pending: OraclePending,
        reference: discord.Message,
        pending_key: Tuple[int, int, int],
    ) -> None:
        """Respuesta a quien citó el último embed del oráculo (sin sumar otra diaria)."""
        llm = await oracle_local_reply_followup(
            pending.original_question,
            pending.last_answer,
            user_line,
        )
        if llm:
            body, rk = llm, "llm"
        else:
            body, rk = _template_followup_no_llm(user_line), "open"

        q_short = (pending.original_question or "")[:700]
        body_show = discord.utils.escape_markdown(body) if rk == "llm" else body
        desc = (
            f"{author.mention} **({nombre_visible})** sigue el hilo:\n"
            f"> {discord.utils.escape_markdown(user_line)[:500]}\n\n"
            f"**Oráculo:** {body_show}\n\n"
            f"_Consulta inicial:_ {discord.utils.escape_markdown(q_short)[:350]}"
        )
        if len(desc) > 4090:
            desc = desc[:4087] + "…"
        emb = discord.Embed(
            title="🔮 Oráculo · seguimiento",
            description=desc,
            color=discord.Color.dark_magenta(),
        )
        mod = (os.getenv("ORACLE_MODEL") or "local").strip()
        sec = self._conversation_ttl_seconds()
        tail = f"Seguimiento: respondé a **este** mensaje (~{max(1, sec // 60)} min)." if sec >= 120 else f"Seguimiento: ~{sec}s."
        if rk == "llm":
            emb.set_footer(text=f"IA local · {mod} · {tail}")
        else:
            emb.set_footer(text=f"Modo plantilla (sin IA) · {tail}")

        sent = await channel.send(embed=emb, reference=reference, mention_author=False)
        if isinstance(sent, discord.Message) and sent.guild:
            self._refresh_oracle_pending(
                pending_key,
                new_bot_message=sent,
                new_last_answer=body,
            )

    def _record_oracle_use(self, user_id: int) -> Tuple[int, int, int, int]:
        """
        Suma contador diario y opcionalmente puntos.
        Devuelve (puntos_otorgados, preguntas_hoy_tras_esta, max_con_puntos, pts_por_pregunta).
        """
        if not self.db:
            return 0, 0, 0, 0
        fecha, _ = self.db.get_current_date_keys()
        prog = self.db.get_progress_diaria(user_id)
        n_before = int(prog.get("oraculo_preguntas") or 0)
        rw = (self.task_config.get("rewards") or {})
        per = int(rw.get("oracle_pregunta_points", 3))
        mx = int(rw.get("oracle_max_preguntas_con_puntos", 5))
        gained = 0
        if per > 0 and n_before < mx:
            self.db.modify_points(user_id, per, gastar=False)
            gained = per
        self.db.update_task_diaria(user_id, "oraculo_preguntas", fecha, 1)
        n_after = n_before + 1
        return gained, n_after, mx, per

    def _embed_respuesta(
        self,
        *,
        nombre_visible: str,
        mencion: str,
        pregunta: str,
        body: str,
        response_kind: Literal["yesno", "open", "llm"] = "yesno",
    ) -> discord.Embed:
        q = (pregunta or "").strip()[:900] or "*(silencio místico)*"
        flavor = "" if response_kind == "llm" else _oracle_echo_flavor(pregunta)
        body_show = discord.utils.escape_markdown(body) if response_kind == "llm" else body
        if response_kind == "llm":
            bloque = (
                f"{mencion} **({nombre_visible})** preguntó:\n"
                f"> {q}\n\n"
                f"**Oráculo (IA local, respuesta corta):** {body_show}"
            )
        elif response_kind == "open":
            bloque = (
                f"{mencion} **({nombre_visible})** preguntó:\n"
                f"> {q}\n\n"
                f"**Modo charla (sin IA local, plantillas + humor):**\n"
                f"{body_show}"
            )
        else:
            bloque = (
                f"{mencion} **({nombre_visible})** preguntó:\n"
                f"> {q}\n\n"
                f"**La respuesta es:** {body_show}"
            )
        desc = f"{bloque}\n\n{flavor}" if flavor else bloque
        if len(desc) > 4090:
            desc = desc[:4087] + "…"
        emb = discord.Embed(
            title=_ORACLE_EMBED_TITLE,
            description=desc,
            color=discord.Color.dark_magenta(),
        )
        foot_bits: list[str] = []
        if response_kind == "llm":
            mod = (os.getenv("ORACLE_MODEL") or "local").strip()
            foot_bits.append(f"IA local (Ollama) · {mod} · puede inventar; no es fuente oficial.")
        elif response_kind == "open":
            foot_bits.append("Respuesta inventada por reglas del bot · no sustituye buscar info oficial.")
        else:
            foot_bits.append("Sí / no / probabilidad a la uruguaya · no es verdad revelada.")
        sec = self._conversation_ttl_seconds()
        if sec >= 120:
            foot_bits.append(f"Seguimiento: respondé a este mensaje (~{max(1, sec // 60)} min).")
        else:
            foot_bits.append(f"Seguimiento: respondé a este mensaje (~{sec}s).")
        emb.set_footer(text=" · ".join(foot_bits))
        return emb

    @commands.command(name="pregunta", aliases=["consulta", "8ball", "bola", "oraculo"])
    async def pregunta_prefijo(self, ctx: commands.Context, *, texto: str = None):
        if not texto or not str(texto).strip():
            await ctx.send("Usá: `?pregunta ¿va a salir bien el stream?` (escribí la pregunta después del comando).")
            return
        wait = self._oracle_cooldown_retry_after(ctx.author.id)
        if wait > 0:
            await ctx.send(f"Esperá **{wait:.1f}s** entre consultas al oráculo.", delete_after=6)
            return
        nombre = ctx.author.display_name if isinstance(ctx.author, discord.Member) else str(ctx.author)
        await self._send_oracle_embed(
            ctx.channel,
            author=ctx.author,
            nombre_visible=nombre,
            pregunta=texto.strip(),
            reference=None,
        )
        self._oracle_mark_use(ctx.author.id)

    @app_commands.command(
        name="aat-consulta",
        description="Sí/no/% con dado; charla con IA solo en preguntas abiertas. Seguimiento citando embed. ?pregunta.",
    )
    @app_commands.describe(pregunta="Sí/no o abierta (cuántas, cuándo, qué opinás…). Lo abierto puede usar IA si está configurada.")
    async def consulta_slash(self, interaction: discord.Interaction, pregunta: str):
        if not pregunta or not pregunta.strip():
            await interaction.response.send_message("Escribí una pregunta.", ephemeral=True)
            return
        wait = self._oracle_cooldown_retry_after(interaction.user.id)
        if wait > 0:
            await interaction.response.send_message(
                f"Esperá **{wait:.1f}s** entre consultas al oráculo.",
                ephemeral=True,
            )
            return
        if not self.db:
            await interaction.response.send_message("Economía no disponible.", ephemeral=True)
            return
        nombre = interaction.user.display_name
        mencion = interaction.user.mention
        embed, body, response_kind = await self._build_oracle_embed(
            nombre_visible=nombre,
            mencion=mencion,
            pregunta=pregunta.strip(),
            author_id=interaction.user.id,
        )
        await interaction.response.send_message(embed=embed)
        self._oracle_mark_use(interaction.user.id)
        try:
            msg = await interaction.original_response()
        except discord.HTTPException:
            msg = None
        if isinstance(msg, discord.Message) and msg.guild:
            self._register_oracle_pending(
                msg,
                interaction.user,
                original_question=pregunta.strip(),
                last_answer=body,
                response_kind=response_kind,
            )

    async def _fetch_reference_message(self, message: discord.Message) -> Optional[discord.Message]:
        ref = message.reference
        if not ref or not ref.message_id:
            return None
        if isinstance(ref.resolved, discord.Message):
            return ref.resolved
        if getattr(ref, "cached_message", None):
            return ref.cached_message
        try:
            return await message.channel.fetch_message(ref.message_id)
        except (discord.NotFound, discord.HTTPException):
            return None

    async def _maybe_handle_oracle_thread_reply(self, message: discord.Message) -> bool:
        """
        True si el mensaje era reply al bot y ya lo tratamos (hilo del oráculo, tiempo vencido, o chiste corto).
        """
        me = self.bot.user
        if not me:
            return False
        ref_msg = await self._fetch_reference_message(message)
        if not ref_msg or ref_msg.author.id != me.id:
            return False

        key = self._pending_key(message)
        pending = self._oracle_pending.get(key)
        user_text = self._strip_mentions_for_question(message.content).strip()
        oracle_embed = self._message_is_oracle_consulta(ref_msg)

        try:
            # A) Reply al mensaje activo del hilo
            if pending and ref_msg.id == pending.bot_message_id:
                if time.monotonic() > pending.deadline_monotonic:
                    self._oracle_pending.pop(key, None)
                    await message.reply(random.choice(_ORACLE_THREAD_EXPIRED), mention_author=False)
                    return True
                if len(user_text) < 1:
                    await message.reply(
                        "Escribí algo en el mensaje para seguir el hilo (aunque sea un “¿y si…?”).",
                        mention_author=False,
                    )
                    return True
                fu = self._followup_cooldown_retry_after(message.author.id)
                if fu > 0:
                    await message.reply(
                        f"Despacito el hilo del oráculo: esperá **{fu:.1f}s**.",
                        mention_author=False,
                        delete_after=8,
                    )
                    return True
                self._followup_mark(message.author.id)
                nombre = (
                    message.author.display_name
                    if isinstance(message.author, discord.Member)
                    else str(message.author)
                )
                await self._send_oracle_followup(
                    message.channel,
                    author=message.author,
                    nombre_visible=nombre,
                    user_line=user_text,
                    pending=pending,
                    reference=message,
                    pending_key=key,
                )
                return True

            # B) Reply a un embed del oráculo que ya no es el activo (o hay otro más nuevo)
            if oracle_embed and pending and ref_msg.id != pending.bot_message_id:
                await message.reply(
                    "Esa lectura **ya no** es el hilo activo: respondé al **último** mensaje del oráculo "
                    "de esta charla o abrí una nueva con `?pregunta …`.",
                    mention_author=False,
                )
                return True

            # C) Embed del oráculo pero sin estado en memoria (reinicio / expiró hace rato)
            if oracle_embed and not pending:
                await message.reply(
                    "No retengo esa consulta en memoria (reinicio del bot o pasó demasiado tiempo).\n"
                    "Volvé a consultar con `?pregunta …` o arrobándome con la duda.",
                    mention_author=False,
                )
                return True

            # D) Reply a otro mensaje mío: si mandaron una pregunta de verdad, la procesamos
            if _looks_like_new_oracle_question(user_text):
                if not self.db:
                    await message.reply("Economía no disponible.", mention_author=False)
                    return True
                wait = self._oracle_cooldown_retry_after(message.author.id)
                if wait > 0:
                    await message.reply(
                        f"Esperá **{wait:.1f}s** entre consultas al oráculo.",
                        mention_author=False,
                        delete_after=8,
                    )
                    return True
                nombre = (
                    message.author.display_name
                    if isinstance(message.author, discord.Member)
                    else str(message.author)
                )
                await self._send_oracle_embed(
                    message.channel,
                    author=message.author,
                    nombre_visible=nombre,
                    pregunta=user_text,
                    reference=message,
                )
                self._oracle_mark_use(message.author.id)
                return True

            await message.reply(random.choice(_ORACLE_QUIP_NOT_ORACLE), mention_author=False)
            return True
        except discord.HTTPException:
            return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        me = self.bot.user
        if not me:
            return

        if message.reference:
            if await self._maybe_handle_oracle_thread_reply(message):
                return

        if me not in message.mentions:
            return
        # Evitar doble respuesta si usaron comando con prefijo (el propio handler ya contestó / falló).
        raw = (message.content or "").lstrip()
        if raw.startswith("?"):
            return

        pregunta = self._strip_mentions_for_question(message.content)
        if len(pregunta) < 2:
            try:
                await message.reply(
                    "Escribí la **pregunta** en el mismo mensaje donde me arrobás "
                    f"(ej. {me.mention} ¿va a llover mañana?). También podés usar `?pregunta …` o `/aat-consulta`.",
                    mention_author=False,
                )
            except discord.HTTPException:
                pass
            return

        wait = self._oracle_cooldown_retry_after(message.author.id)
        if wait > 0:
            try:
                await message.reply(
                    f"Esperá **{wait:.1f}s** entre consultas al oráculo.",
                    mention_author=False,
                    delete_after=8,
                )
            except discord.HTTPException:
                pass
            return

        ch = message.channel
        nombre = message.author.display_name if isinstance(message.author, discord.Member) else str(message.author)
        try:
            await self._send_oracle_embed(
                ch,
                author=message.author,
                nombre_visible=nombre,
                pregunta=pregunta,
                reference=message,
            )
            self._oracle_mark_use(message.author.id)
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(OraculoCog(bot))
