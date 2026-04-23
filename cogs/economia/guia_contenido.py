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


# Límites API Discord (embed): valor de campo ≤1024; descripción ≤4096; máx. 25 campos por embed.
_MAX_FIELD_VALUE_LEN = 1020
_MAX_FIELDS_PER_EMBED = 25
_MAX_DESCRIPTION_LEN = 4096


def _split_field_value(value: str, limit: int = _MAX_FIELD_VALUE_LEN) -> List[str]:
    """Parte un texto en trozos ≤ limit, cortando preferentemente por líneas."""
    if not value:
        return [""]
    if len(value) <= limit:
        return [value]
    chunks: List[str] = []
    lines = value.split("\n")
    cur: List[str] = []
    cur_len = 0
    for line in lines:
        while len(line) > limit:
            if cur:
                chunks.append("\n".join(cur))
                cur = []
                cur_len = 0
            chunks.append(line[:limit])
            line = line[limit:]
        add = len(line) + (1 if cur else 0)
        if cur_len + add > limit and cur:
            chunks.append("\n".join(cur))
            cur = [line]
            cur_len = len(line)
        else:
            cur.append(line)
            cur_len += add
    if cur:
        chunks.append("\n".join(cur))
    return [c[:1024] for c in chunks]


def _normalize_embed_for_discord_limits(src: discord.Embed) -> List[discord.Embed]:
    """Parte valores de campo largos y reparte en varios embeds si hace falta (>25 campos)."""
    rows: List[tuple[str, str, bool]] = []
    for f in src.fields:
        base_name = (f.name or "Campo")[:240]
        for i, part in enumerate(_split_field_value(f.value or "")):
            nm = base_name if i == 0 else f"{base_name} ({i + 1})"[:256]
            rows.append((nm, part, f.inline))

    if not rows:
        e = discord.Embed(
            title=src.title[:256] if src.title else None,
            description=(src.description or "")[:_MAX_DESCRIPTION_LEN] or None,
            color=src.color,
        )
        if src.footer and src.footer.text:
            e.set_footer(text=src.footer.text[:2048])
        return [e]

    out: List[discord.Embed] = []
    i = 0
    part_n = 0
    while i < len(rows):
        chunk = rows[i : i + _MAX_FIELDS_PER_EMBED]
        i += len(chunk)
        part_n += 1
        if part_n == 1:
            e = discord.Embed(
                title=src.title[:256] if src.title else None,
                description=((src.description or "")[:_MAX_DESCRIPTION_LEN] or None),
                color=src.color,
            )
            if src.footer and src.footer.text:
                e.set_footer(text=src.footer.text[:2048])
        else:
            title = (src.title or "Guía")[:220]
            e = discord.Embed(title=f"{title} (parte {part_n})"[:256], color=src.color)
        for name, val, inline in chunk:
            e.add_field(name=name[:256], value=val[:1024], inline=inline)
        out.append(e)
    return out


def _normalize_guia_embed_list(embeds: List[discord.Embed]) -> List[discord.Embed]:
    flat: List[discord.Embed] = []
    for emb in embeds:
        flat.extend(_normalize_embed_for_discord_limits(emb))
    return flat[:50]


def flatten_guia_embeds_to_sections(embeds: List[discord.Embed]) -> List[discord.Embed]:
    """
    Convierte cada embed «denso» (descripción + varios fields) en varias páginas:
    una con la descripción (si hay) y una por cada field (título = embed + nombre del field).
    """
    out: List[discord.Embed] = []
    for emb in embeds:
        title = (emb.title or "Guía")[:256]
        color = emb.color if emb.color is not None else discord.Color.blurple()
        footer_text = (emb.footer.text[:2048] if emb.footer and emb.footer.text else None)
        desc = (emb.description or "").strip()
        fields = list(emb.fields)
        if desc:
            e = discord.Embed(title=title[:256], description=desc[:_MAX_DESCRIPTION_LEN], color=color)
            if footer_text:
                e.set_footer(text=footer_text)
            out.append(e)
        for f in fields:
            name = (f.name or "—")[:256]
            val = (f.value or "").strip() or "*(sin texto)*"
            subt = f"{title} — {name}"[:256]
            e = discord.Embed(title=subt, description=val[:_MAX_DESCRIPTION_LEN], color=color)
            out.append(e)
        if not desc and not fields and (emb.title or emb.description):
            e = discord.Embed(
                title=emb.title[:256] if emb.title else None,
                description=(emb.description or "")[:_MAX_DESCRIPTION_LEN] or None,
                color=color,
            )
            if footer_text:
                e.set_footer(text=footer_text)
            out.append(e)
    return out


