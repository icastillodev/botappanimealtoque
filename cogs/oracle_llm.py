# Cliente mínimo para Ollama (`/api/generate`) — oráculo del bot.
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, Optional

import aiohttp

log = logging.getLogger(__name__)

# Defaults (sobreescribibles con env: ORACLE_MAX_WORDS, ORACLE_MAX_CHARS, ORACLE_FOLLOWUP_*).
_DEF_MAX_WORDS = 20
_DEF_MAX_CHARS = 340
_DEF_FOLLOWUP_MAX_WORDS = 26
_DEF_FOLLOWUP_MAX_CHARS = 440


def _env_int(key: str, default: int, *, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int((os.getenv(key) or str(default)).strip())))
    except ValueError:
        return default


def oracle_max_words_primary() -> int:
    return _env_int("ORACLE_MAX_WORDS", _DEF_MAX_WORDS, lo=5, hi=40)


def oracle_max_chars_primary() -> int:
    return _env_int("ORACLE_MAX_CHARS", _DEF_MAX_CHARS, lo=120, hi=900)


def oracle_max_words_followup() -> int:
    return _env_int("ORACLE_FOLLOWUP_MAX_WORDS", _DEF_FOLLOWUP_MAX_WORDS, lo=6, hi=48)


def oracle_max_chars_followup() -> int:
    return _env_int("ORACLE_FOLLOWUP_MAX_CHARS", _DEF_FOLLOWUP_MAX_CHARS, lo=150, hi=1000)


# System (campo `system` en Ollama). {max_words} se rellena al llamar.
_SYSTEM_ORACLE = (
    "Sos el oráculo de un Discord de anime/otaku; respondés en español. "
    "Si piden **recomendación** o **qué elegir**, decí opción concreta (aunque sea con humor). "
    "Si es **opinión**, historia, cultura o explicación breve, contestá con **idea completa**: "
    "no repitas el título de la pregunta ni te quedes a medias; preferí **una** frase cerrada, "
    "o **dos frases muy cortas** si hace falta para no cortar el sentido. "
    "**Máximo {max_words} palabras** en total (contalas; cuantas menos, mejor). "
    "Sin listas numeradas ni comillas decorativas. Tono jocoso o místico OK. "
    "No inventés fechas oficiales ni citas verificables. "
    "Las preguntas que son solo sí/no al azar las responde **otra parte del bot** (dado: 40% sí, 40% no, 20% con %); "
    "acá respondés con criterio cuando piden opinión, datos generales o consejo."
)

_SYSTEM_FOLLOWUP = (
    "Seguís como oráculo del mismo Discord; español. "
    "Contestá al **último mensaje** del usuario: concreto; si piden recomendación, decí qué harías. "
    "Una frase o dos muy cortas si cerrás mejor; **máx. {max_words} palabras** en total (menos es mejor). "
    "No repitas reglas, encabezados ni el texto del contexto; solo tu respuesta final."
)


def _truncate_response(text: str, *, max_words: int, max_chars: int) -> str:
    t = " ".join((text or "").replace("\n", " ").split()).strip()
    if not t:
        return ""
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    words = t.split()
    if len(words) > max_words:
        t = " ".join(words[:max_words])
    if len(t) > max_chars:
        t = t[: max_chars - 1].rstrip() + "…"
    return t


def _truncate_followup(text: str, *, max_words: int, max_chars: int) -> str:
    t = " ".join((text or "").replace("\n", " ").split()).strip()
    if not t:
        return ""
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    words = t.split()
    if len(words) > max_words:
        t = " ".join(words[:max_words])
    if len(t) > max_chars:
        t = t[: max_chars - 1].rstrip() + "…"
    return t


def _response_echoes_instructions(text: str) -> bool:
    """Modelos muy chicos a veces repiten el system o el prompt; preferimos fallback del cog."""
    low = (text or "").lower()
    if re.search(r"máximo\s+\d+\s*palabras", low) or re.search(r"maximo\s+\d+\s*palabras", low):
        return True
    needles = (
        "reglas oblig",
        "respondé solo",
        "respondí solo",
        "sigo de discord",
        "obligatorias:",
        "máximo 8 palabras",
        "máximo 14",
        "palabras (cont",
        "discord] reglas",
        # Eco del follow-up (tinyllama y similares)
        "seguís como oráculo",
        "seguis como oraculo",
        "seguimos como oración",
        "seguís como oración",
        "mismo discord",
        "del mismo discord",
        "respondé una frase",
        "respondé una sola frase",
        "una frase en español",
        "al mensaje nuevo",
        "mensaje nuevo del usuario",
        "pregunta inicial:",
        "tu respuesta anterior",
        "tu nueva respuesta",
        "oración del mismo",
        "no repitas literal",
        "solo una frase",
        "tu frase anterior",
        "contexto (no lo repitas)",
        "contexto breve (no lo copies)",
        "(no lo copies)",
        "contestá solo con tu frase",
        "usuario ahora:",
    )
    return any(n in low for n in needles)


