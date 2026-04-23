# Preguntas sí / no (40% sí, 40% no, 20% respuesta con % al azar).
# Cuenta para la diaria + puntos extra (config .env).
from __future__ import annotations

import random
import re
import time
from collections import defaultdict, deque
from typing import Deque, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands


def _roll_oracle() -> Tuple[str, str, int]:
    """
    Devuelve (categoría, texto_respuesta, dado 1-100 usado).
    1-40 sí, 41-80 no, 81-100 probabilístico.
    """
    dado = random.randint(1, 100)
    si_msg = random.choice(
        [
            "Sí.",
            "¡Sí!",
            "Por supuesto que sí.",
            "El cosmos asiente.",
            "Afirmativo.",
            "Totalmente sí.",
        ]
    )
    no_msg = random.choice(
        [
            "No.",
            "¡No!",
            "Ni en pedo (no).",
            "Negativo.",
            "Mejor no contar con eso.",
            "El destino dice que no.",
        ]
    )
    if dado <= 40:
        return "Sí", si_msg, dado
    if dado <= 80:
        return "No", no_msg, dado
    pct = random.randint(5, 95)
    lean_si = random.choice([True, False])
    if lean_si:
        prob_msg = random.choice(
            [
                f"Ni sí ni no… tirando **{pct}%** a favor del **sí**.",
                f"Duda razonable: **{pct}%** de que termine en **sí**.",
                f"Las runas marcan **{pct}%** sí (o algo así).",
            ]
        )
    else:
        prob_msg = random.choice(
            [
                f"Ni sí ni no… **{pct}%** de inclinación al **no**.",
                f"Probabilidad estimada: **{pct}%** hacia el **no**.",
                f"El dado flojo: **{pct}%** no, **{100 - pct}%** sí (o al revés mañana).",
            ]
        )
    return "Probabilidad", prob_msg, dado


