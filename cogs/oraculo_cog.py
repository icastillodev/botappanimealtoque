# Preguntas sí / no: 40% sí, 40% no, 20% con % (dado), salvo ORACLE_LLM_YESNO=1 + IA activa → modelo en una frase.
# Cuentas simples: en el bot. Preguntas abiertas: Ollama si IA activa; si no, plantillas + humor.
# Sin Ollama: anime/manga → oracle_media (AniList + definiciones wiki); hechos → ORACLE_WIKI_FALLBACK (Wikipedia es).
# IA: ORACLE_USE_LLM=1 o ORACLE_LLM_AUTO=1, y ORACLE_LLM_URL (ver .env.example). ORACLE_USE_LLM=0 fuerza apagado.
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
from typing import Any, Deque, Dict, Literal, Optional, Tuple

_OracleResponseKind = Literal["yesno", "open", "llm", "math"]

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)

try:
    from cogs.oracle_llm import oracle_local_reply, oracle_local_reply_followup
except Exception:
    log.warning(
        "No se pudo importar cogs.oracle_llm (dependencia rota, sintaxis, etc.). "
        "El oráculo carga igual; IA local queda desactivada.",
        exc_info=True,
    )

    async def oracle_local_reply(*_a: Any, **_k: Any) -> None:  # type: ignore[misc]
        return None

    async def oracle_local_reply_followup(*_a: Any, **_k: Any) -> None:  # type: ignore[misc]
        return None

try:
    from cogs.oracle_media import (
        oracle_media_another_recommendation_async,
        oracle_media_open_reply_async,
    )
except Exception:
    log.warning(
        "No se pudo importar cogs.oracle_media (recomendaciones por género / AniList). "
        "El oráculo sigue; esas respuestas ricas quedan desactivadas.",
        exc_info=True,
    )

    async def oracle_media_open_reply_async(*_a: Any, **_k: Any) -> None:  # type: ignore[misc]
        return None

    async def oracle_media_another_recommendation_async(*_a: Any, **_k: Any) -> None:  # type: ignore[misc]
        return None


def _oracle_use_llm() -> bool:
    """
    Ollama si hay URL y (ORACLE_USE_LLM=1 **o** ORACLE_LLM_AUTO=1).
    ORACLE_USE_LLM=0|false|off desactiva aunque exista ORACLE_LLM_AUTO.
    """
    off = (os.getenv("ORACLE_USE_LLM") or "").strip().lower()
    if off in ("0", "false", "no", "off"):
        return False
    on = off in ("1", "true", "yes", "on")
    auto = (os.getenv("ORACLE_LLM_AUTO") or "").strip().lower() in ("1", "true", "yes", "on")
    if not (on or auto):
        return False
    return bool((os.getenv("ORACLE_LLM_URL") or "").strip())


def _oracle_llm_yesno_via_model() -> bool:
    """Si True y la IA está activa, las consultas que iban al dado pasan primero por el modelo (una frase)."""
    return (os.getenv("ORACLE_LLM_YESNO") or "").strip().lower() in ("1", "true", "yes", "on")


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
    """Algunos clientes no rellenan `mentions` igual; `raw_mentions` y el texto `<@…>` son respaldo."""
    if me in message.mentions:
        return True
    try:
        if me.id in (message.raw_mentions or ()):
            return True
    except Exception:
        pass
    c = message.content or ""
    if f"<@{me.id}>" in c or f"<@!{me.id}>" in c:
        return True
    return False


# Preguntas que no son un sí/no claro: mejor “charla” que un porcentaje místico.
# Tras reemplazar √n y sqrt(n) por un dígito, solo deben quedar dígitos y operadores básicos.
_ARITH_FLATTENED_OK_RE = re.compile(r"^[\d\s\+\-\*\/x×÷.,\(\)=%^]+$", re.IGNORECASE)
# Cuenta “visible” dentro de una frase corta (p. ej. "te pregunte 2+2", "@bot √144 jaja").
_ARITH_SNIPPET_RE = re.compile(
    r"(?i)(?:\b(?:\d{1,8}\s*[\+\-\*\/x×÷]\s*)+\d{1,8}\b"
    r"|\b√\s*\d{1,8}\b"
    r"|\bsqrt\s*\(\s*\d{1,8}\s*\))",
)
# Raíz cuadrada en lenguaje natural o sqrt(n).
_ARITH_SQRT_IN_QUESTION_RE = re.compile(
    r"(?is)(?:ra[ií]z\s+cuadrada|raiz\s+cuadrada)\s+(?:de\s+|del\s+)?(\d{1,8})"
    r"|sqrt\s*\(\s*(\d{1,8})\s*\)",
)

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


def _arith_sqrt_match(q: str) -> Optional[re.Match[str]]:
    s0 = " ".join((q or "").strip().split())
    if len(s0) < 8 or len(s0) > 92:
        return None
    return _ARITH_SQRT_IN_QUESTION_RE.search(s0)


def _arith_sqrt_operand_from_match(m: re.Match[str]) -> Optional[int]:
    g = (m.group(1) or m.group(2) or "").strip()
    if not g.isdigit():
        return None
    n = int(g)
    return n if 0 < n < 10**9 else None


