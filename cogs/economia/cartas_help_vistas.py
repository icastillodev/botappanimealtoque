# Mini-guía `?cartas` / `?cartas trampa` (paginador como `?reclamar`).
from __future__ import annotations

from typing import List

import discord


def build_cartas_help_pages(*, trampa_focus: bool = False) -> List[List[discord.Embed]]:
    """Páginas de embeds: visión general y, si aplica, foco en cartas trampa."""

    e_blisters = discord.Embed(
        title="?cartas (1/3) — Blisters y abrir",
        description=(
            "**Blisters** 🎁 son paquetes que ganás con **tareas** (`?reclamar` / `?progreso`) o **tienda**, "
            "según configure el staff.\n\n"
            "**Abrís todo junto** — cada blister abierto te da **3 cartas** al azar según el tipo de blister.\n"
            "• **`?abrir`** — prefijo (en canal permitido).\n"
            "• **`/aat-abrirblister`** — elegís tipo y cantidad (*slash*, suele ser más cómodo).\n\n"
            "_Si no tenés blisters: completá recompensas o mirá la tienda._"
        ),
        color=discord.Color.gold(),
    )
    e_blisters.set_footer(text="Tip: `?mi` muestra blisters junto con Toque points")

    e_coleccion = discord.Embed(
        title="?cartas (2/3) — Tu colección y el juego",
        description=(
            "**Ver qué tenés**\n"
            "• **`?miscartas`** — lista en el canal (**visible para todos**).\n"
            "• **`/aat-miscartas`** — lo mismo pero **solo vos** (*ephemeral*).\n\n"
            "**Catálogo**\n"
            "• **`?catalogo`** / **`/aat-catalogo`** — todas las cartas del servidor con numeración.\n\n"
            "**Dónde se juega más**\n"
            "Canal del bot o donde indique el staff — en **#general** solo van algunos comandos (`?comandos`)."
        ),
        color=discord.Color.blurple(),
    )

    e_usar = discord.Embed(
        title="?cartas (3/3) — Usar cartas",
        description=(
            "**Gastar una carta del inventario**\n"
            "`?usar <id> [@mención]` — el **id** sale en `?miscartas` / `/aat-miscartas`.\n\n"
            "**Cartas tipo Trampa** (resumen)\n"
            "• **Con @** — usás la carta **contra** alguien; suele contar para la **diaria** (bloque trampa).\n"
            "• **Sin mención** — uso **sin objetivo**; también puede contar para la diaria según reglas del bot.\n\n"
            "**Límite:** máximo **5 usos** de carta en **10 minutos** por usuario.\n\n"
            "_Más detalle en la guía del servidor: `?guia` · `?cartas trampa`_"
        ),
        color=discord.Color.dark_teal(),
    )

    e_trap_main = discord.Embed(
        title="?cartas trampa — Qué son y cómo usarlas",
        description=(
            "Las **Trampa** son cartas de **efecto en Discord**: las jugás con **`?usar`** "
            "(o **`/usar`** si está).\n\n"
            "**Formas válidas**\n"
            "1. **`?usar <id> @usuario`** — carta dirigida a alguien del server.\n"
            "2. **`?usar <id>`** — **sin** mención: trampa **sin objetivo** (una sola carta alcanza según regla diaria).\n\n"
            "**Diario (*daily*)**\n"
            "Una trampa bien usada puede tachar el requisito de **trampa del día** "
            "— mirá **`?diaria`** para el estado.\n\n"
            "**Blisters de tipo trampa**\n"
            "Al abrir un blister **trampa**, las **3** cartas salen del pool de trampas del servidor."
        ),
        color=discord.Color.dark_red(),
    )

    e_trap_extra = discord.Embed(
        title="?cartas trampa (2/2) — Recordatorios",
        description=(
            "**IDs** — Los números `#` los ves en `?miscartas` o `/aat-miscartas`.\n\n"
            "**Privacidad** — Si no querés mostrar tu cole en público, usá **`/aat-miscartas`**.\n\n"
            "**Abrir más cartas** — `?abrir` gasta **todos** los blisters que tengás de una vez; "
            "`/aat-abrirblister` permite elegir.\n\n"
            "**¿Sin cartas?** — Reclamá recompensas o preguntá en la guía fija del servidor (`?guia`)."
        ),
        color=discord.Color.red(),
    )

    if trampa_focus:
        return [[e_trap_main], [e_trap_extra]]

    return [[e_blisters], [e_coleccion], [e_usar]]
