# Preguntas sí / no: 40% sí, 40% no, 20% respuesta tipo probabilidad con % (ver constantes del dado).
# Cuentas simples («2+2», «te pregunte 3*4»): resultado exacto en el bot (rápido); si no se puede parsear, IA local.
# La IA local (Ollama) solo entra en preguntas “abiertas”; el resto siempre va al dado (más divertido).
# Cuenta para la diaria + puntos extra (config .env).
from __future__ import annotations

import ast
import logging
import math
import os
import random
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Literal, Optional, Tuple

_OracleResponseKind = Literal["yesno", "open", "llm", "math"]

import discord
from discord import app_commands
from discord.ext import commands

from cogs.oracle_llm import oracle_local_reply, oracle_local_reply_followup

log = logging.getLogger(__name__)


def _oracle_env_show_errors() -> bool:
    """Si es true, en Discord se muestra tipo + mensaje del error (solo en entornos de confianza)."""
    return (os.getenv("ORACLE_SHOW_ERRORS") or "").strip().lower() in ("1", "true", "yes", "on")


def _oracle_user_visible_internal_error(exc: BaseException) -> str:
    """Texto para reply/embed cuando el oráculo falla por código o datos."""
    if _oracle_env_show_errors():
        name = type(exc).__name__
        detail = str(exc).replace("\n", " ").strip()
        if len(detail) > 400:
            detail = detail[:397] + "…"
        esc = discord.utils.escape_markdown(detail)
        return f"**Oráculo — error interno** (`{name}`): {esc}"
    return (
        "**Oráculo:** falló algo interno. Mirá la **consola / archivo de log** del bot "
        "(línea con `Oráculo _send_oracle_embed` o `Oráculo hilo`). "
        "Para ver el detalle **en Discord**, poné **`ORACLE_SHOW_ERRORS=1`** en el `.env` y reiniciá."
    )


def _message_pings_bot(message: discord.Message, me: discord.abc.User) -> bool:
    """Algunos clientes no rellenan `mentions` igual; `raw_mentions` sale del texto `<@…>`."""
    if me in message.mentions:
        return True
    try:
        return me.id in (message.raw_mentions or ())
    except Exception:
        return False


# Preguntas que no son un sí/no claro: mejor “charla” que un porcentaje místico.
# Solo números y operadores (p. ej. "2+2?", "12 * 3") — no va al dado sí/no.
_ARITH_EXPRESSION_ONLY_RE = re.compile(r"^[\d\s\+\-\*\/x×÷.,\(\)=%^]+$", re.IGNORECASE)
# Cuenta “visible” dentro de una frase corta (p. ej. "te pregunte 2+2", "@bot 12*3 jaja").
_ARITH_SNIPPET_RE = re.compile(r"\b(?:\d{1,8}\s*[\+\-\*\/x×÷]\s*)+\d{1,8}\b", re.IGNORECASE)

# Palabras / risas que suelen rodear la cuenta sin convertirla en consulta seria al oráculo.
_ARITH_CONTEXT_FILLER = frozenset(
    {
        "te",
        "me",
        "le",
        "nos",
        "os",
        "se",
        "lo",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "el",
        "ella",
        "ellos",
        "ellas",
        "por",
        "favor",
        "pf",
        "plis",
        "please",
        "pregunte",
        "pregunté",
        "pregunta",
        "preguntas",
        "consulta",
        "decime",
        "decí",
        "dime",
        "che",
        "boludo",
        "boluda",
        "tipo",
        "literal",
        "re",
        "eh",
        "hey",
        "hol",
        "hola",
        "buenas",
        "buenos",
        "jaja",
        "jajaja",
        "jajajaa",
        "jajajjaa",
        "ja",
        "jj",
        "jiji",
        "dale",
        "daale",
        "bueno",
        "buen",
        "eso",
        "está",
        "esta",
        "es",
        "son",
        "da",
        "sos",
        "eres",
        "cuanto",
        "cuánto",
        "cuantos",
        "cuántos",
        "qué",
        "que",
        "ay",
        "aay",
        "uff",
        "yo",
        "mi",
        "mis",
        "tu",
        "tus",
        "su",
        "sus",
        "acá",
        "aca",
        "ahi",
        "ahí",
        "mira",
        "mirá",
        "ven",
        "vení",
        "ponele",
        "posta",
        "copado",
        "copada",
        "respondeme",
        "respondé",
        "contesta",
        "contestá",
        "decia",
        "decía",
    }
)


