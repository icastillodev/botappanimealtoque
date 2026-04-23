# Embeds de ayuda para `?reclamar` (sin argumentos = guía paginada).
from __future__ import annotations

from typing import Any, Dict, List

import discord

from .reclamar_service import RECLAMO_TIPOS_AYUDA, build_reclaim_status_block


def build_reclamar_help_pages(db: Any, task_config: Dict[str, Any], user_id: int) -> List[List[discord.Embed]]:
    """Varias páginas (una por embed) para el paginador de `?reclamar`."""
    snap = build_reclaim_status_block(db, task_config, user_id)

    e1 = discord.Embed(
        title="?reclamar — Qué es (1/4)",
        description=(
            "Acá **no** se cobra solo por escribir `?reclamar`: abrís esta guía. Para cobrar de verdad usá el **botón verde**, "
            "un comando con tipo (`?reclamar diaria 1`…) o **`/aat-reclamar`**.\n\n"
            "**Qué podés cobrar**\n"
            "• **Iniciación** — hasta **3** premios distintos (Discord · perfil mínimo · perfil completo).\n"
            "• **Diario** — **2** premios (actividad+oráculo · trampa).\n"
            "• **Semanal** — **3** vías (base · Impostor · minijuegos), cada una con su premio.\n\n"
            "**Botones de abajo**\n"
            "• **Reclamar todo lo listo** = igual que `/aat-reclamar` vacío: intenta **cada** ☑ sin mezclar requisitos.\n"
            "• **Ver …** = embed de progreso en un mensaje nuevo."
        ),
        color=discord.Color.gold(),
    )
    e1.set_footer(text="Tip: ?progreso · ?progresoayuda — Paginá con Anterior / Siguiente")

    e2 = discord.Embed(
        title="?reclamar — Comandos y códigos (2/4)",
        description=(
            "**Prefijo `?reclamar`** — referencia = número después del tipo (si no ponés número en inicial/diaria, cobra **todo lo listo** de ese tipo).\n"
            "━━━━━━━━━━━━━━━━━━━━"
        ),
        color=discord.Color.dark_gold(),
    )
    e2.add_field(
        name="Iniciación (código global `1`)",
        value=(
            "`?reclamar inicial` — todo lo listo\n"
            "`?reclamar inicial 1` — solo Discord / comunidad\n"
            "`… inicial 2` — perfil mínimo\n"
            "`… inicial 3` — perfil al tope"
        ),
        inline=False,
    )
    e2.add_field(
        name="Diario (`2`)",
        value=(
            "`?reclamar diaria` — ambas partes si podés\n"
            "`?reclamar diaria 1` — mensajes + rx + oráculo\n"
            "`… diaria 2` — trampa"
        ),
        inline=False,
    )
    e2.add_field(
        name="Semanal (`3` · `4` · `5`)",
        value=(
            "`?reclamar semanal 1` — base · `2` — especial · `3` — minijuegos\n"
            "Aliases: `especial 1`, `minijuegos 1`, `weekly`…"
        ),
        inline=False,
    )
    e2.add_field(
        name="Slash",
        value="`/aat-reclamar` — tipo + referencia (mismas reglas que arriba).",
        inline=False,
    )
    e2.add_field(name="Ayuda compacta", value=RECLAMO_TIPOS_AYUDA[:1020], inline=False)

    e3 = discord.Embed(
        title="?reclamar — Tu estado (3/4)",
        description=(
            "**Leyenda del listado**\n"
            "✅ Ya cobraste esa parte · ☑ Podés cobrar ahora · ☐ Falta requisito\n\n"
            f"{snap}"
        ),
        color=discord.Color.blue(),
    )
    e3.set_footer(text="Esta lista se actualiza cada vez que abrís la guía o reclamás")

    e4 = discord.Embed(
        title="?reclamar — Progreso detallado (4/4)",
        description=(
            "**Comandos de detalle** (ticks y números)\n"
            "`?inicial` · `?diaria` / `?diario` · `?semanal` · `?progreso`\n\n"
            "**Slash (solo vos, ephemeral)**\n"
            "`/aat-progreso-iniciacion` · `…-diaria` · `…-semanal`\n\n"
            "**Discord viejo sin marcar**\n"
            "`/aat-verificar-antiguas` — escanea canales para iniciación.\n\n"
            "_Los botones **Ver …** mandan progreso en un **mensaje nuevo** en este canal._"
        ),
        color=discord.Color.dark_blue(),
    )
    e4.set_footer(text="Anime al Toque · Economía / tareas")
    return [[e1], [e2], [e3], [e4]]