def _arith_prepare_implicit_mul(s: str) -> str:
    """2√9 → 2*√9 ; )√4 → )*√4"""
    t = re.sub(r"(\d)\s*(?=√)", r"\1*", s)
    t = re.sub(r"\)\s*(?=√)", ")*", t)
    return t


def _arith_pure_flatten_radicals(s: str) -> str:
    """Sustituye sqrt(n) y √n por dígito para validar el resto de la expresión."""
    t = re.sub(r"(?i)sqrt\s*\(\s*\d{1,8}\s*\)", "0", s)
    t = re.sub(r"√\s*\(\s*\d{1,8}\s*\)", "0", t)
    t = re.sub(r"√\s*\d{1,8}", "0", t)
    return t


def _is_pure_arithmetic_expression(q: str) -> bool:
    s = (q or "").strip()
    s = re.sub(r"^[¿?]+", "", s)
    s = re.sub(r"[?.!…]+$", "", s)
    s = "".join(s.split())
    s = _arith_prepare_implicit_mul(s)
    if len(s) < 2 or len(s) > 48:
        return False
    flat = _arith_pure_flatten_radicals(s)
    if not _ARITH_FLATTENED_OK_RE.match(flat):
        return False
    if not re.search(r"\d", flat):
        return False
    has_radical = "√" in s or re.search(r"sqrt", s, re.I)
    has_binop = bool(re.search(r"[\+\-\*\/x×÷=%^]", s))
    if has_radical and not has_binop:
        return True
    if has_binop:
        return True
    return False


def _is_simple_arithmetic_question(q: str) -> bool:
    """Pregunta que es básicamente una cuenta: el oráculo no debe tirar sí/no al azar."""
    if _is_pure_arithmetic_expression(q):
        return True
    msqrt = _arith_sqrt_match(q)
    if msqrt and _arith_sqrt_operand_from_match(msqrt) is not None:
        s0 = " ".join((q or "").strip().split())
        before, after = s0[: msqrt.start()], s0[msqrt.end() :]
        rest = f"{before} {after}"
        rest = re.sub(r"[^\w\sáéíóúüñ]", " ", rest, flags=re.IGNORECASE)
        words = [w for w in rest.split() if w]
        extra_ok = frozenset({"cuál", "cual", "cuanto", "cuánto", "vale", "da", "es", "son", "igual"})
        meaningful = [w for w in words if w not in _ARITH_CONTEXT_FILLER and w not in extra_ok]
        return len(meaningful) == 0
    s0 = " ".join((q or "").strip().split())
    if len(s0) < 3 or len(s0) > 88:
        return False
    m = _ARITH_SNIPPET_RE.search(s0)
    if not m:
        return False
    core = re.sub(r"\s+", "", m.group(0))
    if len(core) > 40:
        return False
    before, after = s0[: m.start()], s0[m.end() :]
    rest = f"{before} {after}".strip().lower()
    rest = re.sub(r"[^\w\sáéíóúüñ]", " ", rest, flags=re.IGNORECASE)
    words = [w for w in rest.split() if w]
    meaningful = [w for w in words if w not in _ARITH_CONTEXT_FILLER]
    return len(meaningful) == 0


def _normalize_arith_eval_expr(raw: str) -> str:
    t = "".join((raw or "").split())
    t = _arith_prepare_implicit_mul(t)
    t = t.replace("×", "*").replace("÷", "/")
    t = re.sub(r"(?<=\d)[xX](?=\d)", "*", t)
    # sqrt(n) y notación √ antes de ^ → **
    t = re.sub(r"(?i)sqrt\s*\(\s*(\d{1,8})\s*\)", r"(\1)**0.5", t)
    t = re.sub(r"√\s*\(\s*(\d{1,8})\s*\)", r"(\1)**0.5", t)
    t = re.sub(r"√\s*(\d{1,8})", r"(\1)**0.5", t)
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
        core = _arith_prepare_implicit_mul("".join(s.split()))
    else:
        msqrt = _arith_sqrt_match(q)
        if msqrt:
            n = _arith_sqrt_operand_from_match(msqrt)
            if n is not None:
                return f"({n})**0.5"
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
    msqrt_disp = re.match(r"^\((\d{1,8})\)\*\*0\.5$", (expr_norm or "").replace(" ", ""))
    if msqrt_disp:
        disp = f"√{msqrt_disp.group(1)}"
    else:
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
    if not expr or len(expr) > 72:
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
    r"\bcuál\b|\bcual\b|\bcuales\b|"
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
    r"\b(cuál\s+es|cual\s+es|cuál\s+son|cual\s+son)\b|"
    r"\bprimer[ao]?\s+ley\b|\bley(es)?\s+de\s+newton\b|"
    r"\b(cuéntame|cuentame|contame)\s+(sobre|de)\b|"
    r"\b(hablame|háblame|hablá)\s+de\b|"
    r"\brecomend(?:ame|á|a|arme|ale|an)\b|\brecomiend(?:ame|ale|an)\b"
    r")",
)


