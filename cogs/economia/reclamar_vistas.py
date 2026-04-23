# Embeds de ayuda para `?reclamar` (sin argumentos = guía paginada).
from __future__ import annotations

from typing import Any, Dict, List

import discord

from .reclamar_service import RECLAMO_TIPOS_AYUDA, build_reclaim_status_block


def build_reclamar_help_pages(db: Any, task_config: Dict[str, Any], user_id: int) -> List[List[discord.Embed]]:
    """Varias páginas (una por embed) para el paginador de `?reclamar`."""
    snap = build_reclaim_status_block(db, task_config, user_id)

    e1 = discord.Embed(
        title="?reclamar — Qué es y cómo usarlo (1/4)",
        description=(
            "**Reclamar** = cobrar en el bot las **Toque points** y **blisters** que ganaste cuando "
            "completaste tareas (iniciación, diario, semanal base, especial Impostor, minijuegos).\n\n"
            "**Este menú** (solo `?reclamar` sin nada más) es una **guía con páginas**: usá **Anterior** / **Siguiente** "
            "y los botones de abajo.\n\n"
            "• **Reclamar todo lo listo** — intenta cobrar **todo** lo que ya podés (igual que antes con un solo comando).\n"
            "• **Ver inicial / diario / semanal / especial** — te manda el **detalle de progreso** en un mensaje nuevo "
            "(para ver qué falta sin salir del canal).\n\n"
            "**Atajo:** si ya sabés qué querés cobrar, podés escribir directo "
            "`?reclamar diaria` · `?reclamar daily` · `?reclamar semanal` · `?reclamar especial`… "
            "(se explica en la página 2)."
        ),
        color=discord.Color.gold(),
    )
    e2 = discord.Embed(
        title="?reclamar — Prefijo y nombres (2/4)",
        description=(
            "**Sin argumento** = abre **esta guía** (no cobra solo al escribir; usá el botón verde o un tipo abajo).\n\n"
            "**Con un solo tipo** = intenta cobrar **solo** esa recompensa (si está lista):\n"
            f"{RECLAMO_TIPOS_AYUDA}\n\n"
            "**Nombres internos** (los mismos que en `/aat-reclamar`):\n"
            "`inicial` · `diaria` · `semanal` · `semanal_especial` · `semanal_minijuegos`\n\n"
            "_Ejemplo:_ `?reclamar diario` = `?reclamar diaria` = `?reclamar daily`."
        ),
        color=discord.Color.dark_gold(),
    )
    e3 = discord.Embed(
        title="?reclamar — Tu estado ahora (3/4)",
        description=(
            "**Leyenda:**\n"
            "• ✅ = ya cobraste esa parte.\n"
            "• ☑ = **listo** para reclamar (usá el botón o `?reclamar` + tipo).\n"
            "• ☐ = todavía falta algo.\n\n"
            f"{snap}"
        ),
        color=discord.Color.blue(),
    )
    e4 = discord.Embed(
        title="?reclamar — Ver progreso y slash (4/4)",
        description=(
            "**Ver el detalle** (ticks, números, qué falta):\n"
            "• `?inicial` · `?diaria` / `?diario` · `?semanal` · `?progreso`\n"
            "• `/aat-progreso-iniciacion` · `/aat-progreso-diaria` · `/aat-progreso-semanal` (privado / ephemeral)\n\n"
            "En **diario** y **semanal** el mensaje con páginas también trae **botones Reclamar** para cobrar desde ahí.\n\n"
            "**Iniciación:** si el bot no marcó Discord pero vos ya lo hiciste antes, "
            "usá **`/aat-verificar-antiguas`**.\n\n"
            "_Los botones **Ver …** de abajo envían el progreso en un **mensaje nuevo** en este canal._"
        ),
        color=discord.Color.dark_blue(),
    )
    return [[e1], [e2], [e3], [e4]]