class GuiaEmbedsPaginator(discord.ui.View):
    """Paginador Anterior/Siguiente; solo el usuario que abrió la guía puede tocar los botones."""

    def __init__(self, author_id: int, pages: List[List[discord.Embed]], *, label: str):
        super().__init__(timeout=420)
        self.author_id = author_id
        self.pages = pages
        self.label = label
        self.idx = 0
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        prev_b = discord.utils.get(self.children, label="Anterior")
        next_b = discord.utils.get(self.children, label="Siguiente")
        if isinstance(prev_b, discord.ui.Button):
            prev_b.disabled = self.idx <= 0
        if isinstance(next_b, discord.ui.Button):
            next_b.disabled = self.idx >= len(self.pages) - 1

    def header(self) -> Optional[str]:
        if len(self.pages) <= 1:
            return None
        return f"{self.label} · **{self.idx + 1}/{len(self.pages)}** — **Anterior** / **Siguiente**"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Solo quien abrió la guía puede paginar. Ejecutá el mismo comando vos.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="⬅️", row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.idx > 0:
            self.idx -= 1
        self._sync_buttons()
        await interaction.response.edit_message(content=self.header(), embeds=self.pages[self.idx], view=self)

    @discord.ui.button(label="Siguiente", style=discord.ButtonStyle.primary, emoji="➡️", row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.idx < len(self.pages) - 1:
            self.idx += 1
        self._sync_buttons()
        await interaction.response.edit_message(content=self.header(), embeds=self.pages[self.idx], view=self)


async def send_guia_pages_interaction(
    interaction: discord.Interaction,
    pages: List[List[discord.Embed]],
    *,
    label: str,
) -> None:
    """Tras `defer()`, envía la guía en un solo mensaje con paginación (si hay más de una página)."""
    clean = [p for p in pages if p]
    if not clean:
        await interaction.followup.send("Nada para mostrar.", ephemeral=True)
        return
    if len(clean) == 1:
        await interaction.followup.send(embeds=clean[0])
        return
    view = GuiaEmbedsPaginator(interaction.user.id, clean, label=label)
    await interaction.followup.send(content=view.header(), embeds=clean[0], view=view)


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
        f"**Guía fija del servidor:** <#{gid}> — ahí el bot deja **un mensaje por sección** con **toda** la guía "
        f"(para qué sirve cada cosa). También podés usar `?guia` o `/aat-guia` donde lo permita el staff.\n\n"
    )


def chunk_guia_embeds_for_send(bot: Any) -> List[List[discord.Embed]]:
    """Un embed por página (paginador `?guia` / slash): cada sección = un paso Anterior/Siguiente."""
    raw = build_guia_embeds(bot)
    flattened = flatten_guia_embeds_to_sections(raw)
    embeds = _normalize_guia_embed_list(flattened)
    if not embeds:
        return []
    return [[e] for e in embeds]


