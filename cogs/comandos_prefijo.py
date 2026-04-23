# Comandos con prefijo ? — visibles para todos en el canal (no ephemeral).
# Los slash / siguen existiendo; esto es atajo y descubribilidad.
from __future__ import annotations

import logging
import os
import random
from typing import List, Optional

import discord
from discord.ext import commands

from cogs.economia.db_manager import EconomiaDBManagerV2
from cogs.economia.card_db_manager import CardDBManager
from cogs.economia.cartas_cog import StockCatalogView
from cogs.economia import card_effectos
from cogs.economia.reclamar_service import (
    RECLAMO_TIPOS_AYUDA,
    build_inicial_reclaim_hint,
    is_reclamar_all_keyword,
    map_reclamo_token_to_tipo,
    reclaim_rewards,
)
from cogs.economia.anime_top_cog import _embed_top_for
from cogs.economia.guia_contenido import (
    GuiaEmbedsPaginator,
    build_guia_embeds,
    chunk_guia_embeds_for_send,
)
from cogs.economia.reclamar_help_ui import ReclamarHelpView, build_reclaim_result_embed
from cogs.economia.reclamar_vistas import build_reclamar_help_pages
from cogs.economia.progreso_reclaim_ui import ProgressEmbedsWithReclaimView
from cogs.economia.progreso_vistas import (
    build_pages_diaria,
    build_pages_inicial,
    build_pages_semanal,
    build_progreso_ayuda_pages,
    build_progreso_resumen_pages,
)
from cogs.economia.toque_labels import fmt_toque_sentence, guia_toque_explicacion, toque_emote
from cogs.economia.mi_resumen import render_mi_embed, render_ranking_hub_embed, render_top_embed
from cogs.economia.ranking_hub_view import RankingHubView
from cogs.impostor import core as impostor_core
from cogs.impostor import feed as impostor_feed
from cogs.impostor import notify as impostor_notify
from cogs.impostor.engine import PHASE_END

log = logging.getLogger(__name__)


async def _reply_paginated_embeds(
    ctx: commands.Context,
    pages: List[List[discord.Embed]],
    *,
    label: str,
    reclaim_layout: Optional[str] = None,
) -> None:
    clean = [p for p in pages if p]
    if not clean:
        await ctx.send("Nada para mostrar.", delete_after=8)
        return
    if reclaim_layout:
        view = ProgressEmbedsWithReclaimView(
            ctx.bot, ctx.author.id, clean, label=label, layout=reclaim_layout  # type: ignore[arg-type]
        )
        await ctx.send(content=view.header(), embeds=clean[0], view=view)
        return
    if len(clean) == 1:
        await ctx.send(embeds=clean[0])
        return
    view = GuiaEmbedsPaginator(ctx.author.id, clean, label=label)
    await ctx.send(content=view.header(), embeds=clean[0], view=view)