class OraculoCog(commands.Cog, name="Oráculo"):
    """Preguntas al bot (sí / no / %)."""

    # Mismo criterio que @commands.cooldown(2, 5, commands.BucketType.user) en !pregunta
    _COOLDOWN_RATE = 2
    _COOLDOWN_PER_SEC = 5.0

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = getattr(bot, "economia_db", None)
        self.task_config = getattr(bot, "task_config", None) or {}
        self._oracle_times: dict[int, Deque[float]] = defaultdict(deque)

    def _oracle_cooldown_retry_after(self, user_id: int) -> float:
        """Si está en cooldown, devuelve segundos restantes; si no, 0."""
        now = time.monotonic()
        dq = self._oracle_times[user_id]
        while dq and dq[0] < now - self._COOLDOWN_PER_SEC:
            dq.popleft()
        if len(dq) >= self._COOLDOWN_RATE:
            return max(0.1, self._COOLDOWN_PER_SEC - (now - dq[0]))
        return 0.0

    def _oracle_mark_use(self, user_id: int) -> None:
        self._oracle_times[user_id].append(time.monotonic())

    def _strip_mentions_for_question(self, content: str) -> str:
        s = re.sub(r"<@!?\d+>", " ", content or "")
        s = re.sub(r"<#\d+>", " ", s)
        return " ".join(s.split()).strip()

    async def _send_oracle_embed(
        self,
        channel: discord.abc.Messageable,
        *,
        author: discord.abc.User,
        nombre_visible: str,
        pregunta: str,
        reference: Optional[discord.Message] = None,
    ) -> None:
        if not self.db:
            await channel.send("Economía no disponible.", reference=reference, mention_author=False)
            return
        self.db.ensure_user_exists(author.id)
        _, body, _ = _roll_oracle()
        self._record_oracle_use(author.id)
        embed = self._embed_respuesta(
            nombre_visible=nombre_visible,
            mencion=author.mention,
            pregunta=pregunta.strip(),
            body=body,
        )
        await channel.send(embed=embed, reference=reference, mention_author=False)

    def _record_oracle_use(self, user_id: int) -> Tuple[int, int, int, int]:
        """
        Suma contador diario y opcionalmente puntos.
        Devuelve (puntos_otorgados, preguntas_hoy_tras_esta, max_con_puntos, pts_por_pregunta).
        """
        if not self.db:
            return 0, 0, 0, 0
        fecha, _ = self.db.get_current_date_keys()
        prog = self.db.get_progress_diaria(user_id)
        n_before = int(prog.get("oraculo_preguntas") or 0)
        rw = (self.task_config.get("rewards") or {})
        per = int(rw.get("oracle_pregunta_points", 3))
        mx = int(rw.get("oracle_max_preguntas_con_puntos", 5))
        gained = 0
        if per > 0 and n_before < mx:
            self.db.modify_points(user_id, per, gastar=False)
            gained = per
        self.db.update_task_diaria(user_id, "oraculo_preguntas", fecha, 1)
        n_after = n_before + 1
        return gained, n_after, mx, per

    def _embed_respuesta(
        self,
        *,
        nombre_visible: str,
        mencion: str,
        pregunta: str,
        body: str,
    ) -> discord.Embed:
        q = (pregunta or "").strip()[:900] or "*(silencio místico)*"
        desc = (
            f"{mencion} **({nombre_visible})** preguntó:\n"
            f"> {q}\n\n"
            f"**La respuesta es:** {body}"
        )
        return discord.Embed(
            title="🔮 Consulta al oráculo",
            description=desc,
            color=discord.Color.dark_magenta(),
        )

    @commands.command(name="pregunta", aliases=["consulta", "8ball", "bola", "oraculo"])
    async def pregunta_prefijo(self, ctx: commands.Context, *, texto: str = None):
        if not texto or not str(texto).strip():
            await ctx.send("Usá: `?pregunta ¿va a salir bien el stream?` (escribí la pregunta después del comando).")
            return
        wait = self._oracle_cooldown_retry_after(ctx.author.id)
        if wait > 0:
            await ctx.send(f"Esperá **{wait:.1f}s** entre consultas al oráculo.", delete_after=6)
            return
        nombre = ctx.author.display_name if isinstance(ctx.author, discord.Member) else str(ctx.author)
        await self._send_oracle_embed(
            ctx.channel,
            author=ctx.author,
            nombre_visible=nombre,
            pregunta=texto.strip(),
            reference=None,
        )
        self._oracle_mark_use(ctx.author.id)

    @app_commands.command(
        name="aat-consulta",
        description="Preguntá al oráculo (sí / no / %). También: @bot + pregunta en el canal o ?pregunta.",
    )
    @app_commands.describe(pregunta="Lo que querés preguntar (sí / no / a veces un porcentaje).")
    async def consulta_slash(self, interaction: discord.Interaction, pregunta: str):
        if not pregunta or not pregunta.strip():
            await interaction.response.send_message("Escribí una pregunta.", ephemeral=True)
            return
        wait = self._oracle_cooldown_retry_after(interaction.user.id)
        if wait > 0:
            await interaction.response.send_message(
                f"Esperá **{wait:.1f}s** entre consultas al oráculo.",
                ephemeral=True,
            )
            return
        if not self.db:
            await interaction.response.send_message("Economía no disponible.", ephemeral=True)
            return
        self.db.ensure_user_exists(interaction.user.id)
        _, body, _ = _roll_oracle()
        self._record_oracle_use(interaction.user.id)
        nombre = interaction.user.display_name
        mencion = interaction.user.mention
        embed = self._embed_respuesta(
            nombre_visible=nombre,
            mencion=mencion,
            pregunta=pregunta.strip(),
            body=body,
        )
        await interaction.response.send_message(embed=embed)
        self._oracle_mark_use(interaction.user.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        me = self.bot.user
        if not me or me not in message.mentions:
            return
        # Evitar doble respuesta si usaron comando con prefijo (el propio handler ya contestó / falló).
        raw = (message.content or "").lstrip()
        if raw.startswith("?"):
            return

        pregunta = self._strip_mentions_for_question(message.content)
        if len(pregunta) < 2:
            try:
                await message.reply(
                    "Escribí la **pregunta** en el mismo mensaje donde me arrobás "
                    f"(ej. {me.mention} ¿va a llover mañana?). También podés usar `?pregunta …` o `/aat-consulta`.",
                    mention_author=False,
                )
            except discord.HTTPException:
                pass
            return

        wait = self._oracle_cooldown_retry_after(message.author.id)
        if wait > 0:
            try:
                await message.reply(
                    f"Esperá **{wait:.1f}s** entre consultas al oráculo.",
                    mention_author=False,
                    delete_after=8,
                )
            except discord.HTTPException:
                pass
            return

        ch = message.channel
        nombre = message.author.display_name if isinstance(message.author, discord.Member) else str(message.author)
        try:
            await self._send_oracle_embed(
                ch,
                author=message.author,
                nombre_visible=nombre,
                pregunta=pregunta,
                reference=message,
            )
            self._oracle_mark_use(message.author.id)
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(OraculoCog(bot))
