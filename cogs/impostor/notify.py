# cogs/impostor/notify.py — Rol de avisos y cooldown de ping en lobby
#
# Requisitos:
# - IMPOSTOR_NOTIFY_ROLE_ID: rol que DEBE existir en el servidor (avisos @mención).
# - Opcional IMPOSTOR_NOTIFY_PING_CHANNEL_ID: si está definido, el host “🔔 avisar”
#   publica el @rol ahí (p. ej. #general-impostor). Si no, el mensaje va al canal del lobby.

import os
import time
from typing import Optional
import discord
from discord.ext import commands
import logging

log = logging.getLogger(__name__)

LOBBY_PING_COOLDOWN_SEC = 5.0
_last_lobby_ping_ts: dict[int, float] = {}


def get_notify_role_id() -> int:
    val = os.getenv("IMPOSTOR_NOTIFY_ROLE_ID", "1437939011212546068")
    return int(val)


def get_notify_ping_broadcast_channel_id() -> Optional[int]:
    """Canal fijo para el ping de ‘buscan jugadores’ (ej. #general-impostor). None = usar canal del lobby."""
    raw = (os.getenv("IMPOSTOR_NOTIFY_PING_CHANNEL_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw.split("#", 1)[0].strip())
    except ValueError:
        return None


def lobby_ping_cooldown_remaining(channel_id: int) -> float:
    """Segundos restantes de cooldown, o 0 si se puede pinguear."""
    now = time.monotonic()
    last = _last_lobby_ping_ts.get(channel_id, 0.0)
    wait = LOBBY_PING_COOLDOWN_SEC - (now - last)
    return max(0.0, wait)


def register_lobby_ping(channel_id: int) -> None:
    _last_lobby_ping_ts[channel_id] = time.monotonic()


class ImpostorNotifyView(discord.ui.View):
    """Vista persistente: botón para darse/quitar el rol de avisos."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Avisos Impostor",
        style=discord.ButtonStyle.primary,
        emoji="🔔",
        custom_id="imp:notify_role_toggle",
        row=0,
    )
    async def toggle_notify(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message(
                "❌ Esto solo funciona en un servidor.", ephemeral=True
            )
        member = interaction.user
        if not isinstance(member, discord.Member):
            return await interaction.response.send_message(
                "❌ No se pudo obtener tu miembro en el servidor.", ephemeral=True
            )

        role_id = get_notify_role_id()
        role = interaction.guild.get_role(role_id)
        if not role:
            log.warning("Rol de avisos Impostor (ID %s) no existe en el servidor.", role_id)
            return await interaction.response.send_message(
                "❌ El rol de avisos no está configurado en este servidor (falta el rol o el ID).",
                ephemeral=True,
            )

        bot_member = interaction.guild.me
        if not bot_member or not bot_member.guild_permissions.manage_roles:
            return await interaction.response.send_message(
                "❌ El bot no tiene permiso **Gestionar roles**.", ephemeral=True
            )
        if role >= bot_member.top_role:
            return await interaction.response.send_message(
                "❌ El rol de avisos está por encima del rol del bot; un admin debe reordenar los roles.",
                ephemeral=True,
            )

        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Toggle avisos Impostor (botón)")
                await interaction.response.send_message(
                    "✅ Te quité el rol de avisos. Ya no recibirás menciones de partidas.",
                    ephemeral=True,
                )
            else:
                await member.add_roles(role, reason="Toggle avisos Impostor (botón)")
                await interaction.response.send_message(
                    "✅ Te asigné el rol de avisos. Te mencionarán cuando busquen jugadores.",
                    ephemeral=True,
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ No pude modificar tu rol (permisos o jerarquía).", ephemeral=True
            )
        except discord.HTTPException as e:
            log.exception("Error HTTP al togglear rol de avisos: %s", e)
            await interaction.response.send_message("❌ Error de Discord al cambiar el rol.", ephemeral=True)


class ImpostorNotifyCog(commands.Cog, name="ImpostorNotify"):
    """Registra la vista persistente al cargar."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    bot.add_view(ImpostorNotifyView())
    await bot.add_cog(ImpostorNotifyCog(bot))
