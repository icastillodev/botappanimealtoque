# Contenido del mensaje fijo del canal guía (BOT_GUIA_CHANNEL_ID).
from __future__ import annotations

from typing import Any, Dict, List, Optional

import discord


def _fmt_pts(n: int) -> str:
    return f"**{int(n)}** pts"


def _linea_precio(nombre: str, precio: int) -> Optional[str]:
    if precio and int(precio) > 0:
        return f"• {nombre}: {_fmt_pts(precio)}"
    return None


def build_comandos_ref_embeds() -> List[discord.Embed]:
    """Lista compacta de todos los comandos ! y / (para canal guía y `!ayuda`)."""
    r0 = discord.Embed(
        title="📋 Comandos con prefijo !",
        description=(
            "En **#general** solo funcionan los `!` que el bot permite ahí (lista del staff). "
            "En el **canal de comandos del bot** (`BOT_CHANNEL_ID`) podés usar el resto de `!` sin que los borre el filtro.\n\n"
            "**Economía y cartas**\n"
            "• `!puntos` — tus puntos · `!inventario` — puntos, pins y blisters\n"
            "• `!top` · `!rank` · `!ranking` — top 5 del servidor\n"
            "• `!reclamar` — cobrar recompensas listas\n"
            "• `!progreso` — resumen iniciación + diaria + semanal\n"
            "• `!diaria` · `!daily` · `!semanal` · `!weekly` · `!inicial` · `!starter` · `!iniciacion` — ver qué falta\n"
            "• `!abrir` — abrir blister (público en el canal)\n"
            "• `!miscartas` — lista de cartas (**visible para todos** en ese canal)\n"
            "• `!catalogo` — todas las cartas del juego\n"
            "• `!usar` · `!usarcarta` — usar carta trampa (`!usar <id> [@alguien]`)\n\n"
            "**Resúmenes y guía en el chat**\n"
            "• `!comandos` · `!aat` · `!cmds` · `!cmd` · `!ayudabot` — resumen corto\n"
            "• `!ayuda` · `!guia` — **esta guía completa** en varios embeds\n"
            "• `!canjes` · `!tienda` · `!recompensas` — embed de tienda y canjes\n"
            "• `!ganarpuntos` · `!comoganar` — cómo ganar puntos + reclamar\n"
            "• `!roll` — dado casual entre dos números\n\n"
            "**Impostor**\n"
            "• `!impostor` · `!buscoimpostor` · `!busco` · `!lobbys` · `!cartelera` — aviso de busca / cartelera\n\n"
            "**Oráculo (diaria)**\n"
            "• `!pregunta` · `!consulta` · `!8ball` · `!bola` · `!oraculo` — pregunta sí/no (también @mención al bot)\n\n"
            "**Trivia (pregunta en #general)**\n"
            "• `!respuestapregunta` · `!triviaresp` · `!rtrivia` + tu respuesta\n\n"
            "**Top anime**\n"
            "• `!animetop` · `!animetop @usuario`"
        ),
        color=discord.Color.light_grey(),
    )

    r1 = discord.Embed(
        title="⚙️ Slash — economía, cartas y tienda",
        description=(
            "**Puntos e inventario:** `/aat_puntos` · `/aat_inventario`\n"
            "**Reclamar y progreso:** `/aat_reclamar` · `/aat_progreso_iniciacion` · `/aat_progreso_diaria` · `/aat_progreso_semanal`\n"
            "**Ranking:** `/aat_ranking_top`\n"
            "**Cartas:** `/aat_abrirblister` · `/aat_miscartas` · `/aat_catalogo` · `/vercarta` · `/usar`\n"
            "**Tienda:** `/aat_tienda_ver` · `/aat_tienda_canjear` · `/aat_tienda_fijar` · `/aat_tienda_pin_general` · "
            "`/aat_tienda_encuesta` · `/aat_tienda_rol_temporal`\n"
            "**Público en el canal:** `/aat_canjes` · `/aat_ganar_puntos`\n"
            "**Guía interactiva (solo vos):** `/aat_ayuda`\n"
            "**Minijuegos y encuesta del servidor:** `/aat_roll` · `/aat_roll_retar` · `/aat_roll_aceptar` · "
            "`/aat_voto_semanal`\n"
            "**Duelos con cartas** (si el staff los activa en `.env`): `/aat_duelo_retar` · `/aat_duelo_aceptar`"
        ),
        color=discord.Color.blue(),
    )

    r2 = discord.Embed(
        title="⚙️ Slash — perfil, top anime y oráculo",
        description=(
            "**Top anime (30 posiciones):** `/aat_anime_top_ver` · `/aat_anime_top_set` · `/aat_anime_top_quitar` · `/aat_anime_top_guia`\n"
            "**Wishlist / odiados / personajes:** `/aat_wishlist_ver` · `/aat_wishlist_set` · `/aat_wishlist_quitar` · "
            "`/aat_hated_ver` · `/aat_hated_set` · `/aat_hated_quitar` · `/aat_chars_ver` · `/aat_chars_set` · `/aat_chars_quitar`\n"
            "**Oráculo:** `/aat_consulta`"
        ),
        color=discord.Color.teal(),
    )

    r3 = discord.Embed(
        title="⚙️ Slash — Impostor, VERSUS y votaciones",
        description=(
            "**Impostor:** `/crearsimpostor` · `/entrar` · `/leave` · `/salir` · `/invitar` · `/ready` · `/abrirlobby` · `/cerrarlobby` · `/helpimpostor`\n"
            "**VERSUS semanal:** `/aat_versus_votos` — quién votó en la encuesta actual\n\n"
            "**Votaciones del servidor**\n"
            "• `/crear_votacion` — encuesta simple (usuario)\n"
            "• `/mis_resultados` — resultados de una votación que creaste\n"
            "• `/ayudaencuesta` — ayuda interactiva de votación\n"
            "• **Solo staff:** `/crear_votacionadmin` · `/modificarvotacion` · `/finalizarvotacion` · `/borrarvotacion` · "
            "`/agregaropcion` · `/quitaropcion` · `/resultados`"
        ),
        color=discord.Color.dark_purple(),
    )

    return [r0, r1, r2, r3]


