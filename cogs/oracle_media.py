# Recomendaciones por género/tag, fichas anime/manga y datos vía **AniList** (GraphQL público).
# Listas curadas = fallback si la API falla. Definiciones → Wikipedia es (oracle_wiki).
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

log = logging.getLogger(__name__)

_ANILIST_GQL = "https://graphql.anilist.co"
# Evita ráfagas: mínimo espacio entre POST (por si muchos usuarios preguntan a la vez).
_anilist_last_post: float = 0.0
_ANILIST_MIN_INTERVAL = 0.35


def anilist_enabled() -> bool:
    v = (os.getenv("ORACLE_ANILIST") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _anilist_ua() -> str:
    u = (os.getenv("ORACLE_ANILIST_UA") or "").strip()
    return u or "AnimeAlToqueOracle/1.0 (Discord bot) Python/aiohttp — AniList GraphQL"


# Pistas → listas locales si AniList no responde.
_ORACLE_ANIME_POOLS: Dict[str, Tuple[str, ...]] = {
    "isekai": (
        "Re:Zero − Starting Life in Another World",
        "Mushoku Tensei: Jobless Reincarnation",
        "That Time I Got Reincarnated as a Slime",
        "KonoSuba: God's Blessing on This Wonderful World!",
        "Overlord",
        "Saga of Tanya the Evil",
        "No Game No Life",
        "The Rising of the Shield Hero",
        "Ascendance of a Bookworm",
        "So I'm a Spider, So What?",
        "The Eminence in Shadow",
    ),
    "romance": (
        "Toradora!",
        "Your Name.",
        "Horimiya",
        "Kaguya-sama: Love is War",
        "Fruits Basket (2019)",
        "Clannad",
        "Oregairu",
        "Tsuki ga Kirei",
        "Wotakoi: Love is Hard for Otaku",
    ),
    "shonen": (
        "Hunter x Hunter (2011)",
        "My Hero Academia",
        "Jujutsu Kaisen",
        "Demon Slayer: Kimetsu no Yaiba",
        "One Piece",
        "Attack on Titan",
        "Fullmetal Alchemist: Brotherhood",
        "Haikyu!!",
        "Mob Psycho 100",
    ),
    "seinen": (
        "Vinland Saga",
        "Berserk (1997)",
        "Monster",
        "Parasyte: The Maxim",
        "Psycho-Pass",
        "Steins;Gate",
        "Ghost in the Shell: Stand Alone Complex",
    ),
    "mecha": (
        "Neon Genesis Evangelion",
        "Code Geass: Lelouch of the Rebellion",
        "Gurren Lagann",
        "Mobile Suit Gundam: The Witch from Mercury",
        "86: Eighty-Six",
    ),
    "slice of life": (
        "K-On!",
        "Laid-Back Camp",
        "Non Non Biyori",
        "Barakamon",
        "Aria the Animation",
        "Nichijou",
    ),
    "comedia": (
        "Grand Blue",
        "Nichijou",
        "KonoSuba: God's Blessing on This Wonderful World!",
        "Saiki K.",
        "Spy x Family",
    ),
    "fantasia": (
        "Made in Abyss",
        "Magi: The Labyrinth of Magic",
        "Ranking of Kings",
        "The Ancient Magus' Bride",
    ),
    "terror": (
        "Another",
        "Parasyte: The Maxim",
        "The Promised Neverland (temporada 1)",
        "Monster",
    ),
    "deportes": (
        "Haikyu!!",
        "Blue Lock",
        "Run with the Wind",
        "Ping Pong the Animation",
    ),
}

_HINT_TO_POOL: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("isekai", ("isekai", "iseskai", "reencarn", "otro mundo", "truck")),
    ("romance", ("romance", "romántic", "romantic", "amor", "pareja")),
    ("shonen", ("shonen", "shōnen", "shounen", "batallas", "poderes")),
    ("seinen", ("seinen", "adulto", "maduro")),
    ("mecha", ("mecha", "robot", "gundam", "eva")),
    ("slice of life", ("slice", "iyashikei", "cotidian", "escuela relax", "vida diaria")),
    ("comedia", ("comedia", "comedy", "gracioso", "humor")),
    ("fantasia", ("fantas", "magia", "medieval")),
    ("terror", ("terror", "horror", "suspenso", "miedo")),
    ("deportes", ("deport", "fútbol", "futbol", "voley", "básquet", "basquet")),
)

