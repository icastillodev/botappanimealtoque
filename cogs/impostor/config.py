# Variables de entorno compartidas del modo Impostor.
from __future__ import annotations

import os

# Mínimo absoluto del juego (1 impostor + 2 sociales).
IMPOSTOR_ABSOLUTE_MIN_PLAYERS = 3


def get_min_impo_players() -> int:
    """Mínimo de jugadores para iniciar (`IMPOSTOR_MIN_PLAYERS`, piso 3)."""
    try:
        v = int(os.getenv("IMPOSTOR_MIN_PLAYERS", "4"))
    except ValueError:
        v = 4
    return max(IMPOSTOR_ABSOLUTE_MIN_PLAYERS, v)


def get_min_stay_seconds() -> int:
    """Segundos mínimos antes de poder salir (0 = desactivado)."""
    try:
        return max(0, int(os.getenv("IMPOSTOR_MIN_STAY_SECONDS", "30")))
    except ValueError:
        return 30


def get_rematch_window_seconds() -> int:
    try:
        return max(10, int(os.getenv("IMPOSTOR_REMATCH_WINDOW_SECONDS", "60")))
    except ValueError:
        return 60


def get_rematch_vote_percent() -> int:
    """Porcentaje de humanos que deben votar revancha (1–100). Default 50 = mayoría."""
    try:
        return max(1, min(100, int(os.getenv("IMPOSTOR_REMATCH_VOTE_PERCENT", "50"))))
    except ValueError:
        return 50
