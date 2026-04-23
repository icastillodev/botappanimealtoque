# Contenido del mensaje fijo de guía (canal dedicado BOT_GUIA_CHANNEL_ID / task_config guia_bot).
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import discord

from .toque_labels import fmt_toque_line, guia_toque_explicacion


def _fmt_pts(n: int) -> str:
    return fmt_toque_line(int(n))


def _linea_precio(nombre: str, precio: int) -> Optional[str]:
    if precio and int(precio) > 0:
        return f"• {nombre}: {_fmt_pts(precio)}"
    return None


def guia_fixed_channel_id(bot: Any) -> int:
    tc = getattr(bot, "task_config", None) or {}
    gid = int((tc.get("channels") or {}).get("guia_bot") or 0)
    if gid <= 0:
        raw = (os.environ.get("BOT_GUIA_CHANNEL_ID") or "").strip()
        if raw.isdigit():
            gid = int(raw)
    return gid


def guia_fixed_channel_blurb(bot: Any) -> str:
    gid = guia_fixed_channel_id(bot)
    if gid <= 0:
        return ""
    return (
        f"**Guía fija del servidor:** <#{gid}> — ahí el bot deja varios mensajes/embeds con **toda** la guía "
        f"(para qué sirve cada cosa). También podés usar `?guia` o `/aat-guia` donde lo permita el staff.\n\n"
    )


# Discord suele mostrar mejor varias partes que un solo mensaje con muchos embeds.
GUIDE_EMBEDS_PER_MESSAGE = 5


def chunk_guia_embeds_for_send(bot: Any) -> List[List[discord.Embed]]:
    """Parte la guía en trozos de a lo sumo `GUIDE_EMBEDS_PER_MESSAGE` embeds (máx. 10 en total)."""
    embeds = build_guia_embeds(bot)[:10]
    step = GUIDE_EMBEDS_PER_MESSAGE
    return [embeds[i : i + step] for i in range(0, len(embeds), step)]


