"""Efectos mecánicos al usar cartas: solo Rara / Legendaria (Común = solo narración en el embed)."""
from __future__ import annotations

import datetime
import logging
import random
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

import discord

if TYPE_CHECKING:
    from .db_manager import EconomiaDBManagerV2

log = logging.getLogger(__name__)

RAREZAS_CON_EFECTO = ("Rara", "Legendaria")


def _rareza_tiene_efecto(carta: Dict[str, Any]) -> bool:
    r = (carta.get("rareza") or "").strip()
    return r in RAREZAS_CON_EFECTO


def _role_assignable(role: discord.Role, me: discord.Member) -> bool:
    if role.is_default() or role.managed:
        return False
    if role >= me.top_role:
        return False
    if not me.guild_permissions.manage_roles:
        return False
    return True


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


async def aplicar_efecto_al_usar(
    *,
    carta: Dict[str, Any],
    actor: discord.Member,
    target: Optional[discord.Member],
    channel: discord.abc.Messageable,
    economia_db: Optional["EconomiaDBManagerV2"] = None,
    guild: Optional[discord.Guild] = None,
    trampa_carta_rol_id: int = 0,
    trampa_carta_rol_hours: int = 24,
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
    elif fx == "ROLE_TRAMPA_24H":
        await _efecto_rol_trampa_24h(
            carta=carta,
            actor=actor,
            target=target,
            channel=channel,
            economia_db=economia_db,
            guild=guild,
            role_id=trampa_carta_rol_id,
            hours=trampa_carta_rol_hours,
        )


async def _efecto_rol_trampa_24h(
    *,
    carta: Dict[str, Any],
    actor: discord.Member,
    target: Optional[discord.Member],
    channel: discord.abc.Messageable,
    economia_db: Optional["EconomiaDBManagerV2"],
    guild: Optional[discord.Guild],
    role_id: int,
    hours: int,
) -> None:
    if not target or target.bot:
        if hasattr(channel, "send"):
            await channel.send(
                f"{actor.mention} — **ROLE_TRAMPA_24H** necesita un **usuario objetivo** humano.",
                delete_after=25,
            )
        return
    if role_id <= 0:
        if hasattr(channel, "send"):
            await channel.send(
                f"{actor.mention} — el staff no configuró `TRAMPA_CARTA_ROL_24H_ROLE_ID` (o es 0).",
                delete_after=25,
            )
        return
    if not guild or not economia_db:
        return
    me = guild.me
    if not me or not isinstance(me, discord.Member):
        return
    role = guild.get_role(role_id)
    if not role:
        if hasattr(channel, "send"):
            await channel.send("No encuentro ese rol en el servidor (revisá el ID en `.env`).", delete_after=20)
        return
    if not _role_assignable(role, me):
        if hasattr(channel, "send"):
            await channel.send(
                "No puedo asignar ese rol: jerarquía, rol gestionado por integración o me faltan permisos.",
                delete_after=20,
            )
        return
    if target.top_role >= me.top_role:
        if hasattr(channel, "send"):
            await channel.send("No puedo modificar roles de ese miembro (está por encima del bot).", delete_after=20)
        return
    if role in target.roles:
        if hasattr(channel, "send"):
            await channel.send(f"{target.mention} ya tiene **{role.name}**.", delete_after=15)
        return

    try:
        await target.add_roles(role, reason=f"Carta trampa {carta.get('nombre')} — {actor.id}")
    except discord.Forbidden:
        if hasattr(channel, "send"):
            await channel.send("Discord rechazó **add_roles** (permisos).", delete_after=15)
        return

    now = time.time()
    exp = now + max(1, min(168, int(hours))) * 3600
    economia_db.register_temp_shop_role(
        guild.id,
        role.id,
        target.id,
        actor.id,
        f"carta:{carta.get('nombre') or '?'}",
        now,
        exp,
        kind="card",
    )
    if hasattr(channel, "send"):
        await channel.send(
            f"{target.mention} recibió **{role.name}** por **{hours}** h (cartas trampa). Se quita solo al vencer.",
            delete_after=45,
        )