def _is_pure_arithmetic_expression(q: str) -> bool:
    s = (q or "").strip()
    s = re.sub(r"^[¿?]+", "", s)
    s = re.sub(r"[?.!…]+$", "", s)
    s = "".join(s.split())
    if len(s) < 3 or len(s) > 36:
        return False
    if not _ARITH_EXPRESSION_ONLY_RE.match(s):
        return False
    if not re.search(r"\d", s):
        return False
    if not re.search(r"[\+\-\*\/x×÷=]", s):
        return False
    return True


def _is_simple_arithmetic_question(q: str) -> bool:
    """Pregunta que es básicamente una cuenta: el oráculo no debe tirar sí/no al azar."""
    if _is_pure_arithmetic_expression(q):
        return True
    s0 = " ".join((q or "").strip().split())
    if len(s0) < 3 or len(s0) > 88:
        return False
    m = _ARITH_SNIPPET_RE.search(s0)
    if not m:
        return False
    core = re.sub(r"\s+", "", m.group(0))
    if len(core) > 22:
        return False
    before, after = s0[: m.start()], s0[m.end() :]
    rest = f"{before} {after}".strip().lower()
    rest = re.sub(r"[^\w\sáéíóúüñ]", " ", rest, flags=re.IGNORECASE)
    words = [w for w in rest.split() if w]
    meaningful = [w for w in words if w not in _ARITH_CONTEXT_FILLER]
    return len(meaningful) == 0


def _normalize_arith_eval_expr(raw: str) -> str:
    t = "".join((raw or "").split())
    t = t.replace("×", "*").replace("÷", "/")
    t = re.sub(r"(?<=\d)[xX](?=\d)", "*", t)
    t = t.replace("^", "**")
    if "=" in t:
        t = t.split("=", 1)[0].strip()
    return t


def _extract_arithmetic_expression_for_eval(q: str) -> str:
    if not _is_simple_arithmetic_question(q):
        return ""
    if _is_pure_arithmetic_expression(q):
        s = (q or "").strip()
        s = re.sub(r"^[¿?]+", "", s)
        s = re.sub(r"[?.!…]+$", "", s)
        core = "".join(s.split())
    else:
        s0 = " ".join((q or "").strip().split())
        m = _ARITH_SNIPPET_RE.search(s0)
        if not m:
            return ""
        core = re.sub(r"\s+", "", m.group(0))
    return _normalize_arith_eval_expr(core)


def _format_math_result_value(val: float) -> str:
    if not math.isfinite(val):
        return "∞"
    if abs(val - round(val)) < 1e-9 and abs(round(val)) < 10**15:
        return str(int(round(val)))
    s = f"{val:.12g}"
    if "e" in s.lower():
        return s
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _format_math_answer_body(expr_norm: str, val: float) -> str:
    disp = expr_norm.replace("**", "^") or "?"
    res = _format_math_result_value(val)
    return f"`{disp}` → **{res}**"


