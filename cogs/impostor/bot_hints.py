# Pistas automáticas de bots de relleno (AAT-Bot).
from __future__ import annotations

import os
import random
import re
from typing import List

from .engine import ROLE_IMPOSTOR, ROLE_SOCIAL, GameState

_HINTS_BY_THEME: dict[str, List[str]] = {
    "personaje": [
        "pelo icónico", "trágico", "shonen", "villano", "protagonista",
        "sensei", "rival", "transformación", "pasado oscuro", "motivación",
    ],
    "anime": [
        "clásico", "popular", "isekai", "nostalgia", "temporada larga",
        "opening famoso", "fandom activo", "adaptación", "studio conocido",
    ],
    "objeto": [
        "kunai", "arma legendaria", "coleccionable", "símbolo", "accesorio",
        "artefacto", "premio", "herramienta", "recuerdo", "icono",
    ],
}

_IMPOSTOR_VAGUE = [
    "misterioso", "genérico", "ambiguo", "seguro", "común", "neutro",
]


def is_simple_bots_enabled() -> bool:
    raw = (os.getenv("IMPOSTOR_SIMPLE_BOTS", "1") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _theme_key(lobby: GameState) -> str:
    t = (lobby.secret_theme or "personaje").strip().lower()
    return t if t in _HINTS_BY_THEME else "personaje"


def _word_from_name(name: str, max_len: int = 12) -> str:
    parts = re.findall(r"[\wáéíóúñÁÉÍÓÚÑ]+", name, flags=re.UNICODE)
    skip = {"de", "del", "la", "el", "los", "las", "y", "the", "no"}
    for w in parts:
        wl = w.lower()
        if wl in skip or len(wl) < 3:
            continue
        if len(w) > max_len:
            return w[:max_len]
        return w
    return random.choice(_HINTS_BY_THEME["personaje"])


def pick_bot_hint(lobby: GameState, player: GameState.Player) -> str:
    """Genera una pista de 1–2 palabras para un bot."""
    theme = _theme_key(lobby)

    if is_simple_bots_enabled():
        pool = list(_HINTS_BY_THEME.get(theme, _HINTS_BY_THEME["personaje"]))
        if player.role == ROLE_IMPOSTOR:
            pool = pool + _IMPOSTOR_VAGUE
        return random.choice(pool)

    if player.role == ROLE_SOCIAL:
        if lobby.character_name:
            w = _word_from_name(lobby.character_name)
            if lobby.secret_detalle and random.random() < 0.35:
                d = _word_from_name(lobby.secret_detalle.split()[0] if lobby.secret_detalle else "")
                return f"{w} {d}"[:40].strip()
            return w
        return random.choice(_HINTS_BY_THEME[theme])

    # Impostor “inteligente”: vago pero coherente con temática
    return random.choice(_IMPOSTOR_VAGUE + _HINTS_BY_THEME[theme][:4])
