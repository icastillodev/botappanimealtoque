# Cupos de lobby (sin dependencias de discord para evitar imports circulares).
from __future__ import annotations

import os

UNLIMITED_SLOTS = 99


def _env_unlimited(raw: str) -> bool:
    return (raw or "").strip().lower() in ("", "0", "none", "unlimited", "sinlimite", "inf", "sin_limite")


def parse_max_players_env() -> int:
    raw = (os.getenv("IMPOSTOR_MAX_PLAYERS", "50") or "").strip()
    if _env_unlimited(raw):
        return UNLIMITED_SLOTS
    try:
        v = int(raw)
        return UNLIMITED_SLOTS if v <= 0 else v
    except ValueError:
        return 50


def format_slots_label(current: int, maximum: int) -> str:
    if maximum >= UNLIMITED_SLOTS:
        return f"{current}/∞"
    return f"{current}/{maximum}"
