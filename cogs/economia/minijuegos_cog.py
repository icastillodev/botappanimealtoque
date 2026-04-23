# cogs/economia/minijuegos_cog.py
from __future__ import annotations

import json
import logging
import os
import random
from typing import Literal, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger(__name__)


class MinijuegosCog(commands.Cog, name="Economia Minijuegos"):
    """Roll casual, apuesta por roll 1–100, duelo por poder+carta, voto semanal."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.economia_db
        self.card_db = bot.card_db
        self.task_config = bot.task_config
        self.voto_a = os.getenv("VOTO_SEMANAL_OPCION_A", "Opción A")
        self.voto_b = os.getenv("VOTO_SEMANAL_OPCION_B", "Opción B")

    def cog_unload(self):
        self._expire_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._expire_loop.is_running():
            self._expire_loop.start()

    @tasks.loop(seconds=45)
    async def _expire_loop(self):
        try:
            for row in self.db.minijuego_fetch_expired_pending():
                self.db.modify_points(int(row["p1_id"]), int(row["stake"]), gastar=False)
                self.db.minijuego_invite_resolve(int(row["id"]), "expired")
        except Exception:
            log.exception("expire minijuegos")

    @_expire_loop.before_loop
    async def _expire_before(self):
        await self.bot.wait_until_ready()

    def _rw(self) -> dict:
        return self.task_config.get("rewards", {})

    def _duelos_enabled(self) -> bool:
        raw = (os.getenv("ENABLE_DUELOS", "0") or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _roll_retar_validar(
        self, guild: Optional[discord.Guild], p1: discord.abc.User, p2: discord.Member, apuesta: int
    ) -> Optional[str]:
        """None = OK. str = mensaje de error para el usuario."""
        if not guild:
            return "Solo en servidor."
        if p2.id == p1.id or p2.bot:
            return "Elegí a otro usuario humano."
        if apuesta < 0 or apuesta > 5000:
            return "Apuesta entre 1 y 5000 (o 0 para roll sin puntos)."
        if self.db.minijuego_invite_pending_for_target(p2.id):
            return "Esa persona ya tiene un reto pendiente."
        if apuesta > 0:
            eco = self.db.get_user_economy(p1.id)
            if eco["puntos_actuales"] < apuesta:
                return "No tenés puntos suficientes."
        return None

    def _roll_retar_crear_invite(
        self, guild_id: int, channel_id: int, p1_id: int, p2_id: int, apuesta: int
    ) -> None:
        if apuesta > 0:
            self.db.modify_points(p1_id, apuesta, gastar=True)
            kind = "roll_bet"
        else:
            kind = "roll_casual"
        self.db.minijuego_invite_create(
            kind,
            guild_id,
            channel_id,
            p1_id,
            p2_id,
            apuesta,
            json.dumps({}),
            ttl_sec=420,
        )

    async def _roll_aceptar_resolver(self, row: dict, accepter: discord.Member) -> Tuple[bool, str]:
        """(True, mensaje público) o (False, mensaje ephemeral de error)."""
        kind = row.get("kind")
        if kind not in ("roll_bet", "roll_casual"):
            return False, "No tenés retos de roll pendientes."
        stake = int(row["stake"])
        p1 = int(row["p1_id"])
        if int(row["p2_id"]) != accepter.id:
            return False, "No tenés retos de roll pendientes."

        if kind == "roll_casual":
            r1, r2 = 0, 0
            while r1 == r2:
                r1 = random.randint(1, 100)
                r2 = random.randint(1, 100)
            winner = p1 if r1 > r2 else accepter.id
            self.db.minijuego_invite_resolve(int(row["id"]), "done")
            for uid in (p1, accepter.id):
                prog = self.db.get_progress_semanal(uid)
                if int(prog.get("mg_roll_casual") or 0) == 0:
                    self.db.mark_minijuego_semanal(uid, "mg_roll_casual")
            u1 = self.bot.get_user(p1) or await self.bot.fetch_user(p1)
            msg = (
                f"🎲 **Roll amistoso** — {u1.display_name}: **{r1}** vs {accepter.display_name}: **{r2}**.\n"
                f"🏆 Gana <@{winner}> (sin puntos)."
            )
            return True, msg

        eco = self.db.get_user_economy(accepter.id)
        if eco["puntos_actuales"] < stake:
            return False, "No te alcanza la apuesta para aceptar."
        self.db.modify_points(accepter.id, stake, gastar=True)
        r1, r2 = 0, 0
        while r1 == r2:
            r1 = random.randint(1, 100)
            r2 = random.randint(1, 100)
        winner = p1 if r1 > r2 else accepter.id
        pot = stake * 2
        self.db.modify_points(winner, pot, gastar=False)
        self.db.minijuego_invite_resolve(int(row["id"]), "done")
        self.db.mark_minijuego_semanal(p1, "mg_ret_roll_apuesta")
        self.db.mark_minijuego_semanal(accepter.id, "mg_ret_roll_apuesta")
        u1 = self.bot.get_user(p1) or await self.bot.fetch_user(p1)
        msg = (
            f"🎲 **Roll bet** — {u1.display_name}: **{r1}** vs {accepter.display_name}: **{r2}**.\n"
            f"🏆 Gana <@{winner}> y se lleva **{pot}** pts."
        )
        return True, msg

    async def roll_reto_desde_prefijo(self, ctx: commands.Context, oponente: discord.Member, apuesta: int) -> None:
        """`?rollp` (apuesta=0) o `?rollc` (apuesta>0)."""
        err = self._roll_retar_validar(ctx.guild, ctx.author, oponente, apuesta)
        if err:
            await ctx.send(err, delete_after=12)
            return
        assert ctx.guild is not None
        self._roll_retar_crear_invite(ctx.guild.id, ctx.channel.id, ctx.author.id, oponente.id, apuesta)
        if apuesta == 0:
            txt = (
                f"🎲 Reto **sin apuesta** a {oponente.mention}: el mayor en 1–100 gana (solo honor).\n"
                f"{oponente.mention}: **`/aat-roll-aceptar`** o **`?rollpaceptar`** "
                f"(si no aceptás, el reto expira sin costo)."
            )
        else:
            txt = (
                f"🎲 Reto a {oponente.mention}: apuesta **{apuesta}** pts c/u en un roll 1–100.\n"
                f"{oponente.mention}: **`/aat-roll-aceptar`** o **`?rollpaceptar`** "
                f"(o ignorá: expira y se devuelve la apuesta del retador)."
            )
        await ctx.send(
            txt,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    async def roll_aceptar_desde_prefijo(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await ctx.send("Solo en servidor.", delete_after=8)
            return
        row = self.db.minijuego_invite_pending_for_target(ctx.author.id)
        if not row:
            await ctx.send("No tenés retos de roll pendientes.", delete_after=12)
            return
        ok, msg = await self._roll_aceptar_resolver(row, ctx.author)
        if not ok:
            await ctx.send(msg, delete_after=12)
            return
        await ctx.send(
            msg,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    # --- Roll casual (marca tarea semanal una vez) ---
    @app_commands.command(name="aat-roll", description="Tira dados entre dos números (casual). Cuenta 1 vez por semana para la tarea de minijuegos.")
    @app_commands.describe(minimo="Mínimo inclusive", maximo="Máximo inclusive")
    async def aat_roll(self, interaction: discord.Interaction, minimo: int = 1, maximo: int = 100):
        if minimo >= maximo:
            return await interaction.response.send_message("El máximo debe ser mayor que el mínimo.", ephemeral=True)
        if maximo - minimo > 500:
            return await interaction.response.send_message("Rango máximo 500.", ephemeral=True)
        r = random.randint(minimo, maximo)
        prog = self.db.get_progress_semanal(interaction.user.id)
        if int(prog.get("mg_roll_casual") or 0) == 0:
            self.db.mark_minijuego_semanal(interaction.user.id, "mg_roll_casual")
        await interaction.response.send_message(f"🎲 **{interaction.user.display_name}** sacó **{r}** ({minimo}–{maximo}).")

    # --- Roll 1–100 vs otra persona (con o sin apuesta) ---
    @app_commands.command(
        name="aat-roll-retar",
        description="Retá a alguien a un roll 1–100. Con apuesta: ambos pagan y gana el mayor; con 0: sin puntos.",
    )
    @app_commands.describe(
        oponente="A quién retás",
        apuesta="Puntos que arriesgan ambos (1–5000), o **0** = roll amistoso sin puntos.",
    )
    async def aat_roll_retar(
        self,
        interaction: discord.Interaction,
        oponente: discord.Member,
        apuesta: app_commands.Range[int, 0, 5000] = 0,
    ):
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Solo en servidor.", ephemeral=True)
        err = self._roll_retar_validar(interaction.guild, interaction.user, oponente, int(apuesta))
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        assert interaction.guild is not None
        self._roll_retar_crear_invite(
            interaction.guild.id,
            interaction.channel_id,
            interaction.user.id,
            oponente.id,
            int(apuesta),
        )
        a = int(apuesta)
        if a == 0:
            txt = (
                f"🎲 Reto **sin apuesta** a {oponente.mention}: el mayor en 1–100 gana (solo honor).\n"
                f"{oponente.mention}: **`/aat-roll-aceptar`** o **`?rollpaceptar`** "
                f"(si no aceptás, el reto expira sin costo)."
            )
        else:
            txt = (
                f"🎲 Reto a {oponente.mention}: apuesta **{a}** pts c/u en un roll 1–100.\n"
                f"{oponente.mention}: **`/aat-roll-aceptar`** o **`?rollpaceptar`** "
                f"(o ignorá: expira y se devuelve la apuesta del retador)."
            )
        await interaction.response.send_message(
            txt,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    @app_commands.command(
        name="aat-roll-aceptar",
        description="Aceptás un reto de roll pendiente (con apuesta o amistoso).",
    )
    async def aat_roll_aceptar(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Solo en servidor.", ephemeral=True)
        row = self.db.minijuego_invite_pending_for_target(interaction.user.id)
        if not row:
            return await interaction.response.send_message("No tenés retos de roll pendientes.", ephemeral=True)
        ok, msg = await self._roll_aceptar_resolver(row, interaction.user)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        await interaction.response.send_message(
            msg,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    # --- Duelo por poder + dado ---
    @app_commands.command(
        name="aat-duelo-retar",
        description="Duelo: apostás puntos y elegís carta + si tu total (poder+dado) será mayor o menor que el del rival.",
    )
    @app_commands.rename(carta_id="carta-id")
    @app_commands.describe(
        oponente="Rival",
        apuesta="Puntos c/u",
        carta_id="Tu carta (ID inventario)",
        prediccion="Mayor = creés ganar por arriba; Menor = creés ganar por abajo",
    )
    async def aat_duelo_retar(
        self,
        interaction: discord.Interaction,
        oponente: discord.Member,
        apuesta: int,
        carta_id: str,
        prediccion: Literal["mayor", "menor"],
    ):
        if not self._duelos_enabled():
            return await interaction.response.send_message("⚠️ Los **duelos** están desactivados por el staff.", ephemeral=True)
        if not interaction.guild or not carta_id.isdigit():
            return await interaction.response.send_message("Uso inválido.", ephemeral=True)
        if apuesta < 1 or apuesta > 5000 or oponente.bot or oponente.id == interaction.user.id:
            return await interaction.response.send_message("Datos inválidos.", ephemeral=True)
        if self.db.minijuego_invite_pending_for_target(oponente.id):
            return await interaction.response.send_message("Esa persona ya tiene un reto pendiente.", ephemeral=True)
        eco = self.db.get_user_economy(interaction.user.id)
        if eco["puntos_actuales"] < apuesta:
            return await interaction.response.send_message("Sin puntos suficientes.", ephemeral=True)
        cid = int(carta_id)
        if not self.db.get_card_from_inventory(interaction.user.id, cid):
            return await interaction.response.send_message("No tenés esa carta.", ephemeral=True)
        carta = self.card_db.get_carta_stock_by_id(cid)
        if not carta:
            return await interaction.response.send_message("Carta inválida.", ephemeral=True)
        self.db.modify_points(interaction.user.id, apuesta, gastar=True)
        payload = json.dumps({"p1_card": cid, "guess": prediccion})
        self.db.minijuego_invite_create(
            "duel",
            interaction.guild.id,
            interaction.channel_id,
            interaction.user.id,
            oponente.id,
            apuesta,
            payload,
            ttl_sec=600,
        )
        await interaction.response.send_message(
            f"⚔️ {oponente.mention}: **duelo** por **{apuesta}** pts. Predicción del retador: **{prediccion}**.\n"
            f"Usá **`/aat-duelo-aceptar`** con tu `carta_id`.",
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    @app_commands.command(name="aat-duelo-aceptar", description="Aceptás un duelo pendiente con tu carta.")
    @app_commands.rename(carta_id="carta-id")
    @app_commands.describe(carta_id="ID de tu carta en inventario")
    async def aat_duelo_aceptar(self, interaction: discord.Interaction, carta_id: str):
        if not self._duelos_enabled():
            return await interaction.response.send_message("⚠️ Los **duelos** están desactivados por el staff.", ephemeral=True)
        if not interaction.guild or not carta_id.isdigit():
            return await interaction.response.send_message("Solo en servidor / ID inválido.", ephemeral=True)
        row = self.db.minijuego_invite_pending_for_target(interaction.user.id)
        if not row or row.get("kind") != "duel":
            return await interaction.response.send_message("No hay duelo pendiente para vos.", ephemeral=True)
        stake = int(row["stake"])
        eco = self.db.get_user_economy(interaction.user.id)
        if eco["puntos_actuales"] < stake:
            return await interaction.response.send_message("No alcanza la apuesta.", ephemeral=True)
        p1 = int(row["p1_id"])
        pl = json.loads(row["payload"])
        c1 = int(pl["p1_card"])
        guess = pl["guess"]
        c2 = int(carta_id)
        if not self.db.get_card_from_inventory(interaction.user.id, c2):
            return await interaction.response.send_message("No tenés esa carta.", ephemeral=True)
        carta1 = self.card_db.get_carta_stock_by_id(c1)
        carta2 = self.card_db.get_carta_stock_by_id(c2)
        if not carta1 or not carta2:
            return await interaction.response.send_message("Error de datos de cartas.", ephemeral=True)
        self.db.modify_points(interaction.user.id, stake, gastar=True)
        self.db.use_card_from_inventory(p1, c1)
        self.db.use_card_from_inventory(interaction.user.id, c2)
        d1 = random.randint(1, 60)
        d2 = random.randint(1, 60)
        s1 = int(carta1.get("poder") or 50) + d1
        s2 = int(carta2.get("poder") or 50) + d2
        p1_wins = (guess == "mayor" and s1 > s2) or (guess == "menor" and s1 < s2)
        winner = p1 if p1_wins else interaction.user.id
        pot = stake * 2
        self.db.modify_points(winner, pot, gastar=False)
        self.db.minijuego_invite_resolve(int(row["id"]), "done")
        self.db.mark_minijuego_semanal(p1, "mg_duelo")
        self.db.mark_minijuego_semanal(interaction.user.id, "mg_duelo")
        self.db.mark_minijuego_semanal(p1, "mg_ret_roll_apuesta")
        self.db.mark_minijuego_semanal(interaction.user.id, "mg_ret_roll_apuesta")
        u1 = self.bot.get_user(p1) or await self.bot.fetch_user(p1)
        msg = (
            f"⚔️ **Duelo** {u1.display_name} (`{carta1['nombre']}` p={carta1.get('poder',50)} +🎲{d1}=**{s1}**) vs "
            f"{interaction.user.display_name} (`{carta2['nombre']}` p={carta2.get('poder',50)} +🎲{d2}=**{s2}**).\n"
            f"Apuesta del retador: **{guess}**. 🏆 Gana <@{winner}> (**{pot}** pts)."
        )
        await interaction.response.send_message(msg)

    # --- Voto semanal (domingo / semana ISO) ---
    @app_commands.command(name="aat-voto-semanal", description="Votá en la encuesta semanal del servidor (una vez por semana).")
    @app_commands.describe(opcion="Tu voto")
    async def aat_voto_semanal(self, interaction: discord.Interaction, opcion: Literal["A", "B"]):
        prog = self.db.get_progress_semanal(interaction.user.id)
        if int(prog.get("mg_voto_dom") or 0) >= 1:
            return await interaction.response.send_message("Ya votaste esta semana.", ephemeral=True)
        self.db.mark_minijuego_semanal(interaction.user.id, "mg_voto_dom")
        label = self.voto_a if opcion == "A" else self.voto_b
        await interaction.response.send_message(f"✅ Voto **{opcion}** ({label}) registrado.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MinijuegosCog(bot))