_ANIME_REC_RE = re.compile(
    r"(?is)"
    r"\brecomienda(?:me|nos|le)?(\s+un)?\s+anime\b|"
    r"\brecomiend(?:ame|anos|an|ale)\b.*\banime\b|"
    r"\brecomend(?:ame|á|a|arme|ale|an)\b.*\banime\b|"
    r"\bsuger(?:ime|í|i)\b.*\banime\b|"
    r"\bqu[eé]\s+anime\s+(ver|mirar|empezar|poner)\b|"
    r"\banime\s+(para\s+)?ver\b|"
    r"\bpon(?:eme|me|é)\s+un\s+anime\b|"
    r"\bpas(?:a|á)(?:me|nos)?\s+un\s+anime\b|"
    r"\btir(?:a|á)(?:me|nos)?\s+un\s+anime\b|"
    r"\bdame\s+un\s+anime\b",
)

_ORACLE_MEDIA_REC_GENRE = re.compile(
    r"(?is)\b(anime|manga|manhwa|manhua|isekai|sh[oō]nen|shonen|seinen|josei|"
    r"mecha|rom[aá]nce|slice|fantas|fantasy|fantasía|comedy|comedia|"
    r"acci[oó]n|action|horror|thriller|sci-?fi|deporte|sports|musical|idol|"
    r"iyashikei|reencarn|otro mundo)\b"
)


def _is_anime_recommendation_request(q: str) -> bool:
    s = (q or "").strip()
    if len(s) < 6:
        return False
    if _ANIME_REC_RE.search(s):
        return True
    if re.search(r"\brecomienda\b", s) and re.search(r"\banime\b", s):
        return True
    if re.search(r"\brecomend\w*", s) and re.search(r"\banime\b", s):
        return True
    if re.search(r"\brecomienda(?:me|nos|le)?\b", s) and _ORACLE_MEDIA_REC_GENRE.search(s):
        return True
    if re.search(r"\brecomend\w*", s) and _ORACLE_MEDIA_REC_GENRE.search(s):
        return True
    if re.search(r"\bsuger(?:ime|í|i)\w*\b", s) and _ORACLE_MEDIA_REC_GENRE.search(s):
        return True
    return False


# “Todo al negro / rojo / verde”, “¿rojo o negro?”: ruleta, no pregunta abierta tipo temporadas.
_RULETTE_COLOR_CONTEXT_RE = re.compile(
    r"(?is)"
    r"\btodo\s+al\b|"
    r"\b(al\s+)?(rojo|negro|verde)\s+o\s+(al\s+)?(rojo|negro|verde)\b|"
    r"\b(rojo|negro|verde)\s+o\s+(el\s+)?(rojo|negro|verde)\b|"
    r"\b(quizás|quiza|quizá)\s+el\s+(rojo|negro|verde)\b",
)


def _is_roulette_color_question(q: str) -> bool:
    s = (q or "").strip()
    if len(s) < 6:
        return False
    if not _RULETTE_COLOR_CONTEXT_RE.search(s):
        return False
    low = s.lower()
    if not re.search(r"\b(rojo|negro|verde)\b", low):
        return False
    # Falsos positivos típicos (no es la ruleta del casino).
    if re.search(
        r"(?is)\b(sem[aá]foro|luz\s+roja|rojo\s+vivo|lista\s+negra|"
        r"bandera\s+roja|ojos\s+rojos|humor\s+negro|"
        r"al\s+rojo\s+vivo)\b",
        low,
    ):
        return False
    return True


def _oracle_roulette_pick(q: str) -> str:
    """
    Si nombran un solo color (“todo al rojo”), igual hay dos casillas en la ruleta:
    elige al azar entre Rojo y Negro (no queda fijo en el color que dijeron).
    Si nombran dos o tres colores con ‘o’, solo elige entre esos.
    """
    low = (q or "").lower()
    has_rojo = "rojo" in low
    has_negro = "negro" in low
    has_verde = "verde" in low
    n = sum(1 for x in (has_rojo, has_negro, has_verde) if x)
    pool: list[str] = []
    if n >= 2:
        if has_rojo:
            pool.append("Rojo")
        if has_negro:
            pool.append("Negro")
        if has_verde:
            pool.append("Verde")
        pool = list(dict.fromkeys(pool))
    elif n == 1:
        if has_verde:
            pool = ["Verde", "Rojo", "Negro"]
        else:
            pool = ["Rojo", "Negro"]
            if random.random() < 0.05:
                pool.append("Verde")
    else:
        pool = ["Rojo", "Negro"]
    if not pool:
        pool = ["Rojo", "Negro"]
    pick = random.choice(pool)
    tail = random.choice(
        [
            "Humor de oráculo: no es consejo de apuestas.",
            "Tapete imaginario; en la vida real usá cabeza (y leyes locales).",
            "Tirada simbólica; si perdés plata no reclamás al bot.",
            "Lectura **no científica**; el casino real tiene términos y condiciones.",
            "Siempre podés volver a tirar con otra `?pregunta` — acá no cobramos fichas.",
            "El multiverso asintió; vos decidís si le prestás bola.",
            "Nada de esto reemplaza suerte, criterio o leyes locales.",
            "Cero responsabilidad civil del bot; eso lo firma el destino.",
            "Si sale distinto a lo que querías, fue el viento del tapete.",
        ]
    )
    lead = random.choice(
        [
            f"Que sea **{pick}** — {tail}",
            f"**{pick}** sale del sombrero místico — {tail}",
            f"Tirada express: **{pick}**. {tail}",
            f"La bola imaginaria marca **{pick}**. {tail}",
            f"Me inclino por **{pick}** (sin notario). {tail}",
        ]
    )
    return lead


