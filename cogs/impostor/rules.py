# Reglas de balance: cantidad de impostores y condiciones de victoria.
from __future__ import annotations

from typing import Optional, Tuple

from .engine import ROLE_IMPOSTOR, ROLE_SOCIAL, GameState


def max_impostors_for_players(player_count: int) -> int:
    """
    1 impostor base; +1 cada ~3 jugadores (4→1, 6→2, 9→3).
    Siempre deben quedar al menos 2 sociales posibles.
    """
    n = max(0, int(player_count))
    if n < 4:
        return 1
    return max(1, min(n - 2, n // 3))


def clamp_impostor_count(lobby: GameState) -> int:
    mx = max_impostors_for_players(lobby.all_players_count)
    lobby.impostor_count = max(1, min(int(lobby.impostor_count or 1), mx))
    return lobby.impostor_count


def alive_impostor_players(lobby: GameState):
    return [p for p in lobby.alive_players if p.user_id in lobby.impostor_ids]


def alive_social_players(lobby: GameState):
    return [p for p in lobby.alive_players if p.user_id not in lobby.impostor_ids]


def check_round_start_victory(lobby: GameState) -> Optional[Tuple[str, str]]:
    """
    Devuelve (ROLE_GANADOR, razón) si la partida debe terminar antes de la ronda, o None.
    """
    imps = alive_impostor_players(lobby)
    socs = alive_social_players(lobby)

    if not imps:
        return ROLE_SOCIAL, "Todos los impostores fueron eliminados."

    if len(socs) <= 2:
        n_imp = len(imps)
        return (
            ROLE_IMPOSTOR,
            f"Quedan **{n_imp}** impostor(es) y solo **{len(socs)}** social(es) vivos.",
        )

    if len(lobby.alive_players) == len(imps) and imps:
        return ROLE_IMPOSTOR, "Solo quedan impostores vivos."

    return None
