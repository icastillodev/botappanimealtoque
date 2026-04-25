# Cliente Ollama (`/api/generate`) — oráculo del bot (opcional vía ORACLE_USE_LLM / ORACLE_LLM_AUTO).
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import aiohttp
from duckduckgo_search import DDGS

log = logging.getLogger(__name__)

_oracle_http_lock: Optional[asyncio.Lock] = None
_oracle_http_session: Optional[aiohttp.ClientSession] = None

# Solo hacemos búsqueda web cuando parece “pregunta de hechos” (si no, es latencia gratis).
_WEB_WORTH_IT_RE = re.compile(
    r"(?is)"
    r"\b(qué\s+es|que\s+es|defin(?:i|í)|explic(?:a|á|ame|ame)|"
    r"cu[aá]ndo|d[oó]nde|por\s+qu[eé]|"
    r"fecha|estren|sale|cap[ií]tulo|episodio|temporada|"
    r"qu[ií]en\s+es|qu[ií]en\s+fue|"
    r"precio|valor|cu[aá]nto\s+cuesta|"
    r"ranking|top|lista|"
    r"wikipedia|fuente|link)\b"
)


def _oracle_http_lock_get() -> asyncio.Lock:
    global _oracle_http_lock
    if _oracle_http_lock is None:
        _oracle_http_lock = asyncio.Lock()
    return _oracle_http_lock


async def close_oracle_http() -> None:
    """Cierra la sesión aiohttp compartida (p. ej. al descargar el cog)."""
    global _oracle_http_session
    async with _oracle_http_lock_get():
        if _oracle_http_session is not None and not _oracle_http_session.closed:
            await _oracle_http_session.close()
        _oracle_http_session = None


async def _oracle_http_session_get() -> aiohttp.ClientSession:
    global _oracle_http_session
    async with _oracle_http_lock_get():
        if _oracle_http_session is None or _oracle_http_session.closed:
            _oracle_http_session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
                headers={"User-Agent": "AnimeAlToque-Oracle/1.0"},
            )
        return _oracle_http_session

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
    "Sos el oráculo de un Discord de anime/otaku; **español rioplatense** si encaja el tono. "
    "Si piden **recomendación** o **qué elegir**, nombrá **una** opción concreta (podés humorizar). "
    "Si es **opinión**, lore o explicación corta: **idea completa** en pocas palabras; "
    "no repitas la pregunta entera ni dejes la frase a medias. "
    "**Máximo {max_words} palabras** en total (contalas; menos es mejor). "
    "Sin listas numeradas, sin comillas decorativas, sin roleplay de sistema. "
    "No inventés fechas oficiales, estrenos ni citas verificables. "
    "Si te doy **contexto web** (snippets), usalo como apoyo; si no alcanza, decí que no podés verificarlo. "
    "Si el usuario solo quiere **suerte sí/no**, otra parte del bot puede usar dado; "
    "vos priorizás criterio cuando piden opinión, consejo o charla."
)

_SYSTEM_FOLLOWUP = (
    "Seguís como oráculo del mismo Discord; español. "
    "Contestá al **último mensaje** del usuario: concreto; si piden recomendación, decí qué harías. "
    "Una frase o dos muy cortas si cerrás mejor; **máx. {max_words} palabras** en total (menos es mejor). "
    "No repitas reglas, encabezados ni el texto del contexto; solo tu respuesta final."
)

# Modo sí/no vía modelo (cuando ORACLE_LLM_YESNO=1 en el cog): una línea, tono oráculo.
_SYSTEM_YESNO_LAYER = (
    "Esta consulta va en modo **adivinación sí/no** (no ensayo largo). "
    "Respondé **una sola frase** (máx. {max_words} palabras): **Sí**, **No**, **quizás**, o humor breve con **%** si encaja. "
    "Sin párrafos ni explicación de reglas."
)


def _normalize_generate_url(raw: str) -> str:
    """Acepta URL completa a `/api/generate` o solo base `http://host:11434`."""
    u = (raw or "").strip()
    if not u:
        return ""
    base = u.rstrip("/")
    if base.endswith("/api/generate"):
        return base
    if "/api/" in u and not base.endswith("/api/generate"):
        log.warning(
            "ORACLE_LLM_URL debería terminar en /api/generate (Ollama). Valor recibido: %s",
            u[:120],
        )
    return base + "/api/generate"


def _system_oracle_combined(*, max_words: int, style: str) -> str:
    sys = _SYSTEM_ORACLE.format(max_words=max_words)
    extra = (os.getenv("ORACLE_SYSTEM_SUFFIX") or "").strip()
    if extra:
        sys = f"{sys}\n\n{extra}"
    if style == "yesno":
        sys = f"{sys}\n\n{_SYSTEM_YESNO_LAYER.format(max_words=max_words)}"
    return sys


def _ollama_endpoint_log_label(url: str) -> str:
    try:
        p = urlparse(url)
        host = p.hostname or "?"
        port = f":{p.port}" if p.port else ""
        return f"{host}{port}"
    except Exception:
        return "?"


def oracle_effective_generate_url() -> str:
    """URL normalizada para logs y comprobaciones (misma que usa el POST)."""
    return _normalize_generate_url(os.getenv("ORACLE_LLM_URL") or "")


def oracle_log_host() -> str:
    """Host:puerto del endpoint Ollama (sin path), para logs."""
    return _ollama_endpoint_log_label(oracle_effective_generate_url())


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
    # num_predict lo fija cada caller (consulta vs seguimiento); no pisar con ORACLE_NUM_PREDICT acá.
    np = max(16, min(160, int(num_predict)))
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


def _env_truthy(key: str) -> bool:
    return (os.getenv(key) or "").strip().lower() in ("1", "true", "yes", "on")