def _is_poker_push_decision_question(q: str) -> bool:
    """Poker / naipes + ir con todo o plantarse — no un simple ‘¡Sí!’ sin contexto."""
    s = (q or "").strip()
    if len(s) < 12:
        return False
    low = s.lower()
    if _is_roulette_color_question(s):
        return False
    ctx = bool(
        re.search(r"(?is)\b(poker|holdem|hold'?em|texas|omaha|blackjack)\b", low)
        or re.search(r"(?is)\bbaraja\s+de\s+(poker|cartas?)\b", low)
        or (
            re.search(r"\bnaipes?\b", low)
            and re.search(r"\b(poker|fichas|tapete|apuesta|ciegas?|torneo)\b", low)
        )
        or (
            re.search(r"\ball[\s-]*in\b", low)
            and re.search(r"\b(poker|fichas|tapete|mesa|torneo|baraja)\b", low)
        )
    )
    if not ctx:
        return False
    dilemma = bool(
        re.search(
            r"(?is)\b(le\s+)?(doy|meto|tiro)\s+todo\b|\bno\s+voy\b|\bvoy\s+o\s+no\b|"
            r"\bme\s+la\s+juego\b|\ball[\s-]*in\b|\btodo\s+o\s+nada\b|"
            r"\bapuesto\s+todo\b|\barriesgo\s+todo\b",
            low,
        )
    )
    if not dilemma:
        return False
    if re.search(r"(?is)\b(compr(ar|o)|vend(er|o)|regal(ar|o))\b", low) and not re.search(
        r"\b(doy|meto|tiro|voy\s+o)\b",
        low,
    ):
        return False
    return True


def _oracle_poker_push_answer() -> str:
    """Misma distribución que el dado clásico, texto acorde a mesa / all-in."""
    dado = random.randint(1, 100)
    y_max = _ORACLE_DICE_YES_PCT
    n_max = y_max + _ORACLE_DICE_NO_PCT
    if dado <= y_max:
        return random.choice(
            [
                "**Sí — shove místico:** las cartas te saludan; en Discord no se pierden fichas de verdad.",
                "**All-in simbólico** (sí): el pozo te guiña; en la vida real contá outs y bankroll.",
                "**Sí**: si vas con todo, que sea con **baraja cerrada** y cero drama en el river mental.",
            ]
        )
    if dado <= n_max:
        return random.choice(
            [
                "**No — fold** con estilo: guardá narrativa y el stack emocional.",
                "**No vas** así nomás: el flop del destino pidió un paso atrás.",
                "**No** (por ahora): mejor leer tells del café que del multiverso.",
            ]
        )
    pct = random.randint(15, 85)
    if random.choice([True, False]):
        return random.choice(
            [
                f"Ni mano ganada ni **fold** claro: **~{pct}%** de “meter **presión**” y el resto a pensar en frío.",
                f"Ambiguo como **split pot** místico: **~{pct}%** a favor del **push**; no firmo nada.",
            ]
        )
    return random.choice(
        [
            f"Mano rara: inclinación **~{pct}%** al **no meter**; el resto queda en la penumbra del river.",
            f"Dado flojo en Las Vegas del alma: **{pct}%** no, **{100 - pct}%** sí (humor, no odds reales).",
        ]
    )


def _is_open_ended_question(pregunta: str) -> bool:
    q = (pregunta or "").strip()
    if len(q) < 4:
        return False
    if _is_roulette_color_question(q):
        return False
    if _is_multi_option_or_recommendation(q):
        return False
    if _is_anime_recommendation_request(q):
        return True
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

# Historia / física / “deberes”: no inventar sí/no ni chistes de anime; sin Ollama, respuesta sobria.
_SERIOUS_FACT_RE = re.compile(
    r"(?is)"
    r"\b(revoluci[oó]n\s+francesa|revoluci[oó]n\s+rusa|guerra\s+(mundial|civil|de\s+troya)|"
    r"primera\s+guerra|segunda\s+guerra|imperio\s+romano)\b|"
    r"\b(newton|einstein|galileo|maxwell|darwin|ley(es)?\s+de\s+newton|"
    r"primer[ao]?\s+ley|segund[ao]?\s+ley|tercer[ao]?\s+ley)\b|"
    r"\b(historia\s+universal|historia\s+de\s+(francia|españa|argentina))\b|"
    r"\b(cuál|cual)\s+es\s+la\s+(primera|primer|segunda|tercera|1|2|3)\b",
)