# Filtros AniList: genre_in / tag_in (nombres exactos de su esquema).
_ANILIST_BROWSE: Dict[str, Tuple[List[str], List[str]]] = {
    "isekai": ([], ["Isekai"]),
    "romance": (["Romance"], []),
    "shonen": (["Shounen"], []),
    "seinen": (["Seinen"], []),
    "mecha": (["Mecha"], []),
    "slice of life": (["Slice of Life"], []),
    "comedia": (["Comedy"], []),
    "fantasia": (["Fantasy"], []),
    "terror": (["Horror"], []),
    "deportes": (["Sports"], []),
}

_DEFAULT_ANIME_POOL: Tuple[str, ...] = (
    "Fullmetal Alchemist: Brotherhood",
    "Steins;Gate",
    "Mob Psycho 100",
    "Spy x Family",
    "Violet Evergarden",
    "Hunter x Hunter (2011)",
    "One Punch Man",
    "Made in Abyss",
    "Death Note",
    "Jujutsu Kaisen",
    "Sousou no Frieren",
    "Oshi no Ko",
    "Bocchi the Rock!",
    "March Comes in Like a Lion",
)


def _detect_hint_pools(q: str) -> List[str]:
    low = (q or "").lower()
    found: List[str] = []
    for pool_key, needles in _HINT_TO_POOL:
        if any(n in low for n in needles):
            found.append(pool_key)
    return found


def _curated_recommendation_line(q: str) -> str:
    pools = _detect_hint_pools(q)
    if pools:
        key = random.choice(pools)
        titles = _ORACLE_ANIME_POOLS.get(key, _DEFAULT_ANIME_POOL)
        pick = random.choice(titles)
        tag = key.replace(" ", "·")
        intro = random.choice(
            [
                f"Para **{tag}** (fallback local; AniList no respondió):",
                f"Onda **{tag}** — lista interna del bot:",
                f"Pick **{tag}** desde el cofre local:",
            ]
        )
        return f"{intro} **{pick}**.\n_Revisá en **AniList** si querés más títulos._"
    pick = random.choice(_DEFAULT_ANIME_POOL)
    return (
        f"Sin género claro en la frase, pick general: **{pick}**.\n"
        f"_Tip: decí **isekai**, **romance**, **shonen**, etc._"
    )


async def _anilist_post(query: str, variables: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if not anilist_enabled():
        return None
    global _anilist_last_post
    now = time.monotonic()
    gap = _ANILIST_MIN_INTERVAL - (now - _anilist_last_post)
    if gap > 0:
        await asyncio.sleep(gap)
    _anilist_last_post = time.monotonic()

    payload = {"query": query, "variables": variables or {}}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": _anilist_ua(),
    }
    timeout = aiohttp.ClientTimeout(total=14.0, connect=7.0, sock_read=10.0)
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.post(_ANILIST_GQL, json=payload) as resp:
                if resp.status != 200:
                    log.debug("oracle_media: AniList HTTP %s", resp.status)
                    return None
                data = await resp.json(content_type=None)
    except aiohttp.ClientError:
        log.debug("oracle_media: AniList red", exc_info=True)
        return None
    except Exception:
        log.debug("oracle_media: AniList error", exc_info=True)
        return None

    if not isinstance(data, dict):
        return None
    if data.get("errors"):
        log.debug("oracle_media: AniList errors=%s", data.get("errors")[:1])
        return None
    return data.get("data")


def _pick_title_anilist(m: Dict[str, Any]) -> str:
    t = m.get("title") or {}
    if isinstance(t, dict):
        for k in ("english", "romaji", "native"):
            v = t.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return "?"


def _fmt_date(d: Any) -> str:
    if not isinstance(d, dict):
        return "?"
    y, mo, da = d.get("year"), d.get("month"), d.get("day")
    parts = [str(x) for x in (y, mo, da) if x is not None]
    return "-".join(parts) if parts else "?"


def _strip_desc(s: str, n: int = 300) -> str:
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = " ".join(s.split())
    if len(s) > n:
        s = s[: n - 1].rsplit(" ", 1)[0] + "…"
    return s