def _format_web_context(results: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for r in results:
        title = " ".join((r.get("title") or "").split()).strip()
        body = " ".join((r.get("body") or "").split()).strip()
        href = (r.get("href") or "").strip()
        if not (title or body):
            continue
        if len(title) > 110:
            title = title[:109].rstrip() + "…"
        if len(body) > 220:
            body = body[:219].rstrip() + "…"
        if href and len(href) > 240:
            href = href[:239].rstrip() + "…"
        bit = f"- {title or '(sin título)'} — {body or '…'}"
        if href:
            bit += f" ({href})"
        lines.append(bit)
    if not lines:
        return ""
    # Mantener corto: 3–5 resultados.
    head = "Contexto web (DuckDuckGo, snippets; puede estar incompleto):\n"
    txt = head + "\n".join(lines[:5])
    return txt[:1400].rstrip()


def _duckduckgo_text_sync(query: str, *, max_results: int) -> list[dict[str, str]]:
    # duckduckgo_search es sync; lo corremos en thread con to_thread.
    q = " ".join((query or "").split()).strip()
    if not q or len(q) < 3:
        return []
    out: list[dict[str, str]] = []
    with DDGS() as ddgs:
        for r in ddgs.text(q, max_results=max_results, region="es-es", safesearch="moderate"):
            if not isinstance(r, dict):
                continue
            # r suele traer: title, href, body
            out.append(
                {
                    "title": str(r.get("title") or ""),
                    "href": str(r.get("href") or ""),
                    "body": str(r.get("body") or ""),
                }
            )
            if len(out) >= max_results:
                break
    return out


async def _duckduckgo_context_async(query: str) -> str:
    if not _env_truthy("ORACLE_INTERNET_SEARCH"):
        return ""
    q0 = " ".join((query or "").split()).strip()
    # Evitar búsquedas para “hola”, “jaja”, etc.
    if len(q0) < 14:
        return ""
    # Evitar latencia si no parece una consulta que se beneficie con web.
    if not _WEB_WORTH_IT_RE.search(q0):
        return ""
    try:
        max_results = _env_int("ORACLE_INTERNET_SEARCH_MAX_RESULTS", 4, lo=2, hi=6)
        timeout_sec = float((os.getenv("ORACLE_INTERNET_SEARCH_TIMEOUT") or "3.5").strip())
    except ValueError:
        timeout_sec = 3.5
        max_results = 4
    try:
        res = await asyncio.wait_for(
            asyncio.to_thread(_duckduckgo_text_sync, query, max_results=max_results),
            timeout=max(1.5, min(8.0, timeout_sec)),
        )
    except asyncio.TimeoutError:
        return ""
    except Exception:
        log.debug("DuckDuckGo search falló (ignorado).", exc_info=True)
        return ""
    return _format_web_context(res if isinstance(res, list) else [])


async def _ollama_post_generate(url: str, payload: Dict[str, Any], timeout_sec: float) -> Optional[Dict[str, Any]]:
    # total + sock_read: evita colgarse si Ollama tarda más de lo esperado.
    t = max(5.0, float(timeout_sec))
    timeout = aiohttp.ClientTimeout(total=t + 4.0, connect=8.0, sock_read=t + 3.0)
    try:
        session = await _oracle_http_session_get()
        async with session.post(url, json=payload, timeout=timeout) as resp:
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
        log.warning("Oracle LLM: timeout (%s)", _ollama_endpoint_log_label(url))
        return None
    except aiohttp.ClientError:
        log.exception("Oracle LLM: error de red (%s)", _ollama_endpoint_log_label(url))
        return None
    except Exception:
        log.exception("Oracle LLM: error inesperado")
        return None


async def _ollama_post_generate_guarded(
    url: str, payload: Dict[str, Any], timeout_sec: float
) -> Optional[Dict[str, Any]]:
    """Capa extra: nunca dejamos colgado el event loop más de timeout+6s."""
    cap = max(12.0, float(timeout_sec) + 6.0)
    try:
        return await asyncio.wait_for(
            _ollama_post_generate(url, payload, timeout_sec),
            timeout=cap,
        )
    except asyncio.TimeoutError:
        log.warning("Oracle LLM: cortado por wait_for (>%ss)", cap)
        return None


async def oracle_local_reply(user_question: str, *, style: str = "open") -> Optional[str]:
    """
    Llama a Ollama si hay URL configurada (el cog decide si la IA está activada).
    style: \"open\" (opinión / charla) o \"yesno\" (una frase tipo adivinación).
    """
    url = _normalize_generate_url(os.getenv("ORACLE_LLM_URL") or "")
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
        num_pred = int((os.getenv("ORACLE_NUM_PREDICT") or "48").strip())
    except ValueError:
        num_pred = 48
    num_pred = max(16, min(96, num_pred))
    if style == "yesno":
        num_pred = min(num_pred, 56)
    # `prompt` = solo la consulta; reglas en `system` (API Ollama) para menos eco y menos tokens.
    st = style if style in ("open", "yesno") else "open"
    system = _system_oracle_combined(max_words=mw, style=st)
    web_ctx = ""
    if st == "open":
        web_ctx = await _duckduckgo_context_async(q)
    prompt = q if not web_ctx else (web_ctx + "\n\nPregunta del usuario:\n" + q)
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

    data = await _ollama_post_generate_guarded(url, payload, timeout_sec)
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
    url = _normalize_generate_url(os.getenv("ORACLE_LLM_URL") or "")
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
    sfx = (os.getenv("ORACLE_SYSTEM_SUFFIX") or "").strip()
    if sfx:
        system = f"{system}\n\n{sfx}"
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
    num_pred = max(16, min(72, num_pred))
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

    data = await _ollama_post_generate_guarded(url, payload, timeout_sec)
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