class ComandosPrefijoCog(commands.Cog, name="Comandos Prefijo"):
    """Atajos `?` públicos (economía, impostor)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self.card_db: CardDBManager = bot.card_db
        self.task_config = bot.task_config

    def _pages_inicial(self, ctx: commands.Context) -> List[List[discord.Embed]]:
        return build_pages_inicial(self.db, self.task_config or {}, ctx.author.id)

    def _pages_diaria(self, ctx: commands.Context) -> List[List[discord.Embed]]:
        return build_pages_diaria(self.db, self.task_config or {}, ctx.author.id)

    def _pages_semanal(self, ctx: commands.Context) -> List[List[discord.Embed]]:
        return build_pages_semanal(self.db, self.task_config or {}, ctx.author.id)

    @commands.command(name="comandos", aliases=["aat", "cmds", "cmd", "ayudabot"])
    async def comandos(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Comandos del bot (Anime al Toque)",
            description=(
                "**Guía larga** (una **sección por página**, Anterior/Siguiente): **`?ayuda`** · **`?guia`** · **`/aat-guia`**.\n"
                "**En #general** solo: `?roll` · `?rollp` / `?rollc` / `?rollpaceptar` · `?abrir` · `?usar` · oráculo · trivia · `?impostor` · `?animetop` · `?comandos`.\n"
                "**Economía y tareas** (`?reclamar` = guía + botones; `?reclamar diaria`…; `?progreso`…):** en el **canal del bot** o con **slash** (no en #general).\n"
                "**Con `/`** — versión completa (Discord te autocompleta).\n\n"
                "**Economía (canal del bot o slash):** `?puntos` · `?inventario` · `?mi` · `?top` · `?tophist` · `?ranking` (tablas paginadas + botones) · `?reclamar` · `?progreso` · `?progresoayuda` · "
                "`?diario` / `?diaria` (*daily*) · `?semanal` (*weekly*) · `?inicial` · `?abrir` · `?miscartas` · `?catalogo` · `?usar`\n"
                "**Impostor:** `?impostor` — avisá que buscás gente / ver lobbies abiertos.\n"
                "**Oráculo:** arrobá al bot + tu pregunta en el mismo mensaje · `?pregunta` + texto · `/aat-consulta` — sí / no / a veces %. Cuenta para el **diario** (*daily*) y puede dar **Toque points** extra.\n"
                "**Top anime:** `?animetop` · `?animetop @usuario` — editar: `?topset <1-33> <título>` · `?topquitar <n>` — slash: `/aat-anime-top_*`\n"
                "**Perfil:** `/aat-wishlist_*` · `/aat-hated_*` · `/aat-chars_*` (wishlist 1–33, odiados 1–10, personajes 1–10).\n"
                "**Trivia anime:** el bot publica en **#general** (varias al día, tiempo límite configurable); "
                "`?r` / `?respuestapregunta` + respuesta (a veces también sin `?` en #general, según bot) · `?triviatop` / `?triviami` ranking.\n"
                "**Slash útiles:** `/aat-ayuda` · `/crearsimpostor` · `/entrar` · `/aat-tienda-ver`"
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    async def _send_full_guia_embeds(self, ctx: commands.Context) -> None:
        try:
            chunks = chunk_guia_embeds_for_send(self.bot)
        except Exception:
            log.exception("build_guia_embeds / chunk falló")
            await ctx.send(
                "No pude armar la guía ahora (error interno). Probá `/aat-guia` o avisá al staff.",
                mention_author=False,
            )
            return
        if not chunks or any(len(part) == 0 for part in chunks):
            await ctx.send(
                "La guía salió vacía (revisá configuración del bot). Mientras tanto: `/aat-guia`.",
                mention_author=False,
            )
            return
        try:
            await _reply_paginated_embeds(ctx, chunks, label="📚 **Guía del bot**")
        except discord.HTTPException as e:
            log.warning("Envío guía embeds en canal falló: %s", e)
            try:
                for i, part in enumerate(chunks):
                    head = f"📚 **Guía ({i + 1}/{len(chunks)})**" if len(chunks) > 1 else None
                    await ctx.author.send(content=head, embeds=part)
                await ctx.send(
                    f"{ctx.author.mention} Te mandé la guía por **mensaje privado** (este canal no aceptó los embeds: "
                    "permisos o límites de Discord).",
                    mention_author=False,
                )
            except Exception:
                await ctx.send(
                    "Discord rechazó el envío. Si el bot ya tiene **Incrustar enlaces** acá, actualizá el bot a la última "
                    "versión (había un límite de 1024 caracteres por bloque de texto en la guía). "
                    "Probá `/aat-guia` o en otro canal.",
                    mention_author=False,
                )

    @commands.command(name="ayuda")
    async def ayuda(self, ctx: commands.Context):
        """Misma guía que el canal fijo: economía, tienda, cartas, listado de comandos y recompensas."""
        await self._send_full_guia_embeds(ctx)

    @commands.command(aliases=["puntos"])
    async def puntos_cmd(self, ctx: commands.Context):
        self.db.ensure_user_exists(ctx.author.id)
        eco = self.db.get_user_economy(ctx.author.id)
        tq = toque_emote()
        embed = discord.Embed(
            title=f"{tq} Toque points — {ctx.author.display_name}",
            description=(
                f"**{eco['puntos_actuales']}** actuales · Conseguidos: **{eco['puntos_conseguidos']}** · "
                f"Gastados: **{eco['puntos_gastados']}**\n\n"
                f"{guia_toque_explicacion()}"
            ),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def inventario(self, ctx: commands.Context):
        self.db.ensure_user_exists(ctx.author.id)
        eco = self.db.get_user_economy(ctx.author.id)
        blisters = self.db.get_blisters_for_user(ctx.author.id)
        lines = "\n".join(f"• {b['blister_tipo']}: x{b['cantidad']}" for b in blisters) or "Ninguno"
        embed = discord.Embed(
            title=f"Inventario de {ctx.author.display_name}",
            description=f"Toque points: **{eco['puntos_actuales']}** · Pins: **{eco['creditos_pin']}**\n{lines}",
            color=discord.Color.dark_green(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="roll")
    async def roll_cmd(self, ctx: commands.Context, minimo: int = 1, maximo: int = 100):
        """Roll público simple para #general."""
        if minimo >= maximo:
            return await ctx.send("El máximo debe ser mayor que el mínimo.", delete_after=8)
        if maximo - minimo > 500:
            return await ctx.send("Rango máximo 500.", delete_after=8)
        r = random.randint(minimo, maximo)
        await ctx.send(f"🎲 **{ctx.author.display_name}** sacó **{r}** ({minimo}–{maximo}).")

    @commands.command(name="rollp")
    async def rollp_cmd(self, ctx: commands.Context, oponente: discord.Member):
        """Reto de roll 1–100 sin apuesta vs @usuario (`/aat-roll-retar` con apuesta 0)."""
        cog = self.bot.get_cog("Economia Minijuegos")
        if not cog:
            return await ctx.send("Minijuegos no disponible.", delete_after=8)
        await cog.roll_reto_desde_prefijo(ctx, oponente, 0)

    @commands.command(name="rollc")
    async def rollc_cmd(self, ctx: commands.Context, oponente: discord.Member, apuesta: int):
        """Reto de roll 1–100 con apuesta en puntos: `?rollc @rival 100`."""
        if apuesta < 1:
            return await ctx.send(
                "Con `?rollc` indicá los puntos (1–5000). Para **sin apuesta** usá `?rollp @usuario`.",
                delete_after=12,
            )
        cog = self.bot.get_cog("Economia Minijuegos")
        if not cog:
            return await ctx.send("Minijuegos no disponible.", delete_after=8)
        await cog.roll_reto_desde_prefijo(ctx, oponente, int(apuesta))

    @commands.command(name="rollpaceptar", aliases=["rollp_aceptar"])
    async def rollpaceptar_cmd(self, ctx: commands.Context):
        """Aceptar reto de roll (con o sin apuesta) pendiente hacia vos."""
        cog = self.bot.get_cog("Economia Minijuegos")
        if not cog:
            return await ctx.send("Minijuegos no disponible.", delete_after=8)
        await cog.roll_aceptar_desde_prefijo(ctx)

    @commands.command()
    async def animetop(self, ctx: commands.Context, quien: Optional[discord.Member] = None):
        """Ver top anime propio o de otro miembro (mismo texto que el slash)."""
        target = quien or ctx.author
        rows = self.db.anime_top_list(target.id)
        emb = _embed_top_for(self.bot, target, rows, viewer_is_target=target.id == ctx.author.id)
        await ctx.send(embed=emb)

    @commands.command(name="topset", aliases=["topanimeset", "animetopset"])
    async def topset_cmd(self, ctx: commands.Context, posicion: int, *, titulo: str):
        """Poner o cambiar una casilla del top anime (1–33); misma posición = reemplazar."""
        t = (titulo or "").strip()
        if len(t) > 200:
            return await ctx.send("El título es demasiado largo (máx. 200 caracteres).", delete_after=10)
        try:
            self.db.anime_top_set(ctx.author.id, int(posicion), t)
        except ValueError as e:
            return await ctx.send(str(e), delete_after=10)
        rw = (self.task_config or {}).get("rewards") or {}
        b10 = int(rw.get("anime_top10_bonus") or 0)
        b30 = int(rw.get("anime_top30_bonus") or 0)
        bonus = self.db.apply_anime_milestones(ctx.author.id, b10, b30)
        rows = self.db.anime_top_list(ctx.author.id)
        emb = _embed_top_for(self.bot, ctx.author, rows, viewer_is_target=True)
        extra = "\n".join(bonus) if bonus else ""
        msg = "Listo: guardado (si ya había algo en esa posición, quedó **reemplazado**)."
        if extra:
            msg += "\n" + extra
        await ctx.send(content=msg, embed=emb)

    @commands.command(name="topquitar", aliases=["topanimequitar", "animetopquitar"])
    async def topquitar_cmd(self, ctx: commands.Context, posicion: int):
        """Vaciar una posición del top anime (1–33)."""
        if posicion < 1 or posicion > 33:
            return await ctx.send("La posición debe ser entre 1 y 33.", delete_after=8)
        self.db.anime_top_remove(ctx.author.id, int(posicion))
        rows = self.db.anime_top_list(ctx.author.id)
        emb = _embed_top_for(self.bot, ctx.author, rows, viewer_is_target=True)
        await ctx.send(content=f"Posición **{posicion}** vaciada.", embed=emb)

    @commands.command()
    async def mi(self, ctx: commands.Context):
        """Saldo, posición en `?top` y `?tophist`, cartas en inventario y totales."""
        self.db.ensure_user_exists(ctx.author.id)
        embed = await render_mi_embed(self.bot, self.db, ctx.author)
        await ctx.send(embed=embed)

    @commands.command(aliases=["histtop", "tophistorico"])
    async def tophist(self, ctx: commands.Context):
        """Top 5 por total histórico ganado (`puntos_conseguidos`), sin importar lo gastado."""
        tq = toque_emote()
        embed = await render_top_embed(
            self.bot,
            self.db,
            ranking_type="conseguidos",
            points_key="puntos_conseguidos",
            title=f"{tq} Top 5 — histórico ganado (total conseguido)",
            limit=5,
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["rank"])
    async def top(self, ctx: commands.Context):
        """Top 5 por saldo actual (`?tophist` = histórico ganado; `?ranking` = hub con paginación)."""
        tq = toque_emote()
        embed = await render_top_embed(
            self.bot,
            self.db,
            ranking_type="actual",
            points_key="puntos_actuales",
            title=f"{tq} Top 5 — saldo actual (Toque points)",
            limit=5,
        )
        await ctx.send(embed=embed)

    @commands.command(name="ranking", aliases=["tablas", "leaderboard", "rankings"])
    async def ranking_hub_cmd(self, ctx: commands.Context):
        """Tablas de economía con paginación y botones (tops trivia, tu resumen, top anime)."""
        if ctx.author.bot:
            return
        self.db.ensure_user_exists(ctx.author.id)
        view = RankingHubView(self.bot, self.db, ctx.author.id)
        embed = await render_ranking_hub_embed(
            self.bot, self.db, view.mode, view.offset, view.page_size, ctx.author
        )
        await ctx.send(embed=embed, view=view)

    @commands.command(aliases=["daily", "diario"])
    async def diaria(self, ctx: commands.Context):
        await _reply_paginated_embeds(
            ctx, self._pages_diaria(ctx), label="?diario / ?diaria / ?daily", reclaim_layout="diaria"
        )

    @commands.command(aliases=["weekly", "semanal"])
    async def semanal_cmd(self, ctx: commands.Context):
        await _reply_paginated_embeds(
            ctx, self._pages_semanal(ctx), label="?semanal / ?weekly", reclaim_layout="semanal"
        )

    @commands.command(aliases=["starter", "iniciacion"])
    async def inicial(self, ctx: commands.Context):
        await _reply_paginated_embeds(
            ctx, self._pages_inicial(ctx), label="?inicial / ?starter", reclaim_layout="inicial"
        )

    @commands.command(name="progresoayuda", aliases=["ayudaprogreso", "leyendaprogreso", "comoprogreso"])
    async def progresoayuda(self, ctx: commands.Context):
        await _reply_paginated_embeds(ctx, build_progreso_ayuda_pages(), label="?progresoayuda")

    @commands.command()
    async def progreso(self, ctx: commands.Context):
        pages: List[List[discord.Embed]] = []
        pages.extend(build_progreso_resumen_pages(self.db, self.task_config or {}, ctx.author.id))
        pages.extend(self._pages_inicial(ctx))
        pages.extend(self._pages_diaria(ctx))
        pages.extend(self._pages_semanal(ctx))
        await _reply_paginated_embeds(
            ctx,
            pages,
            label="?progreso (resumen + inicial + diario/daily + semanal/weekly)",
            reclaim_layout="progreso",
        )

    @commands.command()
    async def reclamar(self, ctx: commands.Context, *, args: str = ""):
        parts = args.strip().split()
        if not parts:
            pages = build_reclamar_help_pages(self.db, self.task_config or {}, ctx.author.id)
            view = ReclamarHelpView(ctx.bot, ctx.author.id, pages, label="?reclamar — guía")
            await ctx.send(content=view.header(), embeds=pages[0], view=view)
            return

        tipo = None
        w = parts[0]
        if is_reclamar_all_keyword(w):
            tipo = None
        else:
            m = map_reclamo_token_to_tipo(w)
            if m is None:
                await ctx.send(f"No reconozco `{parts[0]}`. {RECLAMO_TIPOS_AYUDA}")
                return
            tipo = m  # type: ignore[assignment]

        ok, ok_msgs, err_msgs = reclaim_rewards(self.db, self.task_config, ctx.author.id, tipo)  # type: ignore[arg-type]
        embed = build_reclaim_result_embed(self.db, self.task_config or {}, ctx.author.id, ok_msgs, err_msgs)
        await ctx.send(embed=embed)
        if not ok and not err_msgs:
            hint = build_inicial_reclaim_hint(self.db, ctx.author.id)
            if hint:
                await ctx.send(
                    hint + "\n\nPara **diario** / **semanal**: `?diario` · `?semanal` · `?progreso` o `/aat-progreso-*`."
                )

    @commands.command()
    async def miscartas(self, ctx: commands.Context):
        cartas = self.db.get_cards_in_inventory(ctx.author.id)
        if not cartas:
            await ctx.send("No tenés cartas. Abrí blisters con `?abrir` o `/aat-abrirblister`.")
            return
        lines: List[str] = []
        for c in cartas:
            c_data = self.card_db.get_carta_stock_by_id(c["carta_id"])
            if c_data:
                lines.append(f"#{c['carta_id']} **{c_data['nombre']}** (x{c['cantidad']})")
        await ctx.send(embed=discord.Embed(title="Tus cartas", description="\n".join(lines[:25]) or "—", color=discord.Color.blue()))

    @commands.command()
    async def catalogo(self, ctx: commands.Context):
        all_cards = self.card_db.get_all_cards_stock()
        if not all_cards:
            await ctx.send("Catálogo vacío.")
            return
        view = StockCatalogView(ctx.author.id, all_cards, "Catálogo")
        embed = view.get_page_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def abrir(self, ctx: commands.Context):
        user_id = ctx.author.id
        blisters = self.db.get_blisters_for_user(user_id)
        if not blisters:
            await ctx.send("No tenés blisters.")
            return
        cartas_nuevas: List[str] = []
        count = 0
        for b in blisters:
            cant = b["cantidad"]
            if cant <= 0:
                continue
            _, _ = self.db.modify_blisters(user_id, b["blister_tipo"], -cant)
            count += cant
            for _ in range(cant * 3):
                if b["blister_tipo"].lower() == "trampa":
                    c = self.card_db.get_random_card_blister_trampa()
                else:
                    c = self.card_db.get_random_card_by_rarity()
                if c:
                    self.db.add_card_to_inventory(user_id, c["carta_id"], 1)
                    cartas_nuevas.append(c["nombre"])
        if not cartas_nuevas:
            await ctx.send("Error de stock de cartas (avisá al staff).")
            return
        resumen: dict = {}
        for n in cartas_nuevas:
            resumen[n] = resumen.get(n, 0) + 1
        text = "\n".join(f"• {k} x{v}" for k, v in resumen.items())
        await ctx.send(f"Abriste **{count}** blister(s).\n{text[:1800]}")

    @commands.command(aliases=["usarcarta"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def usar(self, ctx: commands.Context, carta_id: str, target: Optional[discord.Member] = None):
        if not carta_id.isdigit():
            await ctx.send("Usá: `?usar <id_carta> [@alguien]` (el ID sale en `?miscartas`).")
            return
        cid = int(carta_id)
        user_id = ctx.author.id
        uso = self.db.get_card_usage_history(user_id, minutes=10)
        if len(uso) >= 5:
            await ctx.send("Límite: 5 cartas cada 10 minutos.")
            return
        if not self.db.get_card_from_inventory(user_id, cid):
            await ctx.send("No tenés esa carta.")
            return
        self.db.use_card_from_inventory(user_id, cid)
        self.db.log_card_usage(user_id)
        c_data = self.card_db.get_carta_stock_by_id(cid)
        if not c_data:
            await ctx.send("Carta no encontrada en catálogo.")
            return
        g_id = ctx.guild.id if ctx.guild else None
        if (c_data.get("tipo_carta") or "").lower() == "trampa":
            self.db.log_trampa_uso(
                user_id, target.id if target else None, cid, str(c_data.get("nombre") or "?"), g_id, ctx.channel.id
            )
            if target:
                self.db.mark_trampa_enviada(user_id)
            else:
                self.db.bump_trampa_sin_objetivo(user_id)
        titulo = "¡Carta activada!"
        desc = f"**{ctx.author.display_name}** usó **{c_data['nombre']}**"
        if target:
            titulo = "¡Carta contra alguien!"
            desc = f"**{ctx.author.display_name}** usó **{c_data['nombre']}** contra {target.mention}"
        embed = discord.Embed(title=titulo, description=desc, color=discord.Color.red())
        if c_data.get("url_imagen"):
            embed.set_image(url=c_data["url_imagen"])
        embed.add_field(name="Efecto", value=str(c_data.get("efecto") or "—"))
        await ctx.send(embed=embed)
        if ctx.guild and isinstance(ctx.author, discord.Member):
            sc = getattr(self.bot, "shop_config", None) or {}
            await card_effectos.aplicar_efecto_al_usar(
                carta=c_data,
                actor=ctx.author,
                target=target,
                channel=ctx.channel,
                economia_db=self.db,
                guild=ctx.guild,
                trampa_carta_rol_id=int(sc.get("trampa_carta_rol_24h_id") or 0),
                trampa_carta_rol_hours=int(sc.get("trampa_carta_rol_24h_hours") or 24),
            )

    @commands.command(aliases=["buscoimpostor", "busco", "lobbys", "cartelera"])
    @commands.cooldown(1, 45, commands.BucketType.channel)
    async def impostor(self, ctx: commands.Context):
        """Aviso público: menciona rol de avisos + resume lobbies abiertos (todos lo ven)."""
        if not ctx.guild:
            await ctx.send("Solo en servidor.")
            return
        role_id = impostor_notify.get_notify_role_id()
        role = ctx.guild.get_role(role_id)
        feed_id = impostor_feed.get_feed_channel_id()
        feed_ch = ctx.guild.get_channel(feed_id) if feed_id else None
        feed_mention = feed_ch.mention if isinstance(feed_ch, discord.abc.GuildChannel) else (f"<#{feed_id}>" if feed_id else "*(cartelera no configurada)*")

        open_lines: List[str] = []
        for lobby in impostor_core.get_all_lobbies():
            if lobby.phase == PHASE_END:
                continue
            if lobby.in_progress or not lobby.is_open:
                continue
            host = ctx.guild.get_member(lobby.host_id)
            host_name = host.display_name if host else str(lobby.host_id)
            open_lines.append(f"• **{lobby.lobby_name}** — {lobby.all_players_count}/{lobby.max_slots} — host **{host_name}** — `/entrar nombre:{lobby.lobby_name}`")

        body = (
            f"¿Quién se suma a **Impostor**? Mirá la cartelera en {feed_mention}\n"
            f"Para crear lobby: `/crearsimpostor`"
        )
        if open_lines:
            body += "\n\n**Lobbies abiertos ahora:**\n" + "\n".join(open_lines[:10])
        else:
            body += "\n\n*(No hay lobbies abiertos en este momento.)*"

        embed = discord.Embed(title="🔔 Impostor — buscan jugadores", description=body, color=discord.Color.dark_red())
        if role:
            await ctx.send(
                content=f"{role.mention} — pedido por {ctx.author.mention}",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=True, users=True),
            )
        else:
            embed.set_footer(text="Falta el rol de avisos (IMPOSTOR_NOTIFY_ROLE_ID) o no existe en el servidor.")
            await ctx.send(embed=embed)

    @commands.command(name="canjes", aliases=["tienda", "recompensas"])
    async def canjes(self, ctx: commands.Context):
        """Resumen público de qué podés canjear con puntos y con qué comandos."""
        embeds = build_guia_embeds(self.bot)
        await ctx.send(embed=embeds[1])

    @commands.command(name="ganarpuntos", aliases=["comoganar"])
    async def ganar_puntos(self, ctx: commands.Context):
        """Resumen público: cómo se consiguen puntos + cómo ver lo que falta y qué reclamar."""
        embeds = build_guia_embeds(self.bot)
        e0 = embeds[0]
        extra = discord.Embed(title="📋 Ver qué te falta y reclamar", color=discord.Color.blurple())
        extra.description = (
            "**En este canal (todos lo ven):** `?progreso` · `?progresoayuda` · `?diario` / `?diaria` (*daily*) · `?semanal` (*weekly*) · `?inicial` · `?reclamar` (guía paginada + ver progreso / cobrar)\n"
            "**Por slash (también sirve en #general):** `/aat-progreso-iniciacion` · `/aat-progreso-diaria` (*daily*) · "
            "`/aat-progreso-semanal` (*weekly*) · `/aat-progreso-ayuda` · `/aat-reclamar`\n\n"
            "Tip: si querés reclamar **solo** un tipo con slash, usá `/aat-reclamar` eligiendo "
            "`inicial` / `diaria` (*daily*) / `semanal` (*weekly*) / `semanal_especial` (*special*) / `semanal_minijuegos` (*minigames*).\n"
            "Guía completa en embeds: `?ayuda` / `?guia` / `/aat-guia`. Interactiva (solo vos): `/aat-ayuda`."
        )
        await _reply_paginated_embeds(ctx, [[e0], [extra]], label="?ganarpuntos / ?comoganar")

    @commands.command(name="guia", aliases=["guía"])
    async def guia(self, ctx: commands.Context):
        """Guía larga paginada (una sección por página). Resumen corto: `?comandos`. Interactiva: `/aat-ayuda`."""
        await self._send_full_guia_embeds(ctx)

    @usar.error
    async def usar_err(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Esperá {error.retry_after:.0f}s antes de volver a usar `?usar`.", delete_after=8)

    @impostor.error
    async def impostor_err(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Este canal ya tuvo un `?impostor` hace poco. Probá en {error.retry_after:.0f}s o usá la cartelera.",
                delete_after=10,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ComandosPrefijoCog(bot))
