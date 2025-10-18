# cogs/impostor/chars.py
import os
from typing import List, Tuple
import aiohttp
import asyncio
import random

CHAR_BASE = os.getenv("IMPOSTOR_CHAR_BASE", "https://animealtoque.com/personajes/").rstrip("/") + "/"
CHAR_ENDPOINT = os.getenv("IMPOSTOR_CHAR_ENDPOINT", "").strip()

# Fallback local por si tu endpoint no está listo
_FALLBACK: List[Tuple[str, str]] = [
    ("Naruto Uzumaki", "naruto-uzumaki"),
    ("Sasuke Uchiha", "sasuke-uchiha"),
    ("Itachi Uchiha", "itachi-uchiha"),
    ("Kakashi Hatake", "kakashi-hatake"),
    ("Sakura Haruno", "sakura-haruno"),
    ("Hinata Hyuga", "hinata-hyuga"),
    ("Gaara", "gaara"),
    ("Jiraiya", "jiraiya"),
    ("Minato Namikaze", "minato-namikaze"),
    ("Madara Uchiha", "madara-uchiha"),
]

_cached: List[Tuple[str, str]] = []

async def _fetch_remote() -> List[Tuple[str, str]]:
    if not CHAR_ENDPOINT:
        return []
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.get(CHAR_ENDPOINT) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
                # Esperamos una lista de objetos con name/slug
                out: List[Tuple[str, str]] = []
                for item in data:
                    name = str(item.get("name") or item.get("nombre") or "").strip()
                    slug = str(item.get("slug") or item.get("url") or "").strip().strip("/")
                    if name and slug:
                        out.append((name, slug))
                return out
    except Exception:
        return []

async def ensure_cache():
    global _cached
    if _cached:
        return
    rem = await _fetch_remote()
    _cached = rem if rem else list(_FALLBACK)

def pick_random() -> Tuple[str, str]:
    if not _cached:
        # en caso extremo (llamar sin ensure)
        return random.choice(_FALLBACK)
    return random.choice(_cached)

def to_link(slug: str) -> str:
    return CHAR_BASE + slug
