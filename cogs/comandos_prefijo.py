# Comandos con prefijo ! — visibles para todos en el canal (no ephemeral).
# Los slash / siguen existiendo; esto es atajo y descubribilidad.
from __future__ import annotations

import os
from typing import List, Optional

import discord
from discord.ext import commands

from cogs.economia.db_manager import EconomiaDBManagerV2
from cogs.economia.card_db_manager import CardDBManager
from cogs.economia.cartas_cog import StockCatalogView
from cogs.economia import card_effectos
from cogs.economia.reclamar_service import reclaim_rewards
from cogs.economia.anime_top_cog import _embed_top_for
from cogs.impostor import core as impostor_core
from cogs.impostor import feed as impostor_feed
from cogs.impostor import notify as impostor_notify
from cogs.impostor.engine import PHASE_END


class ComandosPrefijoCog(commands.Cog, name="Comandos Prefijo"):
    """Atajos ! públicos (economía, impostor)."""

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
                "**Con `!` en el canal** (todos lo ven) — atajos abajo.\n"
                "**Con `/`** — versión completa (Discord te autocompleta).\n\n"
                "**Economía:** `!puntos` · `!inventario` · `!top` · `!reclamar` · `!progreso` · "
                "`!diaria` · `!semanal` · `!inicial` · `!abrir` · `!miscartas` · `!catalogo` · `!usar`\n"
                "**Impostor:** `!impostor` — avisá que buscás gente / ver lobbies abiertos.\n"
                "**Oráculo:** arrobá al bot + tu pregunta en el mismo mensaje · `!pregunta` + texto · `/aat_consulta` — sí / no / a veces %. Cuenta para la **diaria** y puntos extra (ver `.env`).\n"
                "**Top anime:** `!animetop` · `!animetop @usuario` — slash: `/aat_anime_top_*`\n"
                "**Perfil:** `/aat_wishlist_*` · `/aat_hated_*` · `/aat_chars_*` (wishlist 1–30, odiados 1–10, personajes 1–10).\n"
                "**Trivia anime:** el bot publica en **#general**; respondé ahí con `!respuestapregunta` + respuesta.\n"
                "**Slash útiles:** `/aat_ayuda` · `/crearsimpostor` · `/entrar` · `/aat_tienda_ver`"
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["puntos"])
    async def puntos_cmd(self, ctx: commands.Context):
        self.db.ensure_user_exists(ctx.author.id)
        eco = self.db.get_user_economy(ctx.author.id)
        embed = discord.Embed(
            title=f"Puntos de {ctx.author.display_name}",
            description=f"**{eco['puntos_actuales']}** puntos · Conseguidos: {eco['puntos_conseguidos']} · Gastados: {eco['puntos_gastados']}",
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
            description=f"Puntos: **{eco['puntos_actuales']}** · Pins: **{eco['creditos_pin']}**\n{lines}",
            color=discord.Color.dark_green(),
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def animetop(self, ctx: commands.Context, quien: Optional[discord.Member] = None):
        """Ver top anime propio o de otro miembro (mismo texto que el slash)."""
        target = quien or ctx.author
        rows = self.db.anime_top_list(target.id)
        emb = _embed_top_for(self.bot, target, rows, viewer_is_target=target.id == ctx.author.id)
        await ctx.send(embed=emb)

    @commands.command(aliases=["rank", "ranking"])
    async def top(self, ctx: commands.Context):
        top_actual = self.db.get_top_users("actual", limit=5)
        text = ""
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, u in enumerate(top_actual):
            try:
                user = self.bot.get_user(u["user_id"]) or await self.bot.fetch_user(u["user_id"])
                name = user.display_name
            except Exception:
                name = "Desconocido"
            text += f"{medals[i]} {name} • **{u['puntos_actuales']}**\n"
        embed = discord.Embed(title="Top 5 puntos actuales", description=text or "Nadie aún.", color=discord.Color.gold())
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
        tr_ok = tr >= 1 or ts >= 2
        or_n = int(prog.get("oraculo_preguntas") or 0)
        or_ok = or_n >= 1
        rw = self.task_config["rewards"]["diaria"]
        desc = (
            f"**Diaria** ({fecha})\n"
            f"• Mensajes servidor: {msg_n}/10\n"
            f"• Reacciones: {rx_n}/3\n"
            f"• Trampa (dirigida o 2 casual): {'OK' if tr_ok else 'pendiente'} ({tr}/1 · {ts}/2)\n"
            f"• Oráculo (1 pregunta): {'OK' if or_ok else 'pendiente'} (@bot / `!pregunta` / `/aat_consulta`)\n"
            f"Premio: **{rw}** pts + 1 blister → `!reclamar`"
        )
        await ctx.send(embed=discord.Embed(title="Progreso diario", description=desc, color=discord.Color.orange()))

    @commands.command(aliases=["weekly", "semanal"])
    async def semanal_cmd(self, ctx: commands.Context):
        _, semana = self.db.get_current_date_keys()
        prog = self.db.get_progress_semanal(user_id := ctx.author.id)
        rw = self.task_config["rewards"]
        desc = (
            f"**Semanal** (semana {semana.split('-')[-1]})\n"
            f"• Foro / media / videos: {prog.get('debate_post',0)}/{prog.get('media_escrito',0)}/{prog.get('videos_reaccion',0)} (cada uno 1)\n"
            f"• Impostor: {int(prog.get('impostor_partidas') or 0)}/3 partidas, victoria impostor: {int(prog.get('impostor_victorias') or 0)}/1\n"
            f"Premio base: **{rw['semanal']}** pts — especial y minijuegos: `/aat_progreso_semanal`"
        )
        await ctx.send(embed=discord.Embed(title="Progreso semanal", description=desc, color=discord.Color.purple()))

    @commands.command(aliases=["starter", "iniciacion"])
    async def inicial(self, ctx: commands.Context):
        prog = self.db.get_progress_inicial(ctx.author.id)
        if prog["completado"] == 1:
            await ctx.send("✅ Iniciación ya reclamada.")
            return
        desc = (
            "• Presentación · autorol país/rol · redes · reglas · 1 mensaje en #general\n"
            f"Premio: **{self.task_config['rewards']['inicial']}** pts + 3 blisters → `!reclamar`"
        )
        await ctx.send(embed=discord.Embed(title="Iniciación", description=desc, color=discord.Color.blue()))

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
            await ctx.send(embed=embed)
        elif err_msgs:
            await ctx.send("\n".join(err_msgs))
        else:
            await ctx.send("Nada para reclamar ahora. `!progreso` o `/aat_progreso_diaria`.")

    @commands.command()
    async def miscartas(self, ctx: commands.Context):
        cartas = self.db.get_cards_in_inventory(ctx.author.id)
        if not cartas:
            await ctx.send("No tenés cartas. Abrí blisters con `!abrir` o `/aat_abrirblister`.")
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
            await ctx.send("Usá: `!usar <id_carta> [@alguien]` (el ID sale en `!miscartas`).")
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

    @usar.error
    async def usar_err(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Esperá {error.retry_after:.0f}s antes de volver a usar `!usar`.", delete_after=8)

    @impostor.error
    async def impostor_err(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Este canal ya tuvo un `!impostor` hace poco. Probá en {error.retry_after:.0f}s o usá la cartelera.",
                delete_after=10,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ComandosPrefijoCog(bot))