def _format_anilist_media(m: Dict[str, Any], *, kind: str) -> str:
    title = _pick_title_anilist(m)
    status = (m.get("status") or "").replace("_", " ")
    fmt = (m.get("format") or "").replace("_", " ")
    eps = m.get("episodes")
    ch = m.get("chapters")
    sd = _fmt_date(m.get("startDate"))
    ed = _fmt_date(m.get("endDate"))
    genres = m.get("genres") or []
    gtxt = ", ".join(genres[:6]) if isinstance(genres, list) else ""
    studios = ((m.get("studios") or {}).get("nodes")) or []
    st = ", ".join(
        x.get("name", "") for x in studios[:4] if isinstance(x, dict) and x.get("name")
    )
    na = m.get("nextAiringEpisode")
    next_line = ""
    if isinstance(na, dict) and na.get("episode") is not None:
        ep = na.get("episode")
        tua = na.get("timeUntilAiring")
        if isinstance(tua, int):
            h = max(0, tua // 3600)
            next_line = f"Próximo cap. en emisión: **ep. {ep}** (~{h}h según AniList).\n"
    desc = _strip_desc((m.get("description") or "")[:800], 280)
    url = m.get("siteUrl") or ""
    head = f"**{title}** ({kind})"
    lines = [
        head,
        f"Estado: **{status}** · Formato: **{fmt}**",
    ]
    if kind == "manga":
        lines.append(f"Capítulos (conocidos): **{ch if ch is not None else '?'}** · Inicio: **{sd}**")
    else:
        lines.append(f"Episodios: **{eps if eps is not None else '?'}** · Emisión: **{sd}** → **{ed}**")
    if next_line and kind == "anime":
        lines.append(next_line.rstrip())
    if gtxt:
        lines.append(f"Géneros: **{gtxt}**")
    if st:
        lines.append(f"Estudios (main): **{st}**")
    if desc:
        lines.append(desc)
    if url:
        lines.append(f"AniList: {url}")
    lines.append("_Datos vía **AniList** (público); verificá fechas en la ficha._")
    return "\n".join(lines)


async def _anilist_search_first(search: str, media_type: str) -> Optional[str]:
    q = (search or "").strip()
    if len(q) < 2:
        return None
    gql = """
    query ($search: String, $type: MediaType) {
      Page(perPage: 5) {
        media(search: $search, type: $type, sort: SEARCH_MATCH) {
          title { romaji english native }
          format
          status
          episodes
          chapters
          startDate { year month day }
          endDate { year month day }
          nextAiringEpisode { airingAt timeUntilAiring episode }
          studios(isMain: true) { nodes { name } }
          description(asHtml: true)
          siteUrl
          genres
        }
      }
    }
    """
    mt = "MANGA" if media_type.lower() == "manga" else "ANIME"
    data = await _anilist_post(gql, {"search": q, "type": mt})
    if not data:
        return None
    media = (((data.get("Page") or {}).get("media")) or [])
    if not media or not isinstance(media[0], dict):
        return None
    kind = "manga" if mt == "MANGA" else "anime"
    return _format_anilist_media(media[0], kind=kind)


async def _anilist_browse_random_titles(pool_key: str, count: int = 24) -> List[Dict[str, Any]]:
    genres, tags = _ANILIST_BROWSE.get(pool_key, ([], []))
    page = random.randint(1, 5)
    per_page = min(50, max(10, count))

    if genres and tags:
        gql = """
        query ($page: Int, $perPage: Int, $genres: [String], $tags: [String]) {
          Page(page: $page, perPage: $perPage) {
            media(type: ANIME, genre_in: $genres, tag_in: $tags, sort: POPULARITY_DESC, isAdult: false) {
              title { romaji english }
              siteUrl
            }
          }
        }
        """
        variables: Dict[str, Any] = {
            "page": page,
            "perPage": per_page,
            "genres": genres,
            "tags": tags,
        }
    elif tags:
        gql = """
        query ($page: Int, $perPage: Int, $tags: [String]) {
          Page(page: $page, perPage: $perPage) {
            media(type: ANIME, tag_in: $tags, sort: POPULARITY_DESC, isAdult: false) {
              title { romaji english }
              siteUrl
            }
          }
        }
        """
        variables = {"page": page, "perPage": per_page, "tags": tags}
    elif genres:
        gql = """
        query ($page: Int, $perPage: Int, $genres: [String]) {
          Page(page: $page, perPage: $perPage) {
            media(type: ANIME, genre_in: $genres, sort: POPULARITY_DESC, isAdult: false) {
              title { romaji english }
              siteUrl
            }
          }
        }
        """
        variables = {"page": page, "perPage": per_page, "genres": genres}
    else:
        return []

    data = await _anilist_post(gql, variables)
    if not data:
        return []
    return (((data.get("Page") or {}).get("media")) or []) or []


async def _anilist_recommendation_body(q: str) -> str:
    pools = _detect_hint_pools(q)
    if not pools:
        # Sin pista: búsqueda popular genérica
        data = await _anilist_post(
            """
            query ($page: Int) {
              Page(page: $page, perPage: 25) {
                media(type: ANIME, sort: POPULARITY_DESC, isAdult: false) {
                  title { romaji english }
                  siteUrl
                }
              }
            }
            """,
            {"page": random.randint(1, 3)},
        )
        items = (((data or {}).get("Page") or {}).get("media")) or [] if data else []
        if items and isinstance(items[0], dict):
            pick = random.choice(items[:20])
            t = _pick_title_anilist(pick)
            u = pick.get("siteUrl") or ""
            return (
                f"Pick popular en **AniList**: **{t}**.\n"
                f"{u and (u + chr(10)) or ''}"
                f"_Sin género en tu mensaje; decí **isekai**, **romance**, etc. para afinar._"
            )
        return _curated_recommendation_line(q)

    key = random.choice(pools)
    items = await _anilist_browse_random_titles(key)
    usable = [x for x in items if isinstance(x, dict) and _pick_title_anilist(x) != "?"]
    if usable:
        pick = random.choice(usable)
        t = _pick_title_anilist(pick)
        u = pick.get("siteUrl") or ""
        extra = await _anilist_second_pick_same_filter(key, exclude_title=t)
        body = (
            f"Según **AniList** (género/tag **{key}**): **{t}**.\n"
            f"{u and (u + chr(10)) or ''}"
        )
        if extra:
            body += f"{extra}\n"
        body += "_Listas y fechas pueden actualizarse en la web._"
        return body
    return _curated_recommendation_line(q)


async def _anilist_second_pick_same_filter(pool_key: str, *, exclude_title: str) -> str:
    items = await _anilist_browse_random_titles(pool_key)
    cand = [
        _pick_title_anilist(x)
        for x in items
        if isinstance(x, dict) and _pick_title_anilist(x) not in ("?", exclude_title)
    ]
    if not cand:
        return ""
    t2 = random.choice(cand[:12])
    return f"Otra opción del mismo bloque: **{t2}**."


_MEDIA_INFO_TRIG = re.compile(
    r"(?is)\b(cuándo|cuando)\s+(sale|salen|empiez|inici|vuelv|retorn|será|sera|dan)\b|"
    r"\bestreno\b|\bemit(en|ir|ían|ia)\b|\bemisión\b|\bepisodios?\b|\bcap[ií]tulos?\b|"
    r"\bfecha\s+(de\s+)?(salida|estreno)\b|\bhorario\b|\bqué\s+d[ií]a\b|"
    r"\bde\s+qu[eé]\s+trata\b|\bsinopsis\b|\binformaci[oó]n\s+(sobre|de)\b|\bdatos\s+de\b|"
    r"\bestudio\s+(que\s+)?(anim[oó]|hizo)|\bproductora\b|\bestudio\s+de\b|"
    r"\bqui[eé]n\s+(lo\s+)?anim[oó]\b|\banime\s+de\s+\w+\s+(studios?|animation)\b"
)


def _is_anime_recommendation_text(q: str) -> bool:
    s = (q or "").strip()
    if len(s) < 6:
        return False
    if re.search(
        r"(?is)\brecomienda(?:me|nos)?(\s+un)?\s+anime\b|"
        r"\brecomiend(?:ame|anos|an)\b.*\banime\b|"
        r"\brecomend(?:ame|á|a|arme)\b.*\banime\b|"
        r"\bsuger(?:ime|í|i)\b.*\banime\b|"
        r"\bqu[eé]\s+anime\s+(ver|mirar|empezar|poner)\b|"
        r"\banime\s+(para\s+)?ver\b|"
        r"\bpon(?:eme|me|é)\s+un\s+anime\b|"
        r"\bpas(?:a|á)(?:me|nos)?\s+un\s+anime\b|"
        r"\btir(?:a|á)(?:me|nos)?\s+un\s+anime\b|"
        r"\bdame\s+un\s+anime\b",
        s,
    ):
        return True
    if re.search(r"\brecomienda\b", s) and re.search(r"\banime\b", s):
        return True
    if re.search(r"\brecomend\w*", s) and re.search(r"\banime\b", s):
        return True
    return False


def _is_media_info_question(q: str) -> bool:
    s = (q or "").strip()
    low = s.lower()
    if len(s) < 10:
        return False
    if _is_anime_recommendation_text(s):
        return False
    if re.search(r"\brecomend", low):
        return False
    if re.search(r"(?is)\b(anime|manga)\s+de\s+\S+", s) and len(s) >= 12:
        return True
    if not _MEDIA_INFO_TRIG.search(s):
        return False
    if re.search(r"(?is)\banime\b|\bmanga\b|\bmanhwa\b|\bova\b|\bserie\b", s):
        return True
    return len(s) >= 14


_MEDIA_DEF_TRIG = re.compile(
    r"(?is)^(.*\b)?(qu[eé]\s+es|qu[eé]\s+significa|defin[ií](?:ción|ci[oó]n)|"
    r"expl[ií]came\s+qu[eé]\s+es)\b"
)


def _is_media_concept_definition(q: str) -> bool:
    s = (q or "").strip()
    if len(s) < 8 or len(s) > 220:
        return False
    if not _MEDIA_DEF_TRIG.search(s):
        return False
    low = s.lower()
    if re.search(
        r"(?is)\b(isekai|sh[oō]nen|shonen|seinen|josei|mecha|slice|"
        r"rom[aá]nce|fantas|manga|manhwa|manhua|anime|otaku|waifu|"
        r"spoilers?|filler|arc)\b",
        low,
    ):
        return True
    return False


def _strip_media_query_boilerplate(q: str) -> str:
    s = " ".join((q or "").split())
    s = re.sub(
        r"(?is)\b(podés|puedes|podria|podrías|decime|dime|che|"
        r"cuándo|cuando|sale|salen|empieza|empiezan|del|el|la|los|las|un|una|"
        r"anime|manga|serie|temporada|capítulo|capitulo|sobre|de|datos|información|"
        r"emiten|emisión|estreno|sinopsis|trata|estudio|productora|animó|animo)\b",
        " ",
        s,
    )
    s = re.sub(r"[^\w\sáéíóúüñÁÉÍÓÚÜÑ0-9':-]", " ", s)
    s = " ".join(s.split()).strip("¿?.,;:! ")
    return s[:120] if s else ""


async def oracle_media_open_reply_async(pq: str) -> Optional[str]:
    """
    Recomendación (AniList browse), ficha (AniList search), definición (Wikipedia).
    """
    s = (pq or "").strip()
    if not s:
        return None

    if _is_anime_recommendation_text(s):
        return await _anilist_recommendation_body(s)

    if _is_media_info_question(s):
        qsearch = _strip_media_query_boilerplate(s)
        if len(qsearch) < 2:
            return None
        is_manga = bool(re.search(r"(?is)\bmanga\b|\bmanhwa\b|\bmanhua\b", s))
        card = await _anilist_search_first(qsearch, "manga" if is_manga else "anime")
        if card:
            return card
        return (
            "No encontré esa obra en **AniList** con esa búsqueda. "
            "Probá **romaji** o título **inglés**, o pasá el nombre más corto. "
            "También podés abrir la ficha en anilist.co y pegar el título exacto."
        )

    if _is_media_concept_definition(s):
        term = _strip_media_query_boilerplate(s)
        if len(term) < 2:
            term = s
        wiki_q = f"{term} anime manga definición"
        try:
            from cogs.oracle_wiki import wikipedia_es_snippet

            w = await wikipedia_es_snippet(wiki_q, max_chars=380)
            if w:
                return w
        except Exception:
            log.debug("oracle_media: wiki definición falló", exc_info=True)
        return (
            f"No pude traer definición de **{term[:80]}** desde Wikipedia. "
            "Buscá en **AniList** / wiki o usá **Ollama**."
        )

    return None
