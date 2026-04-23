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

_SYSTEM_WRAPPER = """Sos el oráculo de un servidor de Discord sobre anime y cultura otaku.
Reglas OBLIGATORIAS:
- Respondé solo en español, una sola frase.
- Como máximo {max_words} palabras (contalas; sin viñetas ni párrafos).
- Onda jocosa o mística corta; no spoilers largos ni ensayos.
- No presentes hechos de estrenos/fechas como verificados; si no sabés, tirá opinión corta o meme.
Pregunta:
{q}

Respuesta (máximo {max_words} palabras, una frase):"""

_FOLLOWUP_WRAPPER = """Sos el oráculo de un servidor de Discord (anime / cultura otaku). Estás en un SEGUIMIENTO: el usuario ya hizo una consulta y vos ya respondiste.

Consulta original (resumida):
{orig_q}

Tu respuesta anterior (resumida):
{prev_a}

Ahora el usuario agrega (puede ser aclaración, réplica, duda corta, ironía o un "y si…"):
{user_msg}

Reglas OBLIGATORIAS:
- Solo español, UNA frase.
- Máximo {max_words} palabras (sin viñetas ni párrafos).
- Continuá el tono (jocoso o místico-corto) y respondé a lo que acaba de decir, sin repetir literal tu frase anterior.
- No afirmes fechas/datos oficiales; si no aplica, decilo con humor breve.

Tu respuesta (máximo {max_words} palabras):"""


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
        timeout_sec = float((os.getenv("ORACLE_TIMEOUT") or "15").strip())
    except ValueError:
        timeout_sec = 15.0
    try:
        temperature = float((os.getenv("ORACLE_TEMPERATURE") or "0.3").strip())
    except ValueError:
        temperature = 0.3

    q = (user_question or "").strip()[:600]
    if len(q) < 2:
        return None

    prompt = _SYSTEM_WRAPPER.format(q=q, max_words=_MAX_WORDS)
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 48,
        },
    }

    timeout = aiohttp.ClientTimeout(total=max(3.0, timeout_sec))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = (await resp.text())[:300]
                    log.warning("Oracle LLM HTTP %s: %s", resp.status, body)
                    return None
                try:
                    data = await resp.json(content_type=None)
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

    text = data.get("response") if isinstance(data, dict) else None
    if not text or not isinstance(text, str):
        return None
    out = _truncate_response(text)
    return out or None


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
        timeout_sec = float((os.getenv("ORACLE_TIMEOUT") or "15").strip())
    except ValueError:
        timeout_sec = 15.0
    try:
        temperature = float((os.getenv("ORACLE_TEMPERATURE") or "0.35").strip())
    except ValueError:
        temperature = 0.35

    oq = (original_question or "").strip()[:400]
    pa = (previous_answer or "").strip()[:400]
    uf = (user_followup or "").strip()[:400]
    if len(uf) < 1:
        return None

    mw = int((os.getenv("ORACLE_FOLLOWUP_MAX_WORDS") or str(_FOLLOWUP_MAX_WORDS)).strip() or _FOLLOWUP_MAX_WORDS)
    mw = max(6, min(24, mw))

    prompt = _FOLLOWUP_WRAPPER.format(
        orig_q=oq or "(sin texto)",
        prev_a=pa or "(nada)",
        user_msg=uf,
        max_words=mw,
    )
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 72,
        },
    }

    timeout = aiohttp.ClientTimeout(total=max(3.0, timeout_sec))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = (await resp.text())[:300]
                    log.warning("Oracle LLM follow-up HTTP %s: %s", resp.status, body)
                    return None
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    log.warning("Oracle LLM follow-up: JSON inválido")
                    return None
    except asyncio.TimeoutError:
        log.warning("Oracle LLM follow-up: timeout")
        return None
    except aiohttp.ClientError:
        log.exception("Oracle LLM follow-up: error de red")
        return None
    except Exception:
        log.exception("Oracle LLM follow-up: error inesperado")
        return None

    text = data.get("response") if isinstance(data, dict) else None
    if not text or not isinstance(text, str):
        return None
    out = _truncate_followup(text)
    return out or None