def build_comandos_ref_embeds(bot: Any) -> List[discord.Embed]:
    """Lista compacta de todos los comandos ? y / (para canal guía y `?ayuda`)."""
    gid = guia_fixed_channel_id(bot)
    canal_prefijo = (
        f"En <#{gid}> (guía/comandos del bot) podés usar el resto de `?` sin que los borre el filtro.\n\n"
        if gid > 0
        else "En el **canal del bot** podés usar el resto de `?` sin que los borre el filtro.\n\n"
    )
    r0 = discord.Embed(
        title="📋 Comandos con prefijo ?",
        description=(
            "En **#general** solo funcionan los `?` que el bot permite ahí (lista del staff). "
            f"{canal_prefijo}"
            "**Economía y cartas**\n"
            "• `?puntos` — tus Toque points · `?inventario` — saldo, pins y blisters\n"
            "• `?mi` — saldo, posición en tops, cartas e histórico ganado\n"
            "• `?top` · `?rank` · `?ranking` — top 5 por **saldo actual**\n"
            "• `?tophist` · `?histtop` — top 5 por **total ganado** (histórico)\n"
            "• `?reclamar` — cobrar recompensas listas\n"
            "• `?progreso` — resumen iniciación + diaria + semanal\n"
            "• `?diaria` · `?daily` — **dos bloques**: actividad + oráculo, y aparte **Trampa** (misma recompensa al completar todo)\n"
            "• `?semanal` · `?weekly` · `?inicial` · `?starter` · `?iniciacion` — ver qué falta\n"
            "• `?abrir` — abrir blister (público en el canal)\n"
            "• `?miscartas` — lista de cartas (**visible para todos** en ese canal)\n"
            "• `?catalogo` — todas las cartas del juego\n"
            "• `?usar` · `?usarcarta` — usar carta trampa (`?usar <id> [@alguien]`)\n\n"
            "**Resúmenes y guía en el chat**\n"
            "• `?comandos` · `?aat` · `?cmds` · `?cmd` · `?ayudabot` — resumen corto\n"
            "• `?ayuda` · `?guia` — **esta guía completa** en varios embeds\n"
            "• `/aat-guia` — la misma guía completa con slash (todos la ven en el canal)\n"
            "• `?canjes` · `?tienda` · `?recompensas` — embed de tienda y canjes\n"
            "• `?ganarpuntos` · `?comoganar` — cómo ganar Toque points + reclamar\n"
            "• `?roll` — dado casual entre dos números\n\n"
            "**Impostor**\n"
            "• `?impostor` · `?buscoimpostor` · `?busco` · `?lobbys` · `?cartelera` — aviso de busca / cartelera\n\n"
            "**Oráculo (diaria)**\n"
            "• `?pregunta` · `?consulta` · `?8ball` · `?bola` · `?oraculo` — pregunta sí/no (también @mención al bot)\n\n"
            "**Trivia anime (#general, varias al día)**\n"
            "• `?respuestapregunta` · `?triviaresp` · `?rtrivia` + respuesta (primero en acertar dentro del tiempo)\n"
            "• `?triviatop` · `?triviami` — ranking y tu puesto (solo cuentan aciertos ganadores)\n\n"
            "**Top anime**\n"
            "• `?animetop` · `?animetop @usuario`"
        ),
        color=discord.Color.light_grey(),
    )

    r1 = discord.Embed(
        title="⚙️ Slash — economía, cartas y tienda",
        description=(
            "**Toque points e inventario:** `/aat-puntos` · `/aat-inventario`\n"
            "**Reclamar y progreso:** `/aat-reclamar` · `/aat-progreso-iniciacion` · `/aat-progreso-diaria` · `/aat-progreso-semanal`\n"
            "**Ranking:** `/aat-ranking-top` · `/aat-mi` · `/aat-top-hist`\n"
            "**Cartas:** `/aat-abrirblister` · `/aat-miscartas` · `/aat-catalogo` · `/vercarta` · `/usar`\n"
            "**Tienda:** `/aat-tienda-ver` · `/aat-tienda-canjear` · `/aat-tienda-fijar` · `/aat-tienda-pin-general` · "
            "`/aat-tienda-encuesta` · `/aat-tienda-rol-temporal`\n"
            "**Público en el canal:** `/aat-canjes` · `/aat-ganar-puntos` (cómo sumar Toque points)\n"
            "**Guía completa (todos la ven):** `/aat-guia`\n"
            "**Guía interactiva (solo vos):** `/aat-ayuda`\n"
            "**Minijuegos y encuesta del servidor:** `/aat-roll` · `/aat-roll-retar` · `/aat-roll-aceptar` · "
            "`/aat-voto-semanal`\n"
            "**Duelos con cartas** (si están habilitados): `/aat-duelo-retar` · `/aat-duelo-aceptar`"
        ),
        color=discord.Color.blue(),
    )

    r2 = discord.Embed(
        title="⚙️ Slash — perfil, top anime y oráculo",
        description=(
            "**Top anime (hasta 33 casillas; bonos únicos en 10 y 30):** `/aat-anime-top-ver` · `/aat-anime-top-set` · `/aat-anime-top-quitar` · `/aat-anime-top-guia`\n"
            "**Wishlist / odiados / personajes:** `/aat-wishlist-ver` · `/aat-wishlist-set` · `/aat-wishlist-quitar` · "
            "`/aat-hated-ver` · `/aat-hated-set` · `/aat-hated-quitar` · `/aat-chars-ver` · `/aat-chars-set` · `/aat-chars-quitar`\n"
            "**Oráculo:** `/aat-consulta`"
        ),
        color=discord.Color.teal(),
    )

    r3 = discord.Embed(
        title="⚙️ Slash — Impostor, VERSUS y votaciones",
        description=(
            "**Impostor:** `/crearsimpostor` · `/entrar` · `/leave` · `/salir` · `/invitar` · `/ready` · `/listo` · `/abrirlobby` · `/cerrarlobby` · `/helpimpostor` · `/ayudaimpostor`\n"
            "**VERSUS semanal:** `/aat-versus-votos` — quién votó en la encuesta actual\n\n"
            "**Votaciones del servidor**\n"
            "• `/crear-votacion` — encuesta simple (usuario)\n"
            "• `/mis-resultados` — resultados de una votación que creaste\n"
            "• `/ayudaencuesta` — ayuda interactiva de votación\n"
            "• **Solo staff:** `/crear-votacionadmin` · `/modificarvotacion` · `/finalizarvotacion` · `/borrarvotacion` · "
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

    guia_ch = guia_fixed_channel_blurb(bot)
    e0 = discord.Embed(
        title="📌 Guía del bot — Anime al Toque",
        description=(
            f"{guia_ch}"
            "Acá tenés una guía rápida de **todo lo que podés hacer** con el bot: "
            "Toque points, recompensas, cartas, tienda, Impostor, votaciones y más.\n\n"
            f"{guia_toque_explicacion()}\n\n"
            "Abajo: primero lo que **ven todos** con `?`, después lo que es **solo para vos** con slash (*ephemeral*), cuando aplique."
        ),
        color=discord.Color.blurple(),
    )
    e0.add_field(
        name="Cómo ganar Toque points",
        value=(
            f"• **Iniciación** (una vez): {_fmt_pts(int(rw.get('inicial') or 0))} + blisters — Discord + perfil "
            f"(wishlist **{10}**, top **{10}**, odiados **{5}**; máx. **{33}**/**{33}**/**{10}**) — `/aat-progreso-iniciacion`.\n"
            f"• **Diaria** (una recompensa, **dos partes**): {_fmt_pts(int(rw.get('diaria') or 0))} + blister cuando completes **las dos**.\n"
            f"  · **Parte 1 — actividad y oráculo:** 10 mensajes en el servidor, 3 reacciones, 1 consulta al oráculo "
            f"(@bot + pregunta · `?pregunta` · `/aat-consulta`).\n"
            f"  · **Parte 2 — Trampa:** **una** carta trampa **con** mención (a alguien) **o** **sin** objetivo (sola). "
            f"Ver ambas partes con **`?diaria`**.\n"
            f"  · Toque extra oráculo: hasta {int(rw.get('oracle_max_preguntas_con_puntos') or 5)} preguntas/día a "
            f"{_fmt_pts(int(rw.get('oracle_pregunta_points') or 0))} c/u.\n"
            f"• **Semanal** (un premio base): {_fmt_pts(int(rw.get('semanal') or 0))} — **media** (memes / fanart u otros canales de creación) **aparte** de "
            f"**Foro** (un hilo con tu mensaje) + **#videos** (una reacción); **Impostor** es recompensa aparte — `/aat-progreso-semanal`.\n"
            f"• **Especial semanal (Impostor)**: {_fmt_pts(int(rw.get('especial_semanal') or 0))} + blisters.\n"
            f"• **Minijuegos semanal**: {_fmt_pts(int(rw.get('minijuegos_semanal') or 0))} + blisters.\n"
            "• **Top anime (bonos únicos en Toque points):** completar 10 y 30 posiciones — ver embed *Top anime*.\n"
            "• **Colección de blisters (bono):** si completás la colección, el bot te da un premio automático."
        ),
        inline=False,
    )
    e0.add_field(
        name="Progreso y reclamar",
        value=(
            "**Todos en el canal:** `?progreso` · `?diaria` · `?semanal` · `?inicial` "
            "(donde el staff permita, p. ej. #general).\n"
            "**Solo vos:** `/aat-progreso-iniciacion` · `/aat-progreso-diaria` · `/aat-progreso-semanal`\n\n"
            "**Todos:** `?reclamar`\n"
            "**Solo vos:** `/aat-reclamar` (sin tipo reclama todo lo listo, o elegí `inicial` / `diaria` / `semanal` / "
            "`semanal_especial` / `semanal_minijuegos`)."
        ),
        inline=False,
    )
    e0.add_field(
        name="Ver tu saldo (Toque points)",
        value="**Todos:** `?puntos`\n**Solo vos:** `/aat-puntos`",
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
        "**No hay comandos `?` de tienda.** Todo es slash y la respuesta es **solo para vos** "
        "(nadie más ve tu saldo ni el canje).\n"
        "**Solo vos:** `/aat-tienda-ver` (precios y saldo) · `/aat-tienda-canjear` · `/aat-tienda-fijar` · "
        "`/aat-tienda-pin-general` · `/aat-tienda-encuesta` · `/aat-tienda-rol-temporal`"
    )
    e1.add_field(
        name="Canjes típicos (`/aat-tienda-canjear`)",
        value=(
            "**akatsuki** / **jonin** / **pin** / **blister_trampa**\n"
            "• **pin** suma 1 crédito; después `/aat-tienda-fijar` y elegís el mensaje a fijar.\n"
            "• **blister_trampa** → abrís con `/aat-abrirblister` (privado) o `?abrir` (todos ven el resultado en el canal)."
        ),
        inline=False,
    )
    e1.add_field(
        name="Precios (según el servidor)",
        value="\n".join(lineas_tienda) or "*(La tienda no está activa ahora o no tiene precios cargados.)*",
        inline=False,
    )

    b10 = int(rw.get("anime_top10_bonus") or 0)
    b30 = int(rw.get("anime_top30_bonus") or 0)
    e2 = discord.Embed(title="🎌 Top de anime / manga (hasta 33 casillas)", color=discord.Color.dark_teal())
    e2.description = (
        "Armá **tu ranking** (posiciones **1 a 33**); los bonos automáticos siguen al completar **10** y **30** títulos.\n"
        f"Bonos únicos: **10** primeras → {_fmt_pts(b10)} · **30** → {_fmt_pts(b30)}.\n\n"
        "**Todos en el canal:** `?animetop` · `?animetop @usuario` (se ve el listado en el chat).\n"
        "**Solo vos:** `/aat-anime-top-set` · `/aat-anime-top-quitar` · `/aat-anime-top-guia` · "
        "`/aat-anime-top-ver` **sin** elegir a nadie (tu top en privado). "
        "Si en el slash elegís **otro usuario**, la respuesta puede ser **pública** en el canal."
    )

    e3 = discord.Embed(title="🃏 Cartas", color=discord.Color.dark_red())
    e3.add_field(
        name="Inventario (Toque points, pins, blisters)",
        value="**Todos:** `?inventario`\n**Solo vos:** `/aat-inventario`",
        inline=False,
    )
    e3.add_field(
        name="Ver tus cartas (lista con IDs)",
        value=(
            "**Para que solo vos veas tu colección:** usá **`/aat-miscartas`** "
            "(en el canal de comandos del bot). Discord muestra la respuesta como **solo para vos** "
            "(mensaje privado / *ephemeral*; el resto del servidor no ve qué cartas tenés).\n"
            "**Ojo:** **`?miscartas`** deja el embed **en el canal** → **lo ven todos**; usalo solo si te da igual mostrar la lista."
        ),
        inline=False,
    )
    e3.add_field(
        name="Abrir sobres · catálogo · detalle · usar",
        value=(
            "**Todos:** `?abrir` · `?catalogo` · `?usar <id> [@alguien]`\n"
            "**Solo vos:** `/aat-abrirblister` · `/aat-catalogo` · `/vercarta` · `/usar` "
            "(el aviso *¡Carta usada!* es privado; el **embed del efecto** se publica en el canal para que se vea la jugada)."
        ),
        inline=False,
    )

    e4 = discord.Embed(title="🎭 Impostor · ranking · ayuda", color=discord.Color.dark_blue())
    e4.add_field(
        name="Impostor",
        value=(
            "**Todos:** `?impostor` (aviso en el canal; buscan jugadores).\n"
            "**Slash:** `/crearsimpostor` · `/entrar` (según lo que muestre Discord al escribir)."
        ),
        inline=False,
    )
    e4.add_field(
        name="Ranking de Toque points del servidor",
        value=(
            "**Todos:** `?top` (saldo actual) · `?tophist` (histórico ganado) · `?mi` (tu resumen)\n"
            "**Slash:** `/aat-ranking-top` · `/aat-top-hist` · `/aat-mi`"
        ),
        inline=False,
    )
    gid = guia_fixed_channel_id(bot)
    en_canal = (
        f"**En el canal de guía** <#{gid}>: los embeds siguientes listan **todos** los `?` y `/` del bot.\n"
        if gid > 0
        else "**En este canal:** los embeds siguientes listan **todos** los `?` y `/` del bot.\n"
    )
    e4.add_field(
        name="Lista de comandos y ayuda",
        value=(
            f"{en_canal}"
            "**En el chat:** `?ayuda` · `?guia` (donde el staff lo permita) repite la misma guía en embeds.\n"
            "**Slash público:** `/aat-guia`\n"
            "**Resumen corto:** `?comandos`\n"
            "**Solo vos:** `/aat-ayuda` (guía interactiva con botones, *ephemeral*)."
        ),
        inline=False,
    )

    out: List[discord.Embed] = [e0, e1, e2, e3, e4] + build_comandos_ref_embeds(bot)
    return out[:10]
