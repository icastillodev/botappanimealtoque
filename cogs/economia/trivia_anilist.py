# Preguntas trivia desde AniList (GraphQL público), para variedad casi infinita.
from __future__ import annotations

import logging
import os
import random
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger(__name__)

ANILIST_URL = "https://graphql.anilist.co"

QUERY_PAGE = """
query ($page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    media(
      type: ANIME,
      sort: POPULARITY_DESC,
      popularity_greater: 1200,
      averageScore_greater: 52
    ) {
      title { romaji english userPreferred }
      seasonYear
      episodes
      format
      studios(isMain: true) { nodes { name } }
    }
  }
}
"""


async def try_fetch_anilist_trivia_question(
    *,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[Dict[str, Any]]:
    """
    Devuelve {"q": str, "answers": [str, ...]} o None si falla / datos incompletos.
    """
    close_after = False
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12))
        close_after = True
    try:
        page = random.randint(1, 12)
        per_page = random.randint(24, 48)
        payload = {"query": QUERY_PAGE, "variables": {"page": page, "perPage": per_page}}
        async with session.post(ANILIST_URL, json=payload, headers={"Content-Type": "application/json"}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        media_list = (((data or {}).get("data") or {}).get("Page") or {}).get("media") or []
        if not isinstance(media_list, list) or not media_list:
            return None
        m = random.choice(media_list)
        title_romaji = str((m.get("title") or {}).get("romaji") or "").strip()
        title_eng = str((m.get("title") or {}).get("english") or "").strip()
        title_pref = str((m.get("title") or {}).get("userPreferred") or "").strip()
        title = title_romaji or title_eng or title_pref or "?"
        year = m.get("seasonYear")
        eps = m.get("episodes")
        fmt = str(m.get("format") or "").strip()
        studios = (
            ((m.get("studios") or {}).get("nodes") or []) if isinstance(m.get("studios"), dict) else []
        )
        studio_name = ""
        if studios and isinstance(studios[0], dict):
            studio_name = str(studios[0].get("name") or "").strip()

        roll = random.random()
        min_pop = float(os.getenv("TRIVIA_ANILIST_DIFFICULTY", "0.55") or 0.55)

        # Preguntas más “difíciles” mezclan año, episodios y estudio (datos reales).
        if roll < min_pop and year:
            q = f'¿En qué año salió **{title}** (AniList)?'
            answers: List[str] = [str(int(year))]
            return {"q": q, "answers": answers}

        if roll < 0.72 and eps and int(eps) > 0 and int(eps) < 400:
            q = f'¿Cuántos episodios tiene **{title}** en AniList? (número entero)'
            answers = [str(int(eps))]
            return {"q": q, "answers": answers}

        if roll < 0.9 and studio_name and len(studio_name) < 60:
            q = f'¿Qué estudio es el principal de **{title}** en AniList? (nombre corto o completo)'
            answers = [studio_name]
            return {"q": q, "answers": answers}

        if fmt in ("TV", "MOVIE", "OVA", "ONA", "SPECIAL") and random.random() > min_pop:
            q = f'¿Qué **formato** tiene **{title}** en AniList? (TV / MOVIE / OVA / ONA / SPECIAL, en mayúsculas como allí)'
            return {"q": q, "answers": [fmt]}

        if year:
            return {
                "q": f'¿En qué año se listó **{title}** en AniList (seasonYear)?',
                "answers": [str(int(year))],
            }
    except Exception:
        log.debug("trivia anilist: fallo al generar", exc_info=True)
        return None
    finally:
        if close_after:
            try:
                await session.close()
            except Exception:
                pass
    return None
