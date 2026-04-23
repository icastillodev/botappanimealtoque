# Bono único (por versión) al reunir todos los tipos de blister configurados en .env.
from __future__ import annotations

import os
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from cogs.economia.db_manager import EconomiaDBManagerV2


def _parse_types() -> List[str]:
    raw = (os.getenv("BLISTER_COLLECTION_TYPES") or "").strip()
    if not raw:
        return []
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def try_grant_after_inventory_change(db: "EconomiaDBManagerV2", user_id: int) -> List[str]:
    """
    Lee .env y, si aplica, otorga puntos una vez por REWARD_BLISTER_COLLECTION_VERSION.
    Debe llamarse tras cualquier cambio en inventario de blisters.
    """
    pts = int(os.getenv("REWARD_BLISTER_COLLECTION_POINTS", "0") or 0)
    if pts <= 0:
        return []
    types = _parse_types()
    if not types:
        return []
    ver = max(1, int(os.getenv("REWARD_BLISTER_COLLECTION_VERSION", "1") or 1))
    min_single = max(1, int(os.getenv("REWARD_BLISTER_COLLECTION_MIN_SINGLE", "10") or 10))
    return db.apply_blister_collector_bonus(user_id, types, min_single, pts, ver)