# “Pizza, sushi o pasta” / “esta o esa o la otra”: el oráculo elige una (sin ser solo poker).
_CHOICE_ALT_MIN_LEN = 2
_CHOICE_ALT_MAX_LEN = 52
_CHOICE_MAX_ALTS = 8


def _normalize_choice_fragment(t: str) -> str:
    x = " ".join((t or "").split())
    return x.strip("¿?.,;:·\"'«»()[]{}…").strip()


def _extract_or_alternatives(raw: str) -> Optional[list[str]]:
    """Parte por ‘ o ’ y por comas dentro de cada trozo → opciones cortas."""
    s = " ".join((raw or "").split()).strip().strip("¿?")
    if len(s) < 7 or not re.search(r"(?i)\s+o\s+", s):
        return None
    parts = re.split(r"(?i)\s+o\s+", s)
    alts: list[str] = []
    for p in parts:
        subs = [x for x in re.split(r",\s*", p) if x.strip()]
        if not subs:
            continue
        for sub in subs:
            frag = _normalize_choice_fragment(sub)
            if len(frag) < _CHOICE_ALT_MIN_LEN or len(frag) > _CHOICE_ALT_MAX_LEN:
                return None
            alts.append(frag)
    seen: set[str] = set()
    out: list[str] = []
    for a in alts:
        k = a.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(a)
    return out if 2 <= len(out) <= _CHOICE_MAX_ALTS else None


def _alts_are_plain_yesno_only(alts: list[str]) -> bool:
    """Solo sí/no puro → mejor el dado clásico."""
    if len(alts) != 2:
        return False

    def _bucket(x: str) -> Optional[str]:
        z = re.sub(r"[^\wáéíóúÁÉÍÓÚñÑ]+", "", x.lower())
        if z in ("si", "sí"):
            return "si"
        if z == "no":
            return "no"
        return None

    a, b = _bucket(alts[0]), _bucket(alts[1])
    return a is not None and b is not None and a in ("si", "no") and b in ("si", "no")


def _is_multi_option_or_recommendation(q: str) -> bool:
    s = (q or "").strip()
    if len(s) < 9:
        return False
    if _is_roulette_color_question(s):
        return False
    if _is_poker_push_decision_question(s):
        return False
    if _is_anime_recommendation_request(s):
        return False
    if _SERIOUS_FACT_RE.search(s):
        return False
    alts = _extract_or_alternatives(s)
    if not alts:
        return False
    if _alts_are_plain_yesno_only(alts):
        return False
    # Dos trozos muy largos: casi seguro no es “opción A / B”, sino dos oraciones.
    if len(alts) == 2 and len(alts[0]) > 44 and len(alts[1]) > 44:
        return False
    return True


def _oracle_multi_option_pick(q: str) -> str:
    alts = _extract_or_alternatives(q) or []
    if len(alts) < 2:
        return "No leí opciones claras; probá listar tipo **A, B o C**."
    pick_raw = random.choice(alts)
    pick = discord.utils.escape_markdown(pick_raw)[:200]
    return random.choice(
        [
            f"Si tuviera **IA posta** pondría pros/contras; acá va pick random: **{pick}**.",
            f"Entre lo que tiraste, hoy me quedo con **{pick}** (humor, cero garantías).",
            f"**{pick}** — suena a menos arrepentimiento que el resto (o no, el cosmos no firma).",
            f"Recomendación **de vibes**: **{pick}**. Si falla, fue el multiverso.",
        ]
    )


