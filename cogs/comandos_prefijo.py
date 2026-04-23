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
    INICIAL_HATED_MIN,
    INICIAL_TOP_MIN,
    INICIAL_WISHLIST_MIN,
    MSG_TIP_INICIACION_AL_RECLAMAR,
    PERFIL_HATED_CAP,
    PERFIL_TOP_CAP,
    PERFIL_WISHLIST_CAP,
    build_inicial_reclaim_hint,
    reclaim_rewards,
)
from cogs.economia.anime_top_cog import _embed_top_for
from cogs.economia.guia_contenido import build_guia_embeds, chunk_guia_embeds_for_send
from cogs.economia.toque_labels import fmt_toque_sentence, guia_toque_explicacion, toque_emote
from cogs.economia.mi_resumen import render_mi_embed, render_top_embed
from cogs.impostor import core as impostor_core
from cogs.impostor import feed as impostor_feed
from cogs.impostor import notify as impostor_notify
from cogs.impostor.engine import PHASE_END

log = logging.getLogger(__name__)


class ComandosPrefijoCog(commands.Cog, name="Comandos Prefijo"):
    """Atajos `?` públicos (economía, impostor)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self.card_db: CardDBManager = bot.card_db
        self.task_config = bot.task_config

    @commands.command(name="comandos", aliases=["aat", "cmds", "cmd", "ayudabot"])
    async def comandos(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Comandos del bot (Anime al Toque)",
            description=(
                "**Lista completa** (todos los `?` y `/`): **`?ayuda`** / **`?guia`** / **`/aat-guia`** (varios embeds).\n"
                "**Con `?` en el canal** (todos lo ven) — atajos abajo.\n"
                "**Con `/`** — versión completa (Discord te autocompleta).\n\n"
                "**Economía:** `?puntos` · `?inventario` · `?mi` · `?top` · `?tophist` · `?reclamar` · `?progreso` · "
                "`?diaria` · `?semanal` · `?inicial` · `?abrir` · `?miscartas` · `?catalogo` · `?usar`\n"
                "**Impostor:** `?impostor` — avisá que buscás gente / ver lobbies abiertos.\n"
                "**Oráculo:** arrobá al bot + tu pregunta en el mismo mensaje · `?pregunta` + texto · `/aat-consulta` — sí / no / a veces %. Cuenta para la **diaria** y puede dar **Toque points** extra.\n"
                "**Top anime:** `?animetop` · `?animetop @usuario` — slash: `/aat-anime-top_*`\n"
                "**Perfil:** `/aat-wishlist_*` · `/aat-hated_*` · `/aat-chars_*` (wishlist 1–33, odiados 1–10, personajes 1–10).\n"
                "**Trivia anime:** el bot publica en **#general** (varias al día, tiempo límite configurable); "
                "`?respuestapregunta` + respuesta · `?triviatop` / `?triviami` ranking.\n"
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
        n = len(chunks)
        try:
            for i, part in enumerate(chunks):
                head = f"📚 **Guía ({i + 1}/{n})**" if n > 1 else None
                await ctx.send(content=head, embeds=part)
        except discord.HTTPException as e:
            log.warning("Envío guía embeds en canal falló: %s", e)
            try:
                for i, part in enumerate(chunks):
                    head = f"📚 **Guía ({i + 1}/{n})**" if n > 1 else None
                    await ctx.author.send(content=head, embeds=part)
                await ctx.send(
                    f"{ctx.author.mention} Te mandé la guía por **mensaje privado** (este canal no aceptó los embeds: "
                    "permisos o límites de Discord).",
                    mention_author=False,
                )
            except Exception:
                await ctx.send(
                    "Discord rechazó el envío (revisá **Incrustar enlaces** / **Insertar enlaces** para el bot en este canal). "
                    "Probá en otro canal o `/aat-guia`.",
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

    @commands.command()
    async def animetop(self, ctx: commands.Context, quien: Optional[discord.Member] = None):
        """Ver top anime propio o de otro miembro (mismo texto que el slash)."""
        target = quien or ctx.author
        rows = self.db.anime_top_list(target.id)
        emb = _embed_top_for(self.bot, target, rows, viewer_is_target=target.id == ctx.author.id)
        await ctx.send(embed=emb)

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

    @commands.command(aliases=["rank", "ranking"])
    async def top(self, ctx: commands.Context):
        """Top 5 por saldo actual (`?tophist` = histórico ganado)."""
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

    @commands.command(aliases=["daily"])
    async def diaria(self, ctx: commands.Context):
        user_id = ctx.author.id
        fecha, _ = self.db.get_current_date_keys()
        prog = self.db.get_progress_diaria(user_id)
        msg_n = int(prog.get("mensajes_servidor") or 0)
        rx_n = int(prog.get("reacciones_servidor") or 0)
        tr = int(prog.get("trampa_enviada") or 0)
        ts = int(prog.get("trampa_sin_objetivo") or 0)
        tr_ok = tr >= 1 or ts >= 1
        or_n = int(prog.get("oraculo_preguntas") or 0)
        or_ok = or_n >= 1
        rw = self.task_config["rewards"]["diaria"]
        premio_txt = f"Cuando **las dos partes** estén listas: {fmt_toque_sentence(int(rw))} + 1 blister → `?reclamar`"
        e_act = discord.Embed(
            title=f"Diaria — actividad y oráculo ({fecha})",
            description=(
                f"• Mensajes en el servidor: **{msg_n}/10**\n"
                f"• Reacciones en el servidor: **{rx_n}/3**\n"
                f"• Oráculo (1 pregunta): **{'OK' if or_ok else 'pendiente'}** — {or_n}/1 "
                f"(@bot + pregunta · `?pregunta` · `/aat-consulta`)\n\n"
                f"_{premio_txt}_"
            ),
            color=discord.Color.orange(),
        )
        e_tr = discord.Embed(
            title=f"Diaria — trampa ({fecha})",
            description=(
                "**Trampa:** **una** carta — **dirigida** (`?usar` + mención) **o** **sin** objetivo (sola).\n"
                f"• Con objetivo: **{tr}/1**\n"
                f"• Sin objetivo: **{ts}/1**\n"
                f"• Estado trampa: **{'OK' if tr_ok else 'pendiente'}**\n\n"
                f"_{premio_txt}_"
            ),
            color=discord.Color.dark_orange(),
        )
        await ctx.send(embeds=[e_act, e_tr])

    @commands.command(aliases=["weekly", "semanal"])
    async def semanal_cmd(self, ctx: commands.Context):
        _, semana = self.db.get_current_date_keys()
        prog = self.db.get_progress_semanal(user_id := ctx.author.id)
        rw = self.task_config["rewards"]
        sl = semana.split("-")[-1]
        ip = int(prog.get("impostor_partidas") or 0)
        iv = int(prog.get("impostor_victorias") or 0)
        pie_sem = (
            "✅ Premio **semanal base** ya reclamado."
            if int(prog.get("completado") or 0) == 1
            else f"**Premio base (una vez):** {fmt_toque_sentence(int(rw['semanal']))} + 1 blister — `?reclamar` cuando estén **media + foro + #videos**."
        )
        e1 = discord.Embed(
            title=f"Semanal — memes / fanart (sem. {sl})",
            description=(
                f"**Media:** publicá algo con contenido en **memes**, **fanarts** u otro canal de creación que cuente el bot — "
                f"**{int(prog.get('media_escrito') or 0)}/1**\n\n_{pie_sem}_"
            ),
            color=discord.Color.purple(),
        )
        df = int(prog.get("debate_post") or 0)
        dv = int(prog.get("videos_reaccion") or 0)
        e2 = discord.Embed(
            title=f"Semanal — foro y #videos (sem. {sl})",
            description=(
                f"**Foro:** escribir en el foro — **abrí un hilo** en debate (anime o manga). **{df}/1**\n"
                f"**#videos:** reaccionar a **un** mensaje en **#videos**. **{dv}/1**\n\n"
                f"_{pie_sem}_"
            ),
            color=discord.Color.dark_purple(),
        )
        pie_imp = (
            "✅ **Impostor** ya reclamado."
            if int(prog.get("completado_especial") or 0) == 1
            else f"**Premio aparte:** {fmt_toque_sentence(int(rw.get('especial_semanal', 400)))} — `/aat-progreso-semanal`."
        )
        e3 = discord.Embed(
            title=f"Semanal — Impostor (sem. {sl})",
            description=f"Partidas: **{ip}/3** · Victoria como impostor: **{iv}/1**\n\n_{pie_imp}_",
            color=discord.Color.dark_red(),
        )
        await ctx.send(embeds=[e1, e2, e3])

    @commands.command(aliases=["starter", "iniciacion"])
    async def inicial(self, ctx: commands.Context):
        uid = ctx.author.id
        prog = self.db.get_progress_inicial(uid)
        if prog["completado"] == 1:
            await ctx.send("✅ Iniciación ya reclamada.")
            return
        wl = int(self.db.wishlist_total_filled(uid))
        top10 = int(self.db.anime_top_count_filled(uid, INICIAL_TOP_MIN))
        hat = int(self.db.hated_total_filled(uid))
        pie = f"Premio: {fmt_toque_sentence(int(self.task_config['rewards']['inicial']))} + 3 blisters → `?reclamar` (Discord + perfil)."
        e1 = discord.Embed(
            title="Iniciación — Discord",
            description=f"Presentación, autorol, redes, reglas y 1× #general.\n\n_{pie}_",
            color=discord.Color.blue(),
        )
        top_cap = int(self.db.anime_top_count_filled(uid, PERFIL_TOP_CAP))
        wl_show = min(wl, PERFIL_WISHLIST_CAP)
        hat_show = min(hat, PERFIL_HATED_CAP)
        e2 = discord.Embed(
            title="Iniciación — perfil (mínimo para reclamar)",
            description=(
                f"• Wishlist: **{wl}/{INICIAL_WISHLIST_MIN}**\n"
                f"• Top favoritos (pos. 1–{INICIAL_TOP_MIN}): **{top10}/{INICIAL_TOP_MIN}**\n"
                f"• Odiados: **{hat}/{INICIAL_HATED_MIN}**\n\n"
                f"_{pie}_"
            ),
            color=discord.Color.dark_blue(),
        )
        e3 = discord.Embed(
            title="Perfil ampliado (opcional)",
            description=(
                f"Solo **progreso** hacia el tope del perfil; **no suma otra misión** aparte del mínimo de arriba.\n\n"
                f"• Wishlist: **{wl_show}/{PERFIL_WISHLIST_CAP}**\n"
                f"• Top anime: **{top_cap}/{PERFIL_TOP_CAP}**\n"
                f"• Odiados: **{hat_show}/{PERFIL_HATED_CAP}**\n\n"
                "_Bonos del top 10 / 30: `/aat-anime-top-guia`._"
            ),
            color=discord.Color.teal(),
        )
        await ctx.send(embeds=[e1, e2, e3])

    @commands.command()
    async def progreso(self, ctx: commands.Context):
        await self.inicial(ctx)
        await self.diaria(ctx)
        await self.semanal_cmd(ctx)

    @commands.command()
    async def reclamar(self, ctx: commands.Context):
        ok, ok_msgs, err_msgs = reclaim_rewards(self.db, self.task_config, ctx.author.id, None)
        if ok:
            embed = discord.Embed(title="Recompensas", description="\n".join(ok_msgs), color=discord.Color.green())
            prog_ini = self.db.get_progress_inicial(ctx.author.id)
            if int(prog_ini.get("completado") or 0) != 1:
                embed.set_footer(text=MSG_TIP_INICIACION_AL_RECLAMAR)
            await ctx.send(embed=embed)
        elif err_msgs:
            await ctx.send("\n".join(err_msgs))
        else:
            hint = build_inicial_reclaim_hint(self.db, ctx.author.id)
            msg = (
                "Nada para reclamar ahora.\n\n"
                f"{MSG_TIP_INICIACION_AL_RECLAMAR}\n\n"
                "Para **diaria** / **semanal**: `?diaria` · `?semanal` · `?progreso` o los slash `/aat-progreso-*`."
            )
            if hint:
                msg = f"{msg}\n\n{hint}"
            await ctx.send(msg)

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
            "**En este canal (todos lo ven):** `?progreso` · `?diaria` · `?semanal` · `?inicial` · `?reclamar`\n"
            "**Por slash (también sirve en #general):** `/aat-progreso-iniciacion` · `/aat-progreso-diaria` · "
            "`/aat-progreso-semanal` · `/aat-reclamar`\n\n"
            "Tip: si querés reclamar **solo** un tipo con slash, usá `/aat-reclamar` eligiendo "
            "`inicial` / `diaria` / `semanal` / `semanal_especial` / `semanal_minijuegos`.\n"
            "Guía completa en embeds: `?ayuda` / `?guia` / `/aat-guia`. Interactiva (solo vos): `/aat-ayuda`."
        )
        await ctx.send(embeds=[e0, extra])

    @commands.command(name="guia", aliases=["guía"])
    async def guia(self, ctx: commands.Context):
        """Guía larga (embeds): puntos, recompensas, tienda, cartas, comandos. También: `/aat-guia`; con botones: `/aat-ayuda`."""
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
