# Resumen corto desde Wikipedia (es) para el oráculo sin Ollama.
# Requiere User-Agent descriptivo (política de Wikimedia).
from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, List, Optional
from urllib.parse import quote, urlencode

import aiohttp

log = logging.getLogger(__name__)

_API = "https://es.wikipedia.org/w/api.php"
_SUMMARY = "https://es.wikipedia.org/api/rest_v1/page/summary/{title}"
_DEFAULT_UA = (
    "AnimeAlToqueOracle/1.0 (Discord bot; sin URL pública fija) "
    "Python/aiohttp — resúmenes Wikipedia para el oráculo"
)


def _ua() -> str:
    import os

    u = (os.getenv("ORACLE_WIKI_UA") or "").strip()
    return u if u else _DEFAULT_UA


def _strip_html(s: str) -> str:
    t = re.sub(r"<[^>]+>", " ", s)
    t = html.unescape(t)
    return " ".join(t.split()).strip()


def _title_for_rest(title: str) -> str:
    return quote(title.replace(" ", "_"), safe="()%'")


async def _wiki_search(session: aiohttp.ClientSession, q: str) -> List[str]:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": q[:280],
        "utf8": "1",
        "format": "json",
        "srlimit": "5",
    }
    url = f"{_API}?{urlencode(params)}"
    async with session.get(url) as resp:
        if resp.status != 200:
            return []
        data: Any = await resp.json(content_type=None)
    hits = (((data or {}).get("query") or {}).get("search")) or []
    out: List[str] = []
    for h in hits:
        t = (h or {}).get("title")
        if isinstance(t, str) and t.strip():
            out.append(t.strip())
    return out


async def _wiki_summary(session: aiohttp.ClientSession, title: str) -> Optional[str]:
    path = _title_for_rest(title)
    url = _SUMMARY.format(title=path)
    async with session.get(url) as resp:
        if resp.status != 200:
            return None
        try:
            data: Any = await resp.json(content_type=None)
        except (json.JSONDecodeError, aiohttp.ContentTypeError):
            return None
    if not isinstance(data, dict):
        return None
    if (data.get("type") or "").lower() in ("disambiguation", "not_found", "redir"):
        return None
    ext = data.get("extract")
    if not isinstance(ext, str) or not ext.strip():
        return None
    text = _strip_html(ext)
    if len(text) < 40:
        return None
    return text


async def wikipedia_es_snippet(query: str, *, max_chars: int = 400) -> Optional[str]:
    """
    Devuelve un párrafo breve (extract) o None.
    No usa ORACLE_WIKI_FALLBACK: el caller decide si consultar.
    """
    q = (query or "").strip()
    if len(q) < 4:
        return None
    timeout = aiohttp.ClientTimeout(total=10.0, connect=6.0, sock_read=6.0)
    headers = {"User-Agent": _ua(), "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            titles = await _wiki_search(session, q)
            for title in titles:
                body = await _wiki_summary(session, title)
                if body:
                    if len(body) > max_chars:
                        cut = body[: max_chars - 1].rsplit(" ", 1)[0]
                        body = (cut or body[:max_chars]).rstrip(",;:") + "…"
                    return (
                        f"{body}\n\n"
                        f"_Resumen tomado de **Wikipedia** (es); comprobá en la fuente si es para un examen._"
                    )
    except aiohttp.ClientError:
        log.debug("oracle_wiki: error de red", exc_info=True)
    except Exception:
        log.debug("oracle_wiki: error inesperado", exc_info=True)
    return None