def build_guia_embeds(bot: Any) -> List[discord.Embed]:
    """Arma hasta 10 embeds (límite Discord) con resumen de economía, tienda y extras."""
    tc: Dict[str, Any] = bot.task_config or {}
    sc: Dict[str, Any] = bot.shop_config or {}
    rw = tc.get("rewards") or {}

    e0 = discord.Embed(
        title="📌 Guía del bot — Anime al Toque",
        description=(
            "Este **canal** es solo para esta **guía fija** (comandos, reclamos, tienda, qué podés hacer). "
            "**No es** el canal de #general, **no es** donde escribís los `/` del bot (`BOT_CHANNEL_ID` en el `.env`) "
            "ni el de votaciones: el staff elige **otro canal aparte** y pone su ID en **`BOT_GUIA_CHANNEL_ID`** "
            "para que el bot **solo** cree/edite acá este mensaje al reiniciar.\n\n"
            "Abajo: primero lo que **ven todos** con `!`, después lo **solo vos** con slash (*ephemeral*), cuando aplique."
        ),
        color=discord.Color.blurple(),
    )
    e0.add_field(
        name="Cómo ganar puntos",
        value=(
            f"• **Iniciación** (una vez): {_fmt_pts(int(rw.get('inicial') or 0))} + blisters — "
            "`/aat_progreso_iniciacion` (solo vos).\n"
            f"• **Diaria**: {_fmt_pts(int(rw.get('diaria') or 0))} + blister — mensajes, reacciones, **Trampa** y **oráculo**.\n"
            f"  · **Todos:** arrobá al **bot** + tu pregunta en el mismo mensaje (responde en hilo) · `!pregunta` + texto.\n"
            f"  · **Slash:** `/aat_consulta` (la respuesta del oráculo va al canal; la ven quienes estén ahí).\n"
            f"  · Puntos extra oráculo: hasta {int(rw.get('oracle_max_preguntas_con_puntos') or 5)} preguntas/día a "
            f"{_fmt_pts(int(rw.get('oracle_pregunta_points') or 0))} c/u.\n"
            f"• **Semanal**: {_fmt_pts(int(rw.get('semanal') or 0))} — foro / media / videos — `/aat_progreso_semanal` (solo vos).\n"
            f"• **Especial semanal (Impostor)**: {_fmt_pts(int(rw.get('especial_semanal') or 0))} + blisters.\n"
            f"• **Minijuegos semanal**: {_fmt_pts(int(rw.get('minijuegos_semanal') or 0))} + blisters.\n"
            "• **Top anime (bonos únicos):** completar 10 y 30 posiciones — ver embed *Top anime*.\n"
            "• **Colección de blisters (bono, `.env`):** lista de tipos en `BLISTER_COLLECTION_TYPES` + puntos en "
            "`REWARD_BLISTER_COLLECTION_POINTS`; al sumar blisters y cumplir la meta se acredita solo (subí "
            "`REWARD_BLISTER_COLLECTION_VERSION` cuando agregues tipos nuevos)."
        ),
        inline=False,
    )
    e0.add_field(
        name="Progreso y reclamar",
        value=(
            "**Todos en el canal:** `!progreso` · `!diaria` · `!semanal` · `!inicial` "
            "(donde el staff permita, p. ej. #general).\n"
            "**Solo vos:** `/aat_progreso_iniciacion` · `/aat_progreso_diaria` · `/aat_progreso_semanal`\n\n"
            "**Todos:** `!reclamar`\n"
            "**Solo vos:** `/aat_reclamar` (sin tipo reclama todo lo listo, o elegí `inicial` / `diaria` / `semanal` / "
            "`semanal_especial` / `semanal_minijuegos`)."
        ),
        inline=False,
    )
    e0.add_field(
        name="Puntos rápidos",
        value="**Todos:** `!puntos`\n**Solo vos:** `/aat_puntos`",
        inline=False,
    )

    lineas_tienda: List[str] = []
    for label, key in [
        ("Rol Akatsuki", "price_akatsuki"),
        ("Rol Jonin", "price_jonin"),
        ("Crédito pin (luego fijar mensaje)", "price_pin"),
        ("Blister trampa", "price_blister_trampa"),
        ("Encuesta tienda", "price_poll_tienda"),
        ("Pin directo en #general", "price_pin_general"),
        ("Rol decorativo temporal", "price_temp_role"),
    ]:
        ln = _linea_precio(label, int(sc.get(key) or 0))
        if ln:
            lineas_tienda.append(ln)

    e1 = discord.Embed(title="🏪 Tienda y canjes", color=discord.Color.gold())
    e1.description = (
        "**No hay comandos `!` de tienda.** Todo es slash y la respuesta es **solo para vos** "
        "(nadie más ve tu saldo ni el canje).\n"
        "**Solo vos:** `/aat_tienda_ver` (precios y saldo) · `/aat_tienda_canjear` · `/aat_tienda_fijar` · "
        "`/aat_tienda_pin_general` · `/aat_tienda_encuesta` · `/aat_tienda_rol_temporal`"
    )
    e1.add_field(
        name="Canjes típicos (`/aat_tienda_canjear`)",
        value=(
            "**akatsuki** / **jonin** / **pin** / **blister_trampa**\n"
            "• **pin** suma 1 crédito; después `/aat_tienda_fijar` con la **ID** del mensaje en ese canal.\n"
            "• **blister_trampa** → abrís con `/aat_abrirblister` (privado) o `!abrir` (todos ven el resultado en el canal)."
        ),
        inline=False,
    )
    e1.add_field(
        name="Precios (si > 0 en .env)",
        value="\n".join(lineas_tienda) or "*(Sin precios > 0 en env; el staff puede activarlos.)*",
        inline=False,
    )

    b10 = int(rw.get("anime_top10_bonus") or 0)
    b30 = int(rw.get("anime_top30_bonus") or 0)
    e2 = discord.Embed(title="🎌 Top de anime / manga (hasta 30)", color=discord.Color.dark_teal())
    e2.description = (
        "Armá **tu ranking** (posiciones **1 a 30**); podés cambiar títulos cuando quieras.\n"
        f"Bonos únicos (si están en `.env`): **10** primeras → {_fmt_pts(b10)} · **30** → {_fmt_pts(b30)}.\n\n"
        "**Todos en el canal:** `!animetop` · `!animetop @usuario` (se ve el listado en el chat).\n"
        "**Solo vos:** `/aat_anime_top_set` · `/aat_anime_top_quitar` · `/aat_anime_top_guia` · "
        "`/aat_anime_top_ver` **sin** elegir a nadie (tu top en privado). "
        "Si en el slash elegís **otro usuario**, la respuesta puede ser **pública** en el canal."
    )

    e3 = discord.Embed(title="🃏 Cartas", color=discord.Color.dark_red())
    e3.add_field(
        name="Inventario (puntos, pins, blisters)",
        value="**Todos:** `!inventario`\n**Solo vos:** `/aat_inventario`",
        inline=False,
    )
    e3.add_field(
        name="Ver tus cartas (lista con IDs)",
        value=(
            "**Para que solo vos veas tu colección:** usá **`/aat_miscartas`** "
            "(en el canal de comandos del bot). Discord muestra la respuesta como **solo para vos** "
            "(mensaje privado / *ephemeral*; el resto del servidor no ve qué cartas tenés).\n"
            "**Ojo:** **`!miscartas`** deja el embed **en el canal** → **lo ven todos**; usalo solo si te da igual mostrar la lista."
        ),
        inline=False,
    )
    e3.add_field(
        name="Abrir sobres · catálogo · detalle · usar",
        value=(
            "**Todos:** `!abrir` · `!catalogo` · `!usar <id> [@alguien]`\n"
            "**Solo vos:** `/aat_abrirblister` · `/aat_catalogo` · `/vercarta` · `/usar` "
            "(el aviso *¡Carta usada!* es privado; el **embed del efecto** se publica en el canal para que se vea la jugada)."
        ),
        inline=False,
    )

    e4 = discord.Embed(title="🎭 Impostor · ranking · ayuda", color=discord.Color.dark_blue())
    e4.add_field(
        name="Impostor",
        value=(
            "**Todos:** `!impostor` (aviso en el canal; buscan jugadores).\n"
            "**Slash:** `/crearsimpostor` · `/entrar` (según lo que muestre Discord al escribir)."
        ),
        inline=False,
    )
    e4.add_field(
        name="Ranking de puntos del servidor",
        value="**Todos:** `!top` / `!ranking`\n**Slash:** `/aat_ranking_top` (la tabla suele verse en el canal).",
        inline=False,
    )
    e4.add_field(
        name="Lista de comandos y ayuda",
        value=(
            "**En este canal:** los embeds siguientes listan **todos** los `!` y `/` del bot.\n"
            "**En el chat:** `!ayuda` o `!guia` (donde el staff lo permita) repite la misma guía en embeds.\n"
            "**Resumen corto:** `!comandos`\n"
            "**Solo vos:** `/aat_ayuda` (guía interactiva con botones, *ephemeral*)."
        ),
        inline=False,
    )

    out: List[discord.Embed] = [e0, e1, e2, e3, e4] + build_comandos_ref_embeds()
    return out[:10]
