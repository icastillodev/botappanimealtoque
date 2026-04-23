# Cliente mínimo para Ollama (`/api/generate`) — oráculo del bot.
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

import aiohttp

log = logging.getLogger(__name__)

# Respuesta muy corta (pedido del staff): ~8 palabras máximo.
_MAX_WORDS = 8
_MAX_CHARS = 100

# Seguimiento (respondiendo al mensaje del oráculo): un poco más de aire que la primera tirada.
_FOLLOWUP_MAX_WORDS = 14
_FOLLOWUP_MAX_CHARS = 180

# System corto (va en el campo `system` de Ollama): modelos chicos suelen repetir prompts largos mezclados en `prompt`.
_SYSTEM_ORACLE = (
    "Sos el oráculo de un Discord de anime/otaku. "
    "Respondé UNA sola frase en español, tono jocoso o místico, sin listas ni comillas. "
    "Máximo {max_words} palabras. Opiná o inventá; no afirmes fechas oficiales."
)

_SYSTEM_FOLLOWUP = (
    "Seguís como oráculo del mismo Discord. "
    "Respondé UNA frase en español al mensaje nuevo del usuario; máximo {max_words} palabras. "
    "No repitas literal tu frase anterior; sin listas."
)


def _truncate_response(text: str) -> str:
    t = " ".join((text or "").replace("\n", " ").split()).strip()
    if not t:
        return ""
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    words = t.split()
    if len(words) > _MAX_WORDS:
        t = " ".join(words[:_MAX_WORDS])
    if len(t) > _MAX_CHARS:
        t = t[: _MAX_CHARS - 1].rstrip() + "…"
    return t


def _truncate_followup(text: str) -> str:
    t = " ".join((text or "").replace("\n", " ").split()).strip()
    if not t:
        return ""
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    words = t.split()
    if len(words) > _FOLLOWUP_MAX_WORDS:
        t = " ".join(words[:_FOLLOWUP_MAX_WORDS])
    if len(t) > _FOLLOWUP_MAX_CHARS:
        t = t[: _FOLLOWUP_MAX_CHARS - 1].rstrip() + "…"
    return t


def _response_echoes_instructions(text: str) -> bool:
    """Modelos muy chicos a veces repiten el system; en ese caso preferimos fallback del cog."""
    low = (text or "").lower()
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

    # `prompt` = solo la consulta; reglas en `system` (API Ollama) para menos eco y menos tokens.
    system = _SYSTEM_ORACLE.format(max_words=_MAX_WORDS)
    payload: Dict[str, Any] = {
        "model": model,
        "system": system,
        "prompt": q,
        "stream": False,
        "options": _ollama_options(num_predict=28),
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
    out = _truncate_response(text)
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

    try:
        mw = int((os.getenv("ORACLE_FOLLOWUP_MAX_WORDS") or str(_FOLLOWUP_MAX_WORDS)).strip())
    except ValueError:
        mw = _FOLLOWUP_MAX_WORDS
    mw = max(6, min(24, mw))

    system = _SYSTEM_FOLLOWUP.format(max_words=mw)
    prompt = (
        f"Pregunta inicial:\n{oq or '—'}\n\n"
        f"Tu respuesta anterior:\n{pa or '—'}\n\n"
        f"Mensaje nuevo del usuario:\n{uf}\n\n"
        "Tu nueva respuesta (una sola frase):"
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
    out = _truncate_followup(text)
    if not out:
        return None
    if _response_echoes_instructions(out):
        log.info("Oracle LLM follow-up: eco del prompt; fallback plantilla.")
        return None
    return out
