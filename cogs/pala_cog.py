from __future__ import annotations

import random
import re
import time
from collections import defaultdict, deque
from typing import Deque, Dict

import discord
from discord.ext import commands


_PALA_RE = re.compile(r"(?i)\bpala\b")

# 30 respuestas (humor “trabajo / la pala”).
_PALA_LINES = [
    "¿La… *pala*? No, no, acá somos 100% **home office** de la consciencia.",
    "Shhh… no digas *pala* tan fuerte que aparece un Jira nuevo.",
    "Dijiste **pala** y mi Wi‑Fi se desconectó de forma preventiva.",
    "La pala me da alergia. Es mi debilidad tipo Pokémon.",
    "¿Pala? Yo uso `Ctrl+Z` y rezos. No sé de qué hablás.",
    "Me asusté: pensé que era “palabra clave: laburar”.",
    "La pala está baneada por exceso de productividad.",
    "Pala detectada. Activando modo: *me hago el ocupado*.",
    "No me amenaces con herramientas de trabajo, por favor.",
    "¿Pala? En esta economía solo acepto **roll** y **oráculo**.",
    "La pala me mira… y yo miro para otro lado.",
    "Si aparece la pala, yo me convierto en *archivo .zip*.",
    "La pala trae recuerdos… de lunes.",
    "Pala = reunión que pudo ser un mensaje.",
    "La pala no me asusta… me **deprime**.",
    "¿Quién invocó la pala? Acabo de perder 10 puntos de motivación.",
    "La pala es un mito urbano creado por Recursos Humanos.",
    "Me dijeron “pala” y automáticamente busqué el botón de *silenciar canal*.",
    "Pala… ok, me voy a “responder emails” (mentira).",
    "La pala me pegó un susto: ya estaba por abrir el Excel.",
    "No quiero ver pala, quiero ver **feriado**.",
    "La pala apareció y el café se enfrió solo.",
    "Pala en el chat = sprint nuevo. Qué miedo.",
    "¿Pala? Yo soy más de “hacerlo mañana”.",
    "La pala no. La pala no. La pala no. (mantra).",
    "Dijeron pala y se me actualizó el LinkedIn.",
    "Pala detectada: iniciando protocolo “se cayó el sistema”.",
    "La pala es como el despertador: nadie la quiere, pero llega igual.",
    "Si vas a traer la pala, traé también un aumento.",
    "Me asusto con la pala, pero con el sueldo me calmo.",
]


class PalaCog(commands.Cog, name="Pala"):
    """
    Responde con humor cuando alguien escribe “pala”.
    Incluye cooldown suave para evitar spam.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._times: Dict[int, Deque[float]] = defaultdict(deque)  # user_id → timestamps

    def _cooldown_retry_after(self, user_id: int) -> float:
        # Máx 2 respuestas por 25s por usuario.
        window = 25.0
        rate = 2
        now = time.monotonic()
        dq = self._times[user_id]
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= rate:
            return max(0.1, window - (now - dq[0]))
        return 0.0

    def _mark(self, user_id: int) -> None:
        self._times[user_id].append(time.monotonic())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        content = message.content or ""
        if not content:
            return
        # Evitar disparar por comandos.
        if content.lstrip().startswith(("?", "/")):
            return
        if not _PALA_RE.search(content):
            return
        wait = self._cooldown_retry_after(message.author.id)
        if wait > 0:
            return
        self._mark(message.author.id)
        try:
            await message.reply(random.choice(_PALA_LINES), mention_author=False)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PalaCog(bot))

