# cogs/economia/card_effectos.py
"""Efectos mecánicos al usar cartas: solo Rara / Legendaria (Común = solo narración en el embed)."""
from __future__ import annotations

import datetime
import logging
import random
from typing import TYPE_CHECKING, Any, Dict, Optional

import discord

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

RAREZAS_CON_EFECTO = ("Rara", "Legendaria")


def _rareza_tiene_efecto(carta: Dict[str, Any]) -> bool:
    r = (carta.get("rareza") or "").strip()
    return r in RAREZAS_CON_EFECTO


async def aplicar_efecto_al_usar(
    *,
    carta: Dict[str, Any],
    actor: discord.Member,
    target: Optional[discord.Member],
    channel: discord.abc.Messageable,
) -> None:
    if not _rareza_tiene_efecto(carta):
        return
    fx = (carta.get("efecto") or "").strip()
    if not fx or fx == "Sin efecto.":
        return

    if fx == "MUTE_10_MIN" and target:
        await _timeout(target, 10, f"Carta {carta.get('nombre')}", channel)
    elif fx == "MUTE_5_MIN" and target:
        await _timeout(target, 5, f"Carta {carta.get('nombre')}", channel)
    elif fx == "MUTE_15_MIN" and target:
        await _timeout(target, 15, f"Carta {carta.get('nombre')}", channel)
    elif fx == "BROMA_DM" and target:
        chiste = random.choice(
            [
                "Te acaba de lanzar una carta rara que solo dice: *'mirá el sol de acuario'* 🌟",
                "Un genio en una lámpara pidió 3 deseos… esta carta gastó los 3 en memes.",
                "Alerta: tu aura acaba de ser auditada y salió **imponible de facturar**.",
            ]
        )
        try:
            await target.send(f"🃏 **{actor.display_name}** te envió una broma con *{carta.get('nombre')}*:\n{chiste}")
        except discord.Forbidden:
            if hasattr(channel, "send"):
                await channel.send(f"{target.mention} tenés los DM cerrados; acá va la broma: {chiste}", delete_after=45)
    elif fx == "BROMA_EPHEMERAL" and hasattr(channel, "send"):
        subj = target.mention if target else "el chat entero"
        await channel.send(
            f"{actor.mention} activó *{carta.get('nombre')}* — **{subj}** queda **{random.choice(['bendecido', 'maldito', 'en pausa'])}** 30s.",
            delete_after=30,
        )


async def _timeout(target: discord.Member, minutes: int, reason: str, channel: discord.abc.Messageable) -> None:
    try:
        await target.timeout(datetime.timedelta(minutes=minutes), reason=reason[:450])
        if hasattr(channel, "send"):
            await channel.send(f"{target.mention} — timeout **{minutes} min** ({reason}).", delete_after=20)
    except Exception as e:
        log.warning("Timeout carta: %s", e)
        try:
            if hasattr(channel, "send"):
                await channel.send(f"No pude aplicar timeout a {target.mention}: permisos o jerarquía.", delete_after=15)
        except Exception:
            pass