def _arith_eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _arith_eval_node(node.body)
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool) or v is None:
            raise ValueError("bool")
        if isinstance(v, (int, float)):
            x = float(v)
            if not math.isfinite(x):
                raise ValueError("inf")
            return x
        raise ValueError("const")
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_arith_eval_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return _arith_eval_node(node.operand)
        raise ValueError("unary")
    if isinstance(node, ast.BinOp):
        left = _arith_eval_node(node.left)
        right = _arith_eval_node(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            if right == 0:
                raise ZeroDivisionError
            return left / right
        if isinstance(op, ast.FloorDiv):
            if right == 0:
                raise ZeroDivisionError
            return float(left // right)
        if isinstance(op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError
            return left % right
        if isinstance(op, ast.Pow):
            if abs(right) > 48 or abs(left) > 1e9:
                raise ValueError("pow")
            try:
                out = left**right
            except (OSError, OverflowError, ValueError):
                raise ValueError("powr") from None
            if not math.isfinite(out):
                raise ValueError("pown")
            return float(out)
        raise ValueError("binop")
    raise ValueError("node")


def _safe_eval_arithmetic(expr: str) -> Optional[float]:
    if not expr or len(expr) > 44:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    try:
        v = _arith_eval_node(tree)
        if not math.isfinite(v):
            return None
        return float(v)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


_OPEN_QUESTION_RE = re.compile(
    r"(?isx)"
    r"(\b(cuánt|cuant)\w*|"
    r"\bcuál\b|\bcuales\b|"
    r"\b(cómo|como)\s+(está|esta|va|será|sera|fue|iban|ibas|anduv|andaba)\b|"
    r"\bcuándo\b|\bcuando\b\s+(sale|va|llega|empieza|termina)|"
    r"\bdónde\b|\bdonde\b\s+(está|esta|ver|mirar|consigo)|"
    r"por\s*qué|"
    r"\b(temporadas?|caps?\.?|capítulos?|episodios?|ep\.?)\b|"
    r"\bqué\s+opinas\b|\bque\s+opinas\b|\b(opinás|opinas|recomendás|recomendas)\b|"
    # Pedidos de explicación / definición (no van al dado sí/no).
    r"\b(explicá|explica|explícame|explicame|explain)\b|"
    r"\b(describí|describe|descríbeme|describime)\b|"
    r"\b(definí|define|definición|definicion)\b|"
    r"\b(qué\s+es|que\s+es|qué\s+son|que\s+son)\b|"
    r"\b(cuéntame|cuentame|contame)\s+(sobre|de)\b|"
    r"\b(hablame|háblame|hablá)\s+de\b|"
    r"\brecomendame\b|\brecomiendame\b|\brecomendá\b|"
    r"\btodo\s+al\b|\bal\s+(rojo|negro|verde)\b|"
    r"\b(quizás|quiza|quizá)\s+el\s+(rojo|negro|verde)\b)",
    r")",
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


# Rango 1–100 del dado: [1..yes] sí, (yes..yes+no] no, el resto probabilidad con %.
_ORACLE_DICE_PROBABILITY_PCT = 20
_ORACLE_DICE_YES_PCT = (100 - _ORACLE_DICE_PROBABILITY_PCT) // 2
_ORACLE_DICE_NO_PCT = 100 - _ORACLE_DICE_PROBABILITY_PCT - _ORACLE_DICE_YES_PCT


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


def _roll_oracle() -> Tuple[str, str, int]:
    """
    Devuelve (categoría, texto_respuesta, dado 1-100 usado).
    Por defecto: 40% sí, 40% no, 20% respuesta con % (constantes _ORACLE_DICE_*).
    """
    dado = random.randint(1, 100)
    y_max = _ORACLE_DICE_YES_PCT
    n_max = y_max + _ORACLE_DICE_NO_PCT
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
    if dado <= y_max:
        return "Sí", si_msg, dado
    if dado <= n_max:
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


def _parse_consulta_embed_description(desc: str) -> Optional[Tuple[str, str, _OracleResponseKind]]:
    """Recupera (pregunta, última respuesta, tipo) del embed principal de consulta."""
    if not desc or "preguntó:" not in desc:
        return None
    m_q = re.search(r"preguntó:\s*\n>\s*(.+?)(?=\n\n\*\*|\Z)", desc, re.DOTALL | re.IGNORECASE)
    if not m_q:
        return None
    q = (m_q.group(1) or "").strip()
    if not q:
        return None
    if "**La respuesta es:**" in desc:
        m = re.search(r"\*\*La respuesta es:\*\*\s*(.+?)(?:\n\n|\Z)", desc, re.DOTALL)
        if m:
            return (q, m.group(1).strip(), "yesno")
    if "**Cuenta:**" in desc:
        m = re.search(r"\*\*Cuenta:\*\*\s*(.+?)(?:\n\n|\Z)", desc, re.DOTALL)
        if m:
            return (q, m.group(1).strip(), "math")
    if "**Oráculo (IA local, respuesta corta):**" in desc:
        m = re.search(r"\*\*Oráculo \(IA local, respuesta corta\):\*\*\s*(.+?)(?:\n\n|\Z)", desc, re.DOTALL)
        if m:
            return (q, m.group(1).strip(), "llm")
    if "**Modo charla" in desc:
        m = re.search(
            r"\*\*Modo charla \(sin IA local, plantillas \+ humor\):\*\*\s*\n(.+?)(?:\n\n|\Z)",
            desc,
            re.DOTALL,
        )
        if m:
            return (q, m.group(1).strip(), "open")
    return None


def _parse_seguimiento_embed_description(desc: str) -> Optional[Tuple[str, str]]:
    """Recupera (consulta inicial, última respuesta del oráculo) del embed de seguimiento."""
    if not desc:
        return None
    m_or = re.search(r"\*\*Oráculo:\*\*\s*(.+?)(?=\n\n_Consulta inicial:|\Z)", desc, re.DOTALL)
    m_ini = re.search(r"_Consulta inicial:_\s*(.+?)\Z", desc, re.DOTALL | re.IGNORECASE)
    if not m_or or not m_ini:
        return None
    return m_ini.group(1).strip(), m_or.group(1).strip()


def _oracle_context_from_reply_message(msg: discord.Message) -> Optional[Tuple[str, str, _OracleResponseKind]]:
    """Contexto para seguir charlando citando un mensaje del bot con embed de oráculo (sin RAM)."""
    if not msg.embeds:
        return None
    emb = msg.embeds[0]
    desc = emb.description or ""
    title = (emb.title or "").lower()
    if "seguimiento" in title:
        pair = _parse_seguimiento_embed_description(desc)
        if not pair:
            return None
        oq, la = pair
        if not oq or not la:
            return None
        return (oq, la, "open")
    if _ORACLE_EMBED_TITLE in (emb.title or "") or "consulta al oráculo" in title:
        return _parse_consulta_embed_description(desc)
    return None


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
        "explicá ", "explica ", "explícame ", "explicame ", "describe ", "definí ", "define ",
        "hablame ", "háblame ", "hablá ", "contame ", "cuéntame ", "cuentame ",
        "recomendame ", "recomiendame ", "recomendá ", "todo al ",
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
    response_kind: _OracleResponseKind
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
        response_kind: _OracleResponseKind,
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

    async def _oracle_reply_failure(
        self,
        reference: Optional[discord.Message],
        *,
        text: str,
        delete_after: float = 35.0,
    ) -> None:
        """Aviso corto al usuario cuando el embed principal no se pudo mandar."""
        if not reference or not (text or "").strip():
            return
        try:
            await reference.reply(
                (text or "")[:1950],
                mention_author=False,
                delete_after=delete_after,
            )
        except discord.HTTPException as re:
            log.warning("Oráculo: no se pudo enviar el aviso de fallo (reply): %s", re)

    async def cog_load(self) -> None:
        if _oracle_env_show_errors():
            log.warning(
                "ORACLE_SHOW_ERRORS está activo: los fallos del oráculo mostrarán detalle en el canal "
                "(usar solo en servidores de confianza)."
            )

    async def _build_oracle_embed(
        self,
        *,
        nombre_visible: str,
        mencion: str,
        pregunta: str,
        author_id: int,
    ) -> Tuple[discord.Embed, str, _OracleResponseKind]:
        assert self.db is not None
        self.db.ensure_user_exists(author_id)
        pq = pregunta.strip()
        # Cuenta resuelta en el bot primero (rápido): evita que una regex “abierta” fuerce IA antes que `2+2`.
        if _is_simple_arithmetic_question(pq):
            expr = _extract_arithmetic_expression_for_eval(pq)
            val = _safe_eval_arithmetic(expr) if expr else None
            if val is not None:
                body, response_kind = _format_math_answer_body(expr, val), "math"
            else:
                llm = await oracle_local_reply(pq)
                if llm:
                    body, response_kind = llm, "llm"
                elif _is_open_ended_question(pq):
                    kind, body, _ = _roll_oracle_for_question(pq)
                    response_kind = "open" if kind == "open" else "yesno"
                else:
                    body = (
                        "No pude resolver esa cuenta tal cual está; "
                        "probá con `+ - * / % ^ ( )` y números simples."
                    )
                    response_kind = "open"
        elif _is_open_ended_question(pq):
            llm = await oracle_local_reply(pq)
            if llm:
                body, response_kind = llm, "llm"
            else:
                expr = _extract_arithmetic_expression_for_eval(pq)
                if expr:
                    val = _safe_eval_arithmetic(expr)
                    if val is not None:
                        body, response_kind = _format_math_answer_body(expr, val), "math"
                    else:
                        kind, body, _ = _roll_oracle_for_question(pq)
                        response_kind = "open" if kind == "open" else "yesno"
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
        gid = getattr(getattr(channel, "guild", None), "id", None)
        cid = getattr(channel, "id", None)
        typing_fn = getattr(channel, "typing", None)

        async def _build() -> Tuple[discord.Embed, str, _OracleResponseKind]:
            return await self._build_oracle_embed(
                nombre_visible=nombre_visible,
                mencion=author.mention,
                pregunta=pregunta.strip(),
                author_id=author.id,
            )

        try:
            if callable(typing_fn):
                async with typing_fn():
                    embed, body, response_kind = await _build()
            else:
                embed, body, response_kind = await _build()
            sent = await channel.send(embed=embed, reference=reference, mention_author=False)
        except discord.Forbidden as e:
            log.warning(
                "Oráculo _send_oracle_embed: Forbidden guild=%s channel=%s author=%s err=%s",
                gid,
                cid,
                author.id,
                e,
            )
            await self._oracle_reply_failure(
                reference,
                text=(
                    "**Oráculo:** no tengo permiso para enviar (o embedear) en este canal. "
                    "Revisá permisos del rol del bot."
                ),
            )
            return None
        except discord.HTTPException as e:
            log.warning(
                "Oráculo _send_oracle_embed: HTTP %s guild=%s channel=%s author=%s status=%s",
                type(e).__name__,
                gid,
                cid,
                author.id,
                getattr(e, "status", None),
            )
            await self._oracle_reply_failure(
                reference,
                text=(
                    "**Oráculo:** Discord rechazó el envío del embed. "
                    "Reintentá en unos segundos o usá `?pregunta …`."
                ),
            )
            return None
        except Exception as e:
            log.exception(
                "Oráculo _send_oracle_embed: error interno guild=%s channel=%s author=%s pregunta=%r",
                gid,
                cid,
                author.id,
                (pregunta or "")[:200],
            )
            await self._oracle_reply_failure(reference, text=_oracle_user_visible_internal_error(e))
            return None

        if isinstance(sent, discord.Message) and sent.guild:
            self._register_oracle_pending(
                sent,
                author,
                original_question=pregunta.strip(),
                last_answer=body,
                response_kind=response_kind,
            )
        return sent

    async def _resolve_oracle_followup_body(
        self, pending: OraclePending, user_line: str
    ) -> Tuple[str, _OracleResponseKind]:
        """Cuenta local → IA con contexto → IA solo último mensaje → dado / plantilla."""
        if _is_simple_arithmetic_question(user_line):
            expr = _extract_arithmetic_expression_for_eval(user_line)
            val = _safe_eval_arithmetic(expr) if expr else None
            if val is not None:
                return _format_math_answer_body(expr, val), "math"
        llm = await oracle_local_reply_followup(
            pending.original_question,
            pending.last_answer,
            user_line,
        )
        if llm:
            return llm, "llm"
        llm2 = await oracle_local_reply(user_line)
        if llm2:
            return llm2, "llm"
        if _is_simple_arithmetic_question(user_line):
            return (
                "No pude resolver esa cuenta; probá solo la expresión (ej. `3*4`) o `?pregunta …`.",
                "open",
            )
        kind, ans, _ = _roll_oracle_for_question(user_line)
        return ans, ("open" if kind == "open" else "yesno")

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
        persist_pending: bool = True,
    ) -> None:
        """Respuesta a quien citó el último embed del oráculo (sin sumar otra diaria)."""
        gid = getattr(getattr(channel, "guild", None), "id", None)
        cid = getattr(channel, "id", None)
        try:
            body, rk = await self._resolve_oracle_followup_body(pending, user_line)
            body_show = discord.utils.escape_markdown(body) if rk == "llm" else body
            desc = (
                f"{author.mention} **({nombre_visible})** sigue el hilo:\n"
                f"> {discord.utils.escape_markdown(user_line)[:500]}\n\n"
                f"**Oráculo:** {body_show}"
            )
            if len(desc) > 4090:
                desc = desc[:4087] + "…"
            emb = discord.Embed(
                title="🔮 Oráculo · seguimiento",
                description=desc,
                color=discord.Color.dark_magenta(),
            )
            sent = await channel.send(embed=emb, reference=reference, mention_author=False)
        except discord.Forbidden as e:
            log.warning(
                "Oráculo followup: Forbidden guild=%s channel=%s author=%s err=%s",
                gid,
                cid,
                author.id,
                e,
            )
            await self._oracle_reply_failure(
                reference,
                text="**Oráculo (seguimiento):** sin permiso para enviar el embed acá.",
            )
            return
        except discord.HTTPException as e:
            log.warning(
                "Oráculo followup: HTTP %s guild=%s channel=%s author=%s status=%s",
                type(e).__name__,
                gid,
                cid,
                author.id,
                getattr(e, "status", None),
            )
            await self._oracle_reply_failure(
                reference,
                text="**Oráculo (seguimiento):** Discord rechazó el envío. Probá de nuevo.",
            )
            return
        except Exception as e:
            log.exception(
                "Oráculo followup: error interno guild=%s channel=%s author=%s user_line=%r",
                gid,
                cid,
                author.id,
                (user_line or "")[:200],
            )
            await self._oracle_reply_failure(reference, text=_oracle_user_visible_internal_error(e))
            return

        if persist_pending and isinstance(sent, discord.Message) and sent.guild:
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
        response_kind: _OracleResponseKind = "yesno",
    ) -> discord.Embed:
        q = (pregunta or "").strip()[:900] or "*(silencio místico)*"
        body_show = discord.utils.escape_markdown(body) if response_kind == "llm" else body
        if response_kind == "llm":
            bloque = (
                f"{mencion} **({nombre_visible})** preguntó:\n"
                f"> {q}\n\n"
                f"**Oráculo (IA local, respuesta corta):** {body_show}"
            )
        elif response_kind == "math":
            bloque = (
                f"{mencion} **({nombre_visible})** preguntó:\n"
                f"> {q}\n\n"
                f"**Cuenta:** {body_show}"
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
        desc = bloque
        if len(desc) > 4090:
            desc = desc[:4087] + "…"
        emb = discord.Embed(
            title=_ORACLE_EMBED_TITLE,
            description=desc,
            color=discord.Color.dark_magenta(),
        )
        if response_kind == "llm":
            mod = (os.getenv("ORACLE_MODEL") or "local").strip()
            emb.set_footer(text=f"IA local (Ollama) · {mod}")
        elif response_kind == "math":
            emb.set_footer(text="Cuenta resuelta en el bot · instantáneo")
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
        sent = await self._send_oracle_embed(
            ctx.channel,
            author=ctx.author,
            nombre_visible=nombre,
            pregunta=texto.strip(),
            reference=None,
        )
        if sent:
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
        try:
            embed, body, response_kind = await self._build_oracle_embed(
                nombre_visible=nombre,
                mencion=mencion,
                pregunta=pregunta.strip(),
                author_id=interaction.user.id,
            )
            await interaction.response.send_message(embed=embed)
        except discord.HTTPException as e:
            log.warning(
                "Oráculo slash aat-consulta: HTTP %s user=%s status=%s",
                type(e).__name__,
                interaction.user.id,
                getattr(e, "status", None),
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Discord rechazó el envío de la consulta. Reintentá.",
                    ephemeral=True,
                )
            else:
                try:
                    await interaction.followup.send(
                        "Discord rechazó el envío de la consulta. Reintentá.",
                        ephemeral=True,
                    )
                except discord.HTTPException:
                    pass
            return
        except Exception as e:
            log.exception(
                "Oráculo slash aat-consulta: error interno user=%s pregunta=%r",
                interaction.user.id,
                (pregunta or "")[:200],
            )
            msg_err = _oracle_user_visible_internal_error(e)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg_err[:2000], ephemeral=True)
                else:
                    await interaction.followup.send(msg_err[:2000], ephemeral=True)
            except discord.HTTPException:
                pass
            return

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

            # C) Embed del oráculo pero sin estado en memoria: igual contestamos leyendo el embed (sin guardar hilo).
            if oracle_embed and not pending:
                if len(user_text) < 1:
                    await message.reply(
                        "Escribí algo para seguir la charla (aunque sea corto).",
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
                if not self.db:
                    await message.reply("Economía no disponible.", mention_author=False)
                    return True
                nombre = (
                    message.author.display_name
                    if isinstance(message.author, discord.Member)
                    else str(message.author)
                )
                parsed = _oracle_context_from_reply_message(ref_msg)
                if parsed:
                    orig_q, last_a, rk_guess = parsed
                    synthetic = OraclePending(
                        bot_message_id=ref_msg.id,
                        original_question=orig_q[:900],
                        last_answer=last_a[:900],
                        response_kind=rk_guess,
                        deadline_monotonic=time.monotonic(),
                    )
                    await self._send_oracle_followup(
                        message.channel,
                        author=message.author,
                        nombre_visible=nombre,
                        user_line=user_text,
                        pending=synthetic,
                        reference=message,
                        pending_key=key,
                        persist_pending=False,
                    )
                else:
                    llm = await oracle_local_reply(user_text)
                    if llm:
                        esc = discord.utils.escape_markdown(user_text)[:500]
                        esc_r = discord.utils.escape_markdown(llm)
                        d_fb = (
                            f"{message.author.mention} **({nombre})** sigue el hilo:\n"
                            f"> {esc}\n\n**Oráculo:** {esc_r}"
                        )[:4096]
                        emb_fb = discord.Embed(
                            title="🔮 Oráculo · seguimiento",
                            description=d_fb,
                            color=discord.Color.dark_magenta(),
                        )
                        await message.reply(embed=emb_fb, mention_author=False)
                    else:
                        kind, ans, _ = _roll_oracle_for_question(user_text)
                        body_fb = ans
                        d_fb2 = (
                            f"{message.author.mention} **({nombre})** sigue el hilo:\n"
                            f"> {discord.utils.escape_markdown(user_text)[:500]}\n\n"
                            f"**Oráculo:** {body_fb}"
                        )[:4096]
                        emb_fb2 = discord.Embed(
                            title="🔮 Oráculo · seguimiento",
                            description=d_fb2,
                            color=discord.Color.dark_magenta(),
                        )
                        await message.reply(embed=emb_fb2, mention_author=False)
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
                sent = await self._send_oracle_embed(
                    message.channel,
                    author=message.author,
                    nombre_visible=nombre,
                    pregunta=user_text,
                    reference=message,
                )
                if sent:
                    self._oracle_mark_use(message.author.id)
                return True

            await message.reply(random.choice(_ORACLE_QUIP_NOT_ORACLE), mention_author=False)
            return True
        except discord.HTTPException as e:
            log.warning("Oráculo hilo/reply: Discord HTTP (%s): %s", type(e).__name__, e)
            try:
                await message.reply(
                    "No pude enviar la respuesta del oráculo (Discord rechazó el envío). Probá de nuevo en unos segundos.",
                    mention_author=False,
                    delete_after=14,
                )
            except discord.HTTPException:
                pass
            return True
        except Exception as e:
            log.exception(
                "Oráculo hilo/reply: error interno guild=%s channel=%s author=%s",
                message.guild.id if message.guild else None,
                message.channel.id,
                message.author.id,
            )
            try:
                await message.reply(
                    _oracle_user_visible_internal_error(e),
                    mention_author=False,
                    delete_after=35,
                )
            except discord.HTTPException:
                pass
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

        if not _message_pings_bot(message, me):
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
        sent = await self._send_oracle_embed(
            ch,
            author=message.author,
            nombre_visible=nombre,
            pregunta=pregunta,
            reference=message,
        )
        if sent:
            self._oracle_mark_use(message.author.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(OraculoCog(bot))
