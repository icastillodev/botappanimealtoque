# Votos de revancha post-partida.
from __future__ import annotations

import math

from .config import get_rematch_vote_percent
from .engine import GameState


def rematch_votes_needed(lobby: GameState) -> int:
    """Humanos que deben votar según `IMPOSTOR_REMATCH_VOTE_PERCENT` (default 50%)."""
    n = len(lobby.human_players)
    if n <= 0:
        return 1
    pct = get_rematch_vote_percent()
    return max(1, math.ceil(n * pct / 100))


def rematch_vote_status(lobby: GameState) -> str:
    needed = rematch_votes_needed(lobby)
    have = len(getattr(lobby, "rematch_votes", set()) or set())
    return f"**{have}/{needed}** jugadores quieren revancha"