def _ollama_options(*, num_predict: int) -> Dict[str, Any]:
    try:
        temperature = float((os.getenv("ORACLE_TEMPERATURE") or "0.3").strip())
    except ValueError:
        temperature = 0.3
    try:
        num_ctx = int((os.getenv("ORACLE_NUM_CTX") or "1024").strip())
    except ValueError:
        num_ctx = 1024
    num_ctx = max(256, min(8192, num_ctx))
    np = num_predict
    try:
        np = int((os.getenv("ORACLE_NUM_PREDICT") or str(num_predict)).strip())
    except ValueError:
        np = num_predict
    np = max(16, min(160, np))
    opts: Dict[str, Any] = {
        "temperature": temperature,
        "num_predict": np,
        "num_ctx": num_ctx,
    }
    # Menos lag entre consultas: deja el modelo cargado en Ollama (desactivá con ORACLE_KEEP_ALIVE=0).
    try:
        top_p = float((os.getenv("ORACLE_TOP_P") or "0.9").strip())
        if 0.5 <= top_p < 1.0:
            opts["top_p"] = top_p
    except ValueError:
        pass
    return opts


def _ollama_keep_alive() -> Optional[str]:
    raw = (os.getenv("ORACLE_KEEP_ALIVE") or "5m").strip()
    if not raw or raw.lower() in ("0", "false", "no", "off"):
        return None
    return raw


async def _ollama_post_generate(url: str, payload: Dict[str, Any], timeout_sec: float) -> Optional[Dict[str, Any]]:
    timeout = aiohttp.ClientTimeout(total=max(3.0, timeout_sec))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = (await resp.text())[:300]
                    log.warning("Oracle LLM HTTP %s: %s", resp.status, body)
                    return None
                try:
                    return await resp.json(content_type=None)
                except Exception:
                    log.warning("Oracle LLM: JSON inválido")
                    return None
    except asyncio.TimeoutError:
        log.warning("Oracle LLM: timeout")
        return None
    except aiohttp.ClientError:
        log.exception("Oracle LLM: error de red")
        return None
    except Exception:
        log.exception("Oracle LLM: error inesperado")
        return None


async def oracle_local_reply(user_question: str) -> Optional[str]:
    """
    Llama a Ollama (o compatible) si ORACLE_LLM_URL está definido.
    Devuelve texto corto o None si falla / no hay URL.
    """
    url = (os.getenv("ORACLE_LLM_URL") or "").strip()
    if not url:
        return None
    model = (os.getenv("ORACLE_MODEL") or "tinyllama").strip()
    try:
        timeout_sec = float((os.getenv("ORACLE_TIMEOUT") or "12").strip())
    except ValueError:
        timeout_sec = 12.0

    q = (user_question or "").strip()[:600]
    if len(q) < 2:
        return None

    mw = oracle_max_words_primary()
    mc = oracle_max_chars_primary()
    try:
        num_pred = int((os.getenv("ORACLE_NUM_PREDICT") or "72").strip())
    except ValueError:
        num_pred = 72
    # `prompt` = solo la consulta; reglas en `system` (API Ollama) para menos eco y menos tokens.
    system = _SYSTEM_ORACLE.format(max_words=mw)
    payload: Dict[str, Any] = {
        "model": model,
        "system": system,
        "prompt": q,
        "stream": False,
        "options": _ollama_options(num_predict=num_pred),
    }
    ka = _ollama_keep_alive()
    if ka:
        payload["keep_alive"] = ka

    data = await _ollama_post_generate(url, payload, timeout_sec)
    if not isinstance(data, dict):
        return None

    text = data.get("response")
    if not text or not isinstance(text, str):
        return None
    out = _truncate_response(text, max_words=mw, max_chars=mc)
    if not out:
        return None
    if _response_echoes_instructions(out):
        log.info("Oracle LLM: respuesta parece eco del prompt; se usa fallback del oráculo.")
        return None
    return out


async def oracle_local_reply_followup(
    original_question: str,
    previous_answer: str,
    user_followup: str,
) -> Optional[str]:
    """
    Misma URL/modelo que `oracle_local_reply`, pero con contexto de la consulta anterior.
    """
    url = (os.getenv("ORACLE_LLM_URL") or "").strip()
    if not url:
        return None
    model = (os.getenv("ORACLE_MODEL") or "tinyllama").strip()
    try:
        timeout_sec = float((os.getenv("ORACLE_TIMEOUT") or "12").strip())
    except ValueError:
        timeout_sec = 12.0

    oq = (original_question or "").strip()[:400]
    pa = (previous_answer or "").strip()[:400]
    uf = (user_followup or "").strip()[:400]
    if len(uf) < 1:
        return None

    mw = oracle_max_words_followup()
    mc = oracle_max_chars_followup()
    mw = max(6, min(48, mw))

    system = _SYSTEM_FOLLOWUP.format(max_words=mw)
    # Prompt compacto: menos texto copiable por modelos chicos.
    prompt = (
        f"Contexto breve (no lo copies): antes «{(oq or '…')[:200]}»; tu línea anterior «{(pa or '…')[:160]}».\n"
        f"El usuario ahora dice: «{uf}»\n"
        "Contestá solo con tu frase (sin repetir esta consigna):"
    )
    try:
        num_pred = int((os.getenv("ORACLE_NUM_PREDICT_FOLLOWUP") or "40").strip())
    except ValueError:
        num_pred = 40
    payload: Dict[str, Any] = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": _ollama_options(num_predict=num_pred),
    }
    ka = _ollama_keep_alive()
    if ka:
        payload["keep_alive"] = ka

    data = await _ollama_post_generate(url, payload, timeout_sec)
    if not isinstance(data, dict):
        return None

    text = data.get("response")
    if not text or not isinstance(text, str):
        return None
    out = _truncate_followup(text, max_words=mw, max_chars=mc)
    if not out:
        return None
    if _response_echoes_instructions(out):
        log.info("Oracle LLM follow-up: eco del prompt; fallback plantilla.")
        return None
    return out