def build_comandos_ref_embeds(bot: Any) -> List[discord.Embed]:
    """Lista compacta de todos los comandos ? y / (para canal guía y `?ayuda`)."""
    gid = guia_fixed_channel_id(bot)
    canal_prefijo = (
        f"En <#{gid}> (guía/comandos del bot) podés usar el resto de `?` sin que los borre el filtro.\n\n"
        if gid > 0
        else "En el **canal del bot** podés usar el resto de `?` sin que los borre el filtro.\n\n"
    )
    r0a = discord.Embed(
        title="📋 Comandos con prefijo ? (1/2)",
        description=(
            "**En #general** solo: `?roll` · `?rollp` / `?rollc` / `?rollpaceptar` · `?abrir` · `?usar` / `?usarcarta` · oráculo (`?pregunta`… o @bot) · "
            "trivia (`?respuestapregunta`…) · `?impostor` · `?animetop` · `?comandos` (**lista corta**; distinto de la guía larga).\n"
            "**No en #general:** reclamar, progreso, diaria/semanal/inicial, puntos, inventario, tops, tienda, guía larga… "
            f"usalos en el canal del bot o con slash.\n\n"
            f"{canal_prefijo}"
            "**Economía y cartas (canal del bot o donde el staff indique)**\n"
            "• `?puntos` — tus Toque points · `?inventario` — saldo, pins y blisters\n"
            "• `?mi` — saldo, posición en tops, cartas e histórico ganado\n"
            "• `?top` · `?rank` — top 5 rápido por **saldo actual**\n"
            "• `?ranking` · `?tablas` — tablas **paginadas** (saldo / histórico / gastado) + botones (trivia, `?mi`, anime top)\n"
            "• `?tophist` · `?histtop` — top 5 por **total ganado** (histórico)\n"
            "• `?reclamar` — cobrar recompensas listas\n"
            "• `?progreso` — resumen iniciación + diaria + semanal\n"
            "• `?diaria` · `?daily` — **dos bloques**: actividad + oráculo, y aparte **Trampa** (misma recompensa al completar todo)\n"
            "• `?semanal` · `?weekly` · `?inicial` · `?starter` · `?iniciacion` — ver qué falta\n"
            "• `?abrir` — abrir blister (en #general también va)\n"
            "• `?miscartas` — lista de cartas (**visible para todos** en ese canal)\n"
            "• `?catalogo` — todas las cartas del juego\n"
            "• `?usar` · `?usarcarta` — usar carta trampa (`?usar <id> [@alguien]`)\n\n"
            "**Resúmenes y guía larga**\n"
            "• `?comandos` · `?aat` · `?cmds` · `?cmd` · `?ayudabot` — **resumen corto** (no pagina por sección)\n"
            "• `?ayuda` · `?guia` — guía larga: **una sección por página** (Anterior / Siguiente)\n"
            "• `/aat-guia` — lo mismo con slash (un mensaje con paginación)\n"
            "• `?canjes` · `?tienda` · `?recompensas` — embed de tienda y canjes\n"
            "• `?ganarpuntos` · `?comoganar` — cómo ganar Toque points + reclamar\n"
            "• `?roll` — dado casual (rango)\n"
            "• `?rollp @usuario` — reto roll 1–100 **sin** puntos · `?rollc @usuario <pts>` — **con** apuesta · `?rollpaceptar` — aceptar (**5 min**)"
        ),
        color=discord.Color.light_grey(),
    )
    r0b = discord.Embed(
        title="📋 Comandos con prefijo ? (2/2)",
        description=(
            "**Impostor**\n"
            "• `?impostor` · `?buscoimpostor` · `?busco` · `?lobbys` · `?cartelera` — aviso de busca / cartelera\n\n"
            "**Oráculo (cuenta para la diaria)**\n"
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
            "**Minijuegos y encuesta del servidor:** `/aat-roll` · `/aat-roll-retar` (apuesta **0** = sin puntos) · `/aat-roll-aceptar` · "
            "`/aat-voto-semanal`\n"
            "**Duelos con cartas** (si están habilitados): `/aat-duelo-retar` · `/aat-duelo-aceptar`"
        ),
        color=discord.Color.blue(),
    )

    r2 = discord.Embed(
        title="⚙️ Slash — perfil, top anime y oráculo",
        description=(
            "**Top anime (hasta 33 casillas; bonos únicos en 10 y 30):** `/aat-anime-top-ver` · `/aat-anime-top-set` (misma posición = **cambiar**) · `/aat-anime-top-quitar` · `/aat-anime-top-guia` — también `?topset` / `?topquitar` en el canal de comandos\n"
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

    return [r0a, r0b, r1, r2, r3]


def build_guia_embeds(bot: Any) -> List[discord.Embed]:
    """Embeds base de la guía (economía, tienda, cartas, comandos); el paginador parte cada sección en páginas."""
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
            f"**Foro** (un hilo con tu mensaje) + **#videos-nuevos** (una reacción; `VIDEOS_CHANNEL_ID`); **Impostor** es recompensa aparte — `/aat-progreso-semanal`.\n"
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
            "**Con `?` (canal del bot / donde indique el staff, no en #general):** "
            "`?progreso` · `?diaria` · `?semanal` · `?inicial`.\n"
            "**Solo vos:** `/aat-progreso-iniciacion` · `/aat-progreso-diaria` · `/aat-progreso-semanal`\n\n"
            "**Todos:** `?reclamar` (mismo criterio de canal que arriba)\n"
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
        "**Solo vos (canal de comandos o slash):** `?topset <1-33> <título>` (repetís la posición para **modificar**) · "
        "`?topquitar <n>` · `/aat-anime-top-set` · `/aat-anime-top-quitar` · `/aat-anime-top-guia` · "
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

    return [e0, e1, e2, e3, e4] + build_comandos_ref_embeds(bot)
