# Anti-salida inmediata (griefing) tras unirse o al empezar partida.
from __future__ import annotations

import time
from typing import Optional, Tuple

from .config import get_min_stay_seconds
from .engine import PHASE_END, GameState


def leave_block_reason(
    lobby: GameState,
    user_id: int,
    *,
    force: bool = False,
) -> Optional[str]:
    """
    Devuelve mensaje de error si no puede salir; None si puede salir.
    `force=True` omite la regla (cleanup automático del bot).
    """
    if force:
        return None
    if lobby.phase == PHASE_END:
        return None
    if user_id == lobby.host_id:
        return None

    stay = get_min_stay_seconds()
    if stay <= 0:
        return None

    player = lobby.get_player(user_id)
    if not player:
        return None

    now = time.time()

    if lobby.in_progress:
        started = getattr(lobby, "match_started_at_ts", 0) or 0
        if started > 0:
            elapsed = now - started
            if elapsed < stay:
                rem = max(1, int(stay - elapsed))
                return (
                    f"❌ No podés salir los primeros **{stay}s** de la partida "
                    f"(faltan ~**{rem}s**)."
                )
    else:
        joined = getattr(player, "joined_at_ts", 0) or 0
        if joined > 0:
            elapsed = now - joined
            if elapsed < stay:
                rem = max(1, int(stay - elapsed))
                return (
                    f"❌ Esperá **{rem}s** antes de salir del lobby "
                    f"(mínimo {stay}s tras unirte)."
                )

    return None