def _oracle_wiki_fallback_enabled() -> bool:
    v = (os.getenv("ORACLE_WIKI_FALLBACK") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _oracle_serious_no_llm_fallback() -> str:
    return random.choice(
        [
            "Eso es **material de estudio / Wikipedia**, no de adivinanza con dado. "
            "Si querés texto posta en el servidor, que dejen **Ollama** activo (`ORACLE_USE_LLM=1` o `ORACLE_LLM_AUTO=1` + `ORACLE_LLM_URL`). "
            "Si no, buscá en Google o en tus apuntes: acá sin IA no invento fechas ni leyes.",
            "Para **hechos** (historia, leyes de Newton, etc.) no tengo base seria sin **IA local**. "
            "Con el bot en modo solo plantillas te puedo tirar **humor de anime**, pero sería deshonesto para esto.",
            "Consulta **demasiado enciclopedia** para el oráculo-random. Activá **Ollama** en el `.env` o usá una fuente confiable; no te voy a decir Sí/No ni inventar la Revolución.",
        ]
    )


def _oracle_silly_open_templates(pregunta: str) -> str:
    raw_topic = _extract_topic_for_oracle(pregunta)
    topic = discord.utils.escape_markdown(raw_topic) if raw_topic else "eso"
    n1 = random.randint(2, 4)
    n2 = random.randint(5, 10)
    n3 = random.randint(1, 3)
    chaos = random.randint(40, 95)
    return random.choice(
        [
            f"Si fuera una IA **de verdad** te mandaría a buscar fuentes. Como acá es **plantilla**: "
            f"sobre **{topic}** yo tiraría **{n1}** temporadas más… más o menos, con un **{chaos}%** de margen de error y cero responsabilidad civil.",
            f"Opinión **inventada** (pero con onda) sobre **{topic}**: anuncian **{n2}** cosas nuevas, **{n3}** son filler aprobado por el comité del caos, y el fandom discute igual.",
            f"Mi **cerebro de lata** interpreta **{topic}** así: el universo tira un dado, sale **{n1 + n3}**, y alguien en Twitter ya lo sabía desde el capítulo 1.",
            f"Sobre **{topic}**: ni idea real, pero para no quedar en silencio te digo que suena a **{n2}** en la escala de ‘confío en el estudio’ y **{n3}** en la de ‘me van a hacer llorar igual’.",
        ]
    )


async def _oracle_open_answer_async(pregunta: str) -> str:
    """Sin Ollama: anime/manga (AniList, definiciones), hechos vía Wikipedia, resto plantillas."""
    pq = (pregunta or "").strip()
    try:
        media = await oracle_media_open_reply_async(pq)
    except Exception:
        log.debug("Oráculo: oracle_media falló (ignorado).", exc_info=True)
        media = None
    if media:
        return media
    if _SERIOUS_FACT_RE.search(pq):
        if _oracle_wiki_fallback_enabled():
            try:
                from cogs.oracle_wiki import wikipedia_es_snippet

                wiki = await wikipedia_es_snippet(pq)
                if wiki:
                    return wiki
            except Exception:
                log.debug("Oráculo: Wikipedia fallback falló (ignorado).", exc_info=True)
        return _oracle_serious_no_llm_fallback()
    return _oracle_silly_open_templates(pq)


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


async def _roll_oracle_for_question_async(pregunta: str) -> Tuple[str, str, int]:
    """
    Si la pregunta parece abierta (cuántas, cuándo, temporadas…), contesta en modo ‘opinión’.
    Si no, mantiene sí / no / % como antes.
    """
    pq = (pregunta or "").strip()
    # Mensajes ultra cortos tipo saludo: no tiene sentido tirar sí/no/%.
    low = pq.lower()
    if low in ("hola", "holi", "buenas", "buenas!", "hello", "hey", "buen día", "buen dia", "buenas tardes", "buenas noches"):
        return "open", await _oracle_open_answer_async(pq), random.randint(1, 100)
    if _is_roulette_color_question(pq):
        return "yesno", _oracle_roulette_pick(pq), random.randint(1, 100)
    if _is_poker_push_decision_question(pq):
        return "yesno", _oracle_poker_push_answer(), random.randint(1, 100)
    if _is_multi_option_or_recommendation(pq):
        return "yesno", _oracle_multi_option_pick(pq), random.randint(1, 100)
    if _is_open_ended_question(pq):
        return "open", await _oracle_open_answer_async(pq), random.randint(1, 100)
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
    # Formato nuevo (abierto sin subtítulo): cita y luego el cuerpo suelto.
    m_plain = re.search(r"(?is)preguntó:\s*\n>\s*(.+?)\n\n(.+)\Z", desc, re.DOTALL)
    if m_plain:
        qq = (m_plain.group(1) or "").strip()
        body = (m_plain.group(2) or "").strip()
        if qq and body and not body.lstrip().startswith("**"):
            return (qq, body, "open")
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


def _oracle_reply_looks_like_anilist_recommendation(last_answer: str) -> bool:
    la = (last_answer or "").lower()
    if "anilist.co" in la:
        return True
    if "anilist" in la and re.search(r"(?is)g[eé]nero/tag|pick popular|mismo bloque", la):
        return True
    return False


def _oracle_followup_seeks_another_recommendation(user_line: str, pending: OraclePending) -> bool:
    if pending.response_kind != "open":
        return False
    if not _oracle_reply_looks_like_anilist_recommendation(pending.last_answer):
        return False
    low = " ".join((user_line or "").lower().split())
    if len(low) < 2:
        return False
    return bool(
        re.search(
            r"(?is)\b(otro|otra|otros|m[aá]s|siguiente)\b|"
            r"recomend|suger|alternativ|opciones|ideas",
            low,
        )
    )


class OraculoCog(commands.Cog, name="Oraculo"):
    """Preguntas al bot (sí / no / %)."""

    # Mismo criterio que @commands.cooldown(2, 5, commands.BucketType.user) en !pregunta
    _COOLDOWN_RATE = 2
    _COOLDOWN_PER_SEC = 5.0

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = getattr(bot, "economia_db", None)
        self.task_config = getattr(bot, "task_config", None) or {}
        super().__init__()
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
        channel: Optional[discord.abc.Messageable] = None,
        text: str,
        delete_after: float = 35.0,
    ) -> None:
        """Aviso corto al usuario cuando el embed principal no se pudo mandar.
        Con `?pregunta` no hay `reference` → hay que usar `channel.send` o el aviso nunca llega."""
        if not (text or "").strip():
            return
        if reference is None and channel is None:
            log.warning("Oráculo: fallo sin reference ni channel; no se puede avisar al usuario.")
            return
        msg = (text or "")[:1950]
        try:
            if reference is not None:
                await reference.reply(msg, mention_author=False, delete_after=delete_after)
            elif channel is not None:
                await channel.send(msg, delete_after=delete_after)
        except discord.HTTPException as re:
            log.warning("Oráculo: no se pudo enviar el aviso de fallo: %s", re)

    async def cog_load(self) -> None:
        if _oracle_use_llm():
            try:
                from cogs.oracle_llm import oracle_log_host

                host = oracle_log_host()
            except Exception:
                host = "?"
            mod = (os.getenv("ORACLE_MODEL") or "tinyllama").strip()
            to = (os.getenv("ORACLE_TIMEOUT") or "12").strip()
            yn = "sí" if _oracle_llm_yesno_via_model() else "no (dado clásico)"
            log.info(
                "Oráculo: IA local **ON** → host %s · modelo=%s · timeout≈%ss · sí/no vía modelo=%s",
                host,
                mod,
                to,
                yn,
            )
        else:
            log.info(
                "Oráculo: IA **OFF** (dado sí/no/%% + plantillas). Activar: URL en ORACLE_LLM_URL y "
                "ORACLE_USE_LLM=1 **o** ORACLE_LLM_AUTO=1; reiniciar."
            )
        if _oracle_env_show_errors():
            log.warning(
                "ORACLE_SHOW_ERRORS está activo: los fallos del oráculo mostrarán detalle en el canal "
                "(usar solo en servidores de confianza)."
            )

    async def cog_unload(self) -> None:
        try:
            from cogs.oracle_llm import close_oracle_http

            await close_oracle_http()
        except Exception:
            log.debug("Oráculo: no se pudo cerrar sesión HTTP de oracle_llm (ignorado).", exc_info=True)

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
        use_llm = _oracle_use_llm()
        # Ruleta (negro/rojo/verde): siempre pick local; el LLM en modo sí/no no entiende el contexto.
        if _is_roulette_color_question(pq):
            rb = _oracle_roulette_pick(pq)
            emb = self._embed_respuesta(
                nombre_visible=nombre_visible,
                mencion=mencion,
                pregunta=pregunta.strip(),
                body=rb,
                response_kind="yesno",
            )
            return emb, rb, "yesno"
        if _is_poker_push_decision_question(pq):
            pb = _oracle_poker_push_answer()
            emb = self._embed_respuesta(
                nombre_visible=nombre_visible,
                mencion=mencion,
                pregunta=pregunta.strip(),
                body=pb,
                response_kind="yesno",
            )
            return emb, pb, "yesno"
        if _is_multi_option_or_recommendation(pq):
            mb = _oracle_multi_option_pick(pq)
            emb = self._embed_respuesta(
                nombre_visible=nombre_visible,
                mencion=mencion,
                pregunta=pregunta.strip(),
                body=mb,
                response_kind="yesno",
            )
            return emb, mb, "yesno"
        # Cuenta resuelta en el bot primero (rápido): evita que una regex “abierta” fuerce IA antes que `2+2`.
        if _is_simple_arithmetic_question(pq):
            expr = _extract_arithmetic_expression_for_eval(pq)
            val = _safe_eval_arithmetic(expr) if expr else None
            if val is not None:
                body, response_kind = _format_math_answer_body(expr, val), "math"
            else:
                media_first = await oracle_media_open_reply_async(pq)
                if media_first:
                    body, response_kind = media_first, "open"
                else:
                    llm = await oracle_local_reply(pq, style="open") if use_llm else None
                    if llm:
                        body, response_kind = llm, "llm"
                    elif _is_open_ended_question(pq):
                        kind, body, _ = await _roll_oracle_for_question_async(pq)
                        response_kind = "open" if kind == "open" else "yesno"
                    else:
                        body = (
                            "No pude resolver esa cuenta tal cual está; "
                            "probá con `+ - * / % ^ ( )` y números simples."
                        )
                        response_kind = "open"
        elif _is_open_ended_question(pq):
            media_first = await oracle_media_open_reply_async(pq)
            if media_first:
                body, response_kind = media_first, "open"
            else:
                llm = await oracle_local_reply(pq, style="open") if use_llm else None
                if llm:
                    body, response_kind = llm, "llm"
                else:
                    expr = _extract_arithmetic_expression_for_eval(pq)
                    if expr:
                        val = _safe_eval_arithmetic(expr)
                        if val is not None:
                            body, response_kind = _format_math_answer_body(expr, val), "math"
                        else:
                            kind, body, _ = await _roll_oracle_for_question_async(pq)
                            response_kind = "open" if kind == "open" else "yesno"
                    else:
                        kind, body, _ = await _roll_oracle_for_question_async(pq)
                        response_kind = "open" if kind == "open" else "yesno"
        else:
            if use_llm and _oracle_llm_yesno_via_model():
                llm = await oracle_local_reply(pq, style="yesno")
                if llm:
                    body, response_kind = llm, "llm"
                else:
                    kind, body, _ = await _roll_oracle_for_question_async(pq)
                    response_kind = "open" if kind == "open" else "yesno"
            else:
                kind, body, _ = await _roll_oracle_for_question_async(pq)
                response_kind = "open" if kind == "open" else "yesno"
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
            self._record_oracle_use(author.id)
            log.info(
                "Oráculo: consulta publicada guild=%s channel=%s user=%s kind=%s",
                gid,
                cid,
                author.id,
                response_kind,
            )
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
                channel=channel,
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
                channel=channel,
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
            await self._oracle_reply_failure(
                reference,
                channel=channel,
                text=_oracle_user_visible_internal_error(e),
            )
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
        """Cuenta local → (opcional IA) → dado / plantilla."""
        if _is_simple_arithmetic_question(user_line):
            expr = _extract_arithmetic_expression_for_eval(user_line)
            val = _safe_eval_arithmetic(expr) if expr else None
            if val is not None:
                return _format_math_answer_body(expr, val), "math"
        if _oracle_use_llm():
            llm = await oracle_local_reply_followup(
                pending.original_question,
                pending.last_answer,
                user_line,
            )
            if llm:
                return llm, "llm"
            llm2 = await oracle_local_reply(user_line, style="open")
            if llm2:
                return llm2, "llm"
        if _oracle_followup_seeks_another_recommendation(user_line, pending):
            try:
                media_fu = await oracle_media_another_recommendation_async(
                    pending.original_question,
                    pending.last_answer,
                )
            except Exception:
                log.debug("Oráculo: otra recomendación AniList falló (ignorado).", exc_info=True)
                media_fu = None
            if media_fu:
                return media_fu, "open"
        if _is_simple_arithmetic_question(user_line):
            return (
                "No pude resolver esa cuenta; probá solo la expresión (ej. `3*4`) o `?pregunta …`.",
                "open",
            )
        kind, ans, _ = await _roll_oracle_for_question_async(user_line)
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
                channel=channel,
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
                channel=channel,
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
            await self._oracle_reply_failure(
                reference,
                channel=channel,
                text=_oracle_user_visible_internal_error(e),
            )
            return

        if persist_pending and isinstance(sent, discord.Message) and sent.guild:
            self._refresh_oracle_pending(
                pending_key,
                new_bot_message=sent,
                new_last_answer=body,
            )

    @staticmethod
    def _safe_int(val: object, default: int = 0) -> int:
        try:
            if val is None:
                return default
            return int(val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def _record_oracle_use(self, user_id: int) -> Tuple[int, int, int, int]:
        """
        Suma contador diario y opcionalmente puntos.
        Devuelve (puntos_otorgados, preguntas_hoy_tras_esta, max_con_puntos, pts_por_pregunta).
        Nunca relanza: un fallo de BD no debe dejar al usuario sin respuesta del oráculo.
        """
        if not self.db:
            return 0, 0, 0, 0
        try:
            fecha, _ = self.db.get_current_date_keys()
            prog = self.db.get_progress_diaria(user_id)
            n_before = self._safe_int(prog.get("oraculo_preguntas"), 0)
            rw = (self.task_config.get("rewards") or {})
            per = self._safe_int(rw.get("oracle_pregunta_points", 3), 3)
            mx = self._safe_int(rw.get("oracle_max_preguntas_con_puntos", 5), 5)
            gained = 0
            if per > 0 and n_before < mx:
                self.db.modify_points(user_id, per, gastar=False)
                gained = per
            self.db.update_task_diaria(user_id, "oraculo_preguntas", fecha, 1)
            n_after = n_before + 1
            return gained, n_after, mx, per
        except Exception:
            log.exception(
                "Oráculo: fallo al registrar uso en BD (user_id=%s). La consulta igual puede haberse mostrado.",
                user_id,
            )
            return 0, 0, 0, 0

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
            # Sin subtítulo “modo charla”: solo la respuesta (más limpio en Discord).
            bloque = (
                f"{mencion} **({nombre_visible})** preguntó:\n"
                f"> {q}\n\n"
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

    async def oracle_pregunta_desde_prefijo(self, ctx: commands.Context, *, texto: Optional[str] = None) -> None:
        """Lógica de `?pregunta` (el comando con prefijo lo registra `comandos_prefijo` para que no se pierda)."""
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
        description=(
            "Oráculo: sí/no/% (dado u opcional IA), abiertas con Ollama si IA activa, si no plantillas. "
            "IA: ORACLE_USE_LLM=1 o ORACLE_LLM_AUTO=1 + URL. ?pregunta."
        ),
    )
    @app_commands.describe(
        pregunta="Sí/no o abierta. Con IA: Ollama; sin IA: dado o plantillas. Opcional ORACLE_LLM_YESNO=1 para sí/no vía modelo."
    )
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
            self._record_oracle_use(interaction.user.id)
            log.info(
                "Oráculo: slash /aat-consulta publicada user=%s kind=%s",
                interaction.user.id,
                response_kind,
            )
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
                    llm = await oracle_local_reply(user_text, style="open") if _oracle_use_llm() else None
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
                        kind, ans, _ = await _roll_oracle_for_question_async(user_text)
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
