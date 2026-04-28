# cogs/economia/minijuegos_cog.py
from __future__ import annotations

import json
import logging
import os
import random
from typing import Any, Dict, Literal, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

# Tiempo máximo para que el retado acepte (roll o duelo); al vencer se devuelve la apuesta y se avisa en el canal.
RETO_ACCEPT_MINUTES = 5
RETO_ACCEPT_TTL_SEC = RETO_ACCEPT_MINUTES * 60

# Tras aceptar piedra/papel/tijera, tiempo para elegir (cada uno en `/aat-rps-elegir`, solo vos lo ves).
RPS_PICK_TTL_SEC = max(60, min(900, int(os.getenv("RPS_PICK_SECONDS", "240") or 240)))


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
                kind = str(row.get("kind") or "")
                stake = int(row.get("stake") or 0)
                p1, p2 = int(row["p1_id"]), int(row["p2_id"])
                if kind in ("rps_bet", "rps_casual"):
                    pl = {}
                    try:
                        pl = json.loads(row.get("payload") or "{}")
                    except Exception:
                        pass
                    if kind == "rps_bet":
                        if str(pl.get("phase")) == "pick":
                            self.db.modify_points(p1, stake, gastar=False)
                            self.db.modify_points(p2, stake, gastar=False)
                        elif stake > 0:
                            self.db.modify_points(p1, stake, gastar=False)
                    self.db.minijuego_invite_resolve(int(row["id"]), "expired")
                    await self._post_reto_expired_message(row)
                    continue
                if stake > 0:
                    self.db.modify_points(p1, stake, gastar=False)
                self.db.minijuego_invite_resolve(int(row["id"]), "expired")
                await self._post_reto_expired_message(row)
        except Exception:
            log.exception("expire minijuegos")

    @_expire_loop.before_loop
    async def _expire_before(self):
        await self.bot.wait_until_ready()

    async def _display_name_uid(self, user_id: int) -> str:
        u = self.bot.get_user(user_id)
        if u is None:
            try:
                u = await self.bot.fetch_user(user_id)
            except (discord.NotFound, discord.HTTPException):
                return f"ID {user_id}"
        return u.display_name

    async def _post_reto_expired_message(self, row: Dict[str, Any]) -> None:
        """Aviso público en el canal donde se lanzó el reto (el retado no aceptó a tiempo)."""
        gid = int(row["guild_id"])
        cid = int(row["channel_id"])
        guild = self.bot.get_guild(gid)
        if guild is None:
            return
        ch = guild.get_channel(cid)
        if ch is None:
            try:
                ch = await guild.fetch_channel(cid)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        if not isinstance(ch, discord.abc.Messageable):
            return

        p1, p2 = int(row["p1_id"]), int(row["p2_id"])
        n1 = discord.utils.escape_markdown(await self._display_name_uid(p1))
        n2 = discord.utils.escape_markdown(await self._display_name_uid(p2))
        kind = str(row.get("kind") or "")
        stake = int(row.get("stake") or 0)
        mins = RETO_ACCEPT_MINUTES

        if kind == "roll_casual":
            body = (
                f"⌛ **{n2}** no aceptó el reto roll **sin apuesta** de **{n1}** a tiempo (**{mins} min**). "
                f"*Se canceló; nadie gana ni pierde nada.*"
            )
        elif kind == "roll_bet":
            body = (
                f"⌛ **{n2}** no aceptó el reto roll con apuesta de **{n1}** a tiempo (**{mins} min**). "
                f"La apuesta (**{stake}** pts) ya quedó **devuelta** al retador."
            )
        elif kind == "duel":
            body = (
                f"⌛ **{n2}** no aceptó el **duelo** de **{n1}** a tiempo (**{mins} min**). "
                f"La apuesta (**{stake}** pts) ya quedó **devuelta** al retador."
            )
        elif kind in ("rps_bet", "rps_casual"):
            pl = {}
            try:
                pl = json.loads(row.get("payload") or "{}")
            except Exception:
                pass
            if str(pl.get("phase")) == "pick":
                body = (
                    f"⌛ **Piedra/papel/tijera** entre **{n1}** y **{n2}** — nadie eligió a tiempo. "
                    f"*Si había apuesta, quedó devuelta.*"
                )
            elif kind == "rps_casual":
                body = (
                    f"⌛ **{n2}** no aceptó el **piedra/papel/tijera** (sin apuesta) de **{n1}** a tiempo (**{mins} min**)."
                )
            else:
                body = (
                    f"⌛ **{n2}** no aceptó el **piedra/papel/tijera** con apuesta de **{n1}** a tiempo (**{mins} min**). "
                    f"La apuesta (**{stake}** pts) ya quedó **devuelta** al retador."
                )
        else:
            body = (
                f"⌛ **{n2}** no respondió a tiempo al reto de **{n1}** (**{mins} min**). Invitación cancelada."
            )

        try:
            await ch.send(
                body,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            log.warning("No se pudo publicar aviso de reto expirado (canal %s)", cid)

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
            ttl_sec=RETO_ACCEPT_TTL_SEC,
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
                self.db.mark_diaria_minijuego_hecho(uid, "dia_roll_casual")
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
        self.db.mark_diaria_minijuego_hecho(p1, "dia_roll_bet")
        self.db.mark_diaria_minijuego_hecho(accepter.id, "dia_roll_bet")
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
                f"— **{RETO_ACCEPT_MINUTES} min** para aceptar; si no, se cancela."
            )
        else:
            txt = (
                f"🎲 Reto a {oponente.mention}: apuesta **{apuesta}** pts c/u en un roll 1–100.\n"
                f"{oponente.mention}: **`/aat-roll-aceptar`** o **`?rollpaceptar`** "
                f"— **{RETO_ACCEPT_MINUTES} min**; si no aceptás, se devuelve la apuesta al retador."
            )
        await ctx.send(
            txt,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    async def roll_aceptar_desde_prefijo(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await ctx.send("Solo en servidor.", delete_after=8)
            return
        row = self.db.minijuego_invite_pending_for_target_kinds(ctx.author.id, ("roll_bet", "roll_casual"))
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
        self.db.mark_diaria_minijuego_hecho(interaction.user.id, "dia_roll_casual")

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
                f"— **{RETO_ACCEPT_MINUTES} min** para aceptar; si no, se cancela."
            )
        else:
            txt = (
                f"🎲 Reto a {oponente.mention}: apuesta **{a}** pts c/u en un roll 1–100.\n"
                f"{oponente.mention}: **`/aat-roll-aceptar`** o **`?rollpaceptar`** "
                f"— **{RETO_ACCEPT_MINUTES} min**; si no aceptás, se devuelve la apuesta al retador."
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
        row = self.db.minijuego_invite_pending_for_target_kinds(interaction.user.id, ("roll_bet", "roll_casual"))
        if not row:
            return await interaction.response.send_message("No tenés retos de roll pendientes.", ephemeral=True)
        ok, msg = await self._roll_aceptar_resolver(row, interaction.user)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        await interaction.response.send_message(
            msg,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    # --- Piedra / papel / tijera (elección oculta con slash o ?ppselegir) ---
    @staticmethod
    def _norm_rps_choice(s: str) -> Optional[str]:
        t = (s or "").strip().lower()
        m = {
            "p": "papel",
            "papel": "papel",
            "paper": "papel",
            "r": "piedra",
            "piedra": "piedra",
            "rock": "piedra",
            "s": "tijera",
            "tijera": "tijera",
            "tijeras": "tijera",
            "scissors": "tijera",
        }
        return m.get(t)

    @staticmethod
    def _rps_outcome(a: str, b: str) -> int:
        """0 empate; 1 gana p1; 2 gana p2."""
        if a == b:
            return 0
        win = {("piedra", "tijera"), ("tijera", "papel"), ("papel", "piedra")}
        if (a, b) in win:
            return 1
        if (b, a) in win:
            return 2
        return 0

    def _rps_crear_invite(self, guild_id: int, channel_id: int, p1: int, p2: int, apuesta: int) -> None:
        if apuesta > 0:
            self.db.modify_points(p1, apuesta, gastar=True)
            kind = "rps_bet"
        else:
            kind = "rps_casual"
        self.db.minijuego_invite_create(
            kind,
            guild_id,
            channel_id,
            p1,
            p2,
            apuesta,
            json.dumps({}),
            ttl_sec=RETO_ACCEPT_TTL_SEC,
        )

    async def _rps_aceptar_begin_pick(self, row: dict, accepter: discord.Member) -> Tuple[bool, str]:
        kind = str(row.get("kind") or "")
        if kind not in ("rps_bet", "rps_casual"):
            return False, "No tenés **piedra/papel/tijera** pendiente."
        stake = int(row["stake"])
        p1 = int(row["p1_id"])
        if int(row["p2_id"]) != accepter.id:
            return False, "No tenés **piedra/papel/tijera** pendiente para vos."

        if kind == "rps_bet":
            eco = self.db.get_user_economy(accepter.id)
            if eco["puntos_actuales"] < stake:
                return False, "No te alcanza la apuesta para aceptar."
            self.db.modify_points(accepter.id, stake, gastar=True)

        pl = {"phase": "pick", "p1": None, "p2": None}
        self.db.minijuego_invite_update_row(int(row["id"]), json.dumps(pl), time.time() + RPS_PICK_TTL_SEC)

        return True, ""

    async def _rps_announce_to_invite_channel(self, row: dict, pub: str) -> None:
        gid, cid = int(row["guild_id"]), int(row["channel_id"])
        g = self.bot.get_guild(gid)
        ch = g.get_channel(cid) if g else None
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(
                    pub,
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
            except Exception:
                log.warning("rps: no se pudo publicar resultado en canal %s", cid, exc_info=True)

    async def _rps_apply_pick(self, member: discord.Member, choice_raw: str) -> Tuple[bool, str]:
        choice_n = self._norm_rps_choice(choice_raw)
        if not choice_n:
            return False, "Usá **piedra**, **papel** o **tijera**."

        row = self.db.minijuego_invite_pending_rps_for_user(member.id)
        if not row:
            return False, "No tenés ningún **piedra/papel/tijera** en curso."

        try:
            pl = json.loads(row.get("payload") or "{}")
        except Exception:
            pl = {}

        if str(pl.get("phase")) != "pick":
            return False, "Primero tiene que **aceptar** el rival (`/aat-rps-aceptar` / `?ppsaceptar`)."

        p1, p2 = int(row["p1_id"]), int(row["p2_id"])
        if member.id not in (p1, p2):
            return False, "No sos parte de esta partida."

        stake = int(row["stake"] or 0)
        kind = str(row.get("kind") or "")
        slot = "p1" if member.id == p1 else "p2"

        if pl.get(slot):
            return False, "Ya registramos tu jugada — esperá al rival."

        pl[slot] = choice_n
        invite_id = int(row["id"])
        self.db.minijuego_invite_update_row(invite_id, json.dumps(pl))

        emoji_ok = {"piedra": "🪨", "papel": "📄", "tijera": "✂️"}

        if not pl.get("p1") or not pl.get("p2"):
            return (
                True,
                f"{emoji_ok.get(choice_n, '✓')} Guardado (**solo vos** lo viste). Esperando al rival…",
            )

        a, b = str(pl["p1"]), str(pl["p2"])
        out = self._rps_outcome(a, b)
        self.db.minijuego_invite_resolve(invite_id, "done")
        self.db.mark_diaria_minijuego_hecho(p1, "dia_rps")
        self.db.mark_diaria_minijuego_hecho(p2, "dia_rps")

        u1 = self.bot.get_user(p1) or await self.bot.fetch_user(p1)
        u2 = self.bot.get_user(p2) or await self.bot.fetch_user(p2)

        label = {"piedra": "Piedra", "papel": "Papel", "tijera": "Tijera"}
        em = {"piedra": "🪨", "papel": "📄", "tijera": "✂️"}
        la = f'{em.get(a, "")} {label.get(a, a)}'.strip()
        lb = f'{em.get(b, "")} {label.get(b, b)}'.strip()

        self.db.mark_minijuego_semanal(p1, "mg_rps")
        self.db.mark_minijuego_semanal(p2, "mg_rps")

        if out == 0:
            if kind == "rps_bet" and stake > 0:
                self.db.modify_points(p1, stake, gastar=False)
                self.db.modify_points(p2, stake, gastar=False)
            pub = (
                f"✂️ **Piedra / papel / tijera** — **{u1.display_name}**: {la} vs **{u2.display_name}**: {lb}.\n"
                f"🤝 **Empate** — nadie pierde puntos."
            )
            await self._rps_announce_to_invite_channel(row, pub)
            return True, "Empate — mirá el canal donde empezó el reto."

        winner = p1 if out == 1 else p2
        if kind == "rps_bet" and stake > 0:
            pot = stake * 2
            self.db.modify_points(winner, pot, gastar=False)
            pub = (
                f"✂️ **Piedra / papel / tijera** — **{u1.display_name}**: {la} vs **{u2.display_name}**: {lb}.\n"
                f"🏆 Gana <@{winner}> (**{pot}** pts)."
            )
        else:
            pub = (
                f"✂️ **Piedra / papel / tijera** — **{u1.display_name}**: {la} vs **{u2.display_name}**: {lb}.\n"
                f"🏆 Gana <@{winner}> (sin puntos)."
            )
        await self._rps_announce_to_invite_channel(row, pub)
        return True, "Partida cerrada — resultado en el canal del reto."

    async def rps_reto_desde_prefijo(self, ctx: commands.Context, oponente: discord.Member, apuesta: int) -> None:
        err = self._roll_retar_validar(ctx.guild, ctx.author, oponente, apuesta)
        if err:
            await ctx.send(err, delete_after=12)
            return
        assert ctx.guild is not None
        self._rps_crear_invite(ctx.guild.id, ctx.channel.id, ctx.author.id, oponente.id, apuesta)
        if apuesta == 0:
            txt = (
                f"✂️ Reto **piedra/papel/tijera** (sin puntos) a {oponente.mention}.\n"
                f"{oponente.mention}: **`/aat-rps-aceptar`** o **`?ppsaceptar`** "
                f"— **{RETO_ACCEPT_MINUTES} min**."
            )
        else:
            txt = (
                f"✂️ Reto **piedra/papel/tijera** con apuesta **{apuesta}** pts c/u a {oponente.mention}.\n"
                f"{oponente.mention}: **`/aat-rps-aceptar`** o **`?ppsaceptar`** "
                f"— **{RETO_ACCEPT_MINUTES} min** (si no aceptás, se devuelve la apuesta al retador)."
            )
        await ctx.send(
            txt,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    async def rps_aceptar_desde_prefijo(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await ctx.send("Solo en servidor.", delete_after=8)
            return
        row = self.db.minijuego_invite_pending_for_target_kinds(ctx.author.id, ("rps_bet", "rps_casual"))
        if not row:
            # Ayuda: muchas veces el usuario tiene otro reto pendiente o el reto no era hacia él.
            any_row = self.db.minijuego_invite_pending_for_target(ctx.author.id)
            if any_row:
                kind = str(any_row.get("kind") or "")
                p1 = int(any_row.get("p1_id") or 0)
                mins = RETO_ACCEPT_MINUTES
                await ctx.send(
                    (
                        "No tenés un **PPT** pendiente para aceptar.\n"
                        f"📌 Pero sí tenés un reto pendiente de tipo **{kind}** de <@{p1}> "
                        f"(tenés **{mins} min** desde que te retaron)."
                    ),
                    delete_after=16,
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
            else:
                await ctx.send(
                    "No tenés piedra/papel/tijera pendiente. Asegurate de que **te hayan retado a vos** (te tiene que mencionar).",
                    delete_after=14,
                )
            return
        ok, err = await self._rps_aceptar_begin_pick(row, ctx.author)
        if not ok:
            await ctx.send(err, delete_after=14)
            return
        p1 = int(row["p1_id"])
        u1 = self.bot.get_user(p1) or await self.bot.fetch_user(p1)
        sec = RPS_PICK_TTL_SEC
        await ctx.send(
            (
                f"✂️ **{u1.display_name}** vs **{ctx.author.display_name}** — cada uno elegí **en privado** "
                f"(solo vos lo ves): **`/aat-rps-elegir`** o **`?ppselegir papel`**… "
                f"Tenés **~{sec // 60} min**."
            ),
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    async def rps_elegir_desde_prefijo(self, ctx: commands.Context, *, eleccion: str) -> None:
        ok, ephem = await self._rps_apply_pick(ctx.author, eleccion)
        await ctx.send(ephem, delete_after=20 if ok else 12)

    @app_commands.command(
        name="aat-rps-retar",
        description="Piedra/papel/tijera vs otro. Con apuesta: ambos pagan; con 0: sin puntos. Luego /aat-rps-elegir (oculto).",
    )
    @app_commands.describe(
        oponente="Rival",
        apuesta="Puntos c/u (1–5000) o **0** = sin puntos.",
    )
    async def aat_rps_retar(
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
        self._rps_crear_invite(
            interaction.guild.id,
            interaction.channel_id,
            interaction.user.id,
            oponente.id,
            int(apuesta),
        )
        a = int(apuesta)
        if a == 0:
            txt = (
                f"✂️ Reto **piedra/papel/tijera** (sin puntos) a {oponente.mention}.\n"
                f"{oponente.mention}: **`/aat-rps-aceptar`** — **{RETO_ACCEPT_MINUTES} min**."
            )
        else:
            txt = (
                f"✂️ Reto **piedra/papel/tijera** apuesta **{a}** pts c/u a {oponente.mention}.\n"
                f"{oponente.mention}: **`/aat-rps-aceptar`** — **{RETO_ACCEPT_MINUTES} min**."
            )
        await interaction.response.send_message(
            txt,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    @app_commands.command(name="aat-rps-aceptar", description="Aceptás un reto de piedra/papel/tijera pendiente.")
    async def aat_rps_aceptar(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Solo en servidor.", ephemeral=True)
        row = self.db.minijuego_invite_pending_for_target_kinds(interaction.user.id, ("rps_bet", "rps_casual"))
        if not row:
            any_row = self.db.minijuego_invite_pending_for_target(interaction.user.id)
            if any_row:
                kind = str(any_row.get("kind") or "")
                p1 = int(any_row.get("p1_id") or 0)
                return await interaction.response.send_message(
                    f"No tenés un **PPT** pendiente. Pero sí tenés un reto pendiente **{kind}** de <@{p1}>.",
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
            return await interaction.response.send_message(
                "No tenés piedra/papel/tijera pendiente.",
                ephemeral=True,
            )
        ok, err = await self._rps_aceptar_begin_pick(row, interaction.user)
        if not ok:
            return await interaction.response.send_message(err, ephemeral=True)
        p1 = int(row["p1_id"])
        u1 = self.bot.get_user(p1) or await self.bot.fetch_user(p1)
        sec = RPS_PICK_TTL_SEC
        await interaction.response.send_message(
            (
                f"✅ Reto aceptado. **{u1.display_name}** vs vos — cada uno: **`/aat-rps-elegir`** "
                f"(solo vos ves tu jugada) o `?ppselegir …`. ~**{sec // 60} min**."
            ),
            ephemeral=True,
        )
        try:
            ch = interaction.guild.get_channel(int(row["channel_id"]))
            if isinstance(ch, discord.TextChannel):
                await ch.send(
                    (
                        f"✂️ **{u1.display_name}** vs **{interaction.user.display_name}** — "
                        f"elegí en **privado**: `/aat-rps-elegir` · `?ppselegir …` (~{sec // 60} min)."
                    ),
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
        except Exception:
            log.warning("rps: no se pudo avisar en canal", exc_info=True)

    @app_commands.command(
        name="aat-rps-elegir",
        description="Tu jugada de piedra/papel/tijera (solo vos la ves) cuando hay partida en curso.",
    )
    @app_commands.describe(opcion="Qué jugás")
    async def aat_rps_elegir(
        self,
        interaction: discord.Interaction,
        opcion: Literal["piedra", "papel", "tijera"],
    ):
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Solo en servidor.", ephemeral=True)
        ok, ephem = await self._rps_apply_pick(interaction.user, opcion)
        await interaction.response.send_message(ephem, ephemeral=True)

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
            ttl_sec=RETO_ACCEPT_TTL_SEC,
        )
        await interaction.response.send_message(
            f"⚔️ {oponente.mention}: **duelo** por **{apuesta}** pts. Predicción del retador: **{prediccion}**.\n"
            f"Usá **`/aat-duelo-aceptar`** con tu `carta_id` (**{RETO_ACCEPT_MINUTES} min** o se cancela y se devuelve la apuesta).",
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
        row = self.db.minijuego_invite_pending_for_target_kinds(interaction.user.id, ("duel",))
        if not row:
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
