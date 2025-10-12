# economy/recompensas.py
from dataclasses import dataclass
from typing import List, Optional, Dict
import os
import discord
from discord.ext import commands

# --- ENV (precios y canales) ---
def _price(name: str, default: Optional[int] = None) -> Optional[int]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return default

AKATSUKI_ROLE_PRICE = _price("SHOP_PRICE_ROLE_AKATSUKI")
JONIN_ROLE_PRICE    = _price("SHOP_PRICE_ROLE_JONIN")
PIN_MESSAGE_PRICE   = _price("SHOP_PRICE_PIN_MESSAGE")
POLL_PROPOSE_PRICE  = _price("SHOP_PRICE_POLL_PROPOSE")

GENERAL_CHANNEL_ID  = int(os.getenv("GENERAL_CHANNEL_ID", "0"))          # para fijar mensajes
VOTING_CHANNEL_ID   = int(os.getenv("VOTING_CHANNEL_ID", "0"))           # para encuestas

AKATSUKI_ROLE_ID    = int(os.getenv("AKATSUKI_ROLE_ID", "0"))
JONIN_ROLE_ID       = int(os.getenv("JONIN_ROLE_ID", "0"))

CURRENCY            = os.getenv("ECONOMY_CURRENCY", "🌀")

@dataclass
class Reward:
    key: str
    icon: str
    name: str
    price: Optional[int]  # None => no definido
    description: str

def get_shop_items() -> List[Reward]:
    return [
        Reward("role_akatsuki", "🩸", "Rol Akatsuki", AKATSUKI_ROLE_PRICE,
               "Se te asigna el rol Akatsuki."),
        Reward("role_jonin", "🍃", "Rol Jōnin", JONIN_ROLE_PRICE,
               "Se te asigna el rol Jōnin."),
        Reward("pin_message", "💬", "Mensaje fijo", PIN_MESSAGE_PRICE,
               "Fijamos un mensaje tuyo en #general-y-offtopic."),
        Reward("poll_propose", "🍥", "Proponer encuesta", POLL_PROPOSE_PRICE,
               "Publicamos tu propuesta para que la comunidad vote."),
    ]

def format_shop(items: List[Reward]) -> str:
    lines = []
    for it in items:
        price_txt = f"{CURRENCY} {it.price}" if it.price is not None else "**no definido**"
        lines.append(f"{it.icon} **{it.name}** — {price_txt}\n   _{it.description}_")
    if not lines:
        return "La tienda está vacía por ahora."
    return "🛍️ **Tienda de recompensas**\n" + "\n".join(lines)

# -------- acciones de canje --------

async def redeem(
    cog: commands.Cog,
    interaction: discord.Interaction,
    key: str,
    *,
    message_link: Optional[str] = None,
    poll_text: Optional[str] = None,
    add_points=None, get_points=None, set_points=None
) -> str:
    """
    Ejecuta la recompensa. Devuelve texto para mostrar al usuario.
    Lanza ValueError con mensajes legibles si falta configuración.
    """
    guild = interaction.guild
    member = interaction.user if isinstance(interaction.user, discord.Member) else None
    if not guild or not member:
        raise ValueError("Este canje solo puede hacerse dentro de un servidor.")

    # helpers de saldo
    async def ensure_balance(cost: int):
        if cost is None:
            raise ValueError("Esta recompensa aún no tiene precio definido.")
        pts, _ = await cog._get_user(guild.id, member.id)  # type: ignore
        if pts < cost:
            raise ValueError(f"No te alcanza. Tenés {CURRENCY} {pts} y cuesta {CURRENCY} {cost}.")
        await cog._set_points(guild.id, member.id, pts - cost)  # type: ignore

    # ---- rol akatsuki ----
    if key == "role_akatsuki":
        if AKATSUKI_ROLE_ID == 0:
            raise ValueError("El rol Akatsuki no está configurado.")
        role = guild.get_role(AKATSUKI_ROLE_ID)
        if not role:
            raise ValueError("No encuentro el rol Akatsuki en este servidor.")
        await ensure_balance(AKATSUKI_ROLE_PRICE)
        await member.add_roles(role, reason="Canje tienda: Rol Akatsuki")
        return f"🩸 Listo, te asigné **{role.name}**."

    # ---- rol jonin ----
    if key == "role_jonin":
        if JONIN_ROLE_ID == 0:
            raise ValueError("El rol Jōnin no está configurado.")
        role = guild.get_role(JONIN_ROLE_ID)
        if not role:
            raise ValueError("No encuentro el rol Jōnin en este servidor.")
        await ensure_balance(JONIN_ROLE_PRICE)
        await member.add_roles(role, reason="Canje tienda: Rol Jōnin")
        return f"🍃 Listo, te asigné **{role.name}**."

    # ---- fijar mensaje en general ----
    if key == "pin_message":
        if GENERAL_CHANNEL_ID == 0:
            raise ValueError("El canal general para fijar mensajes no está configurado.")
        chan = guild.get_channel(GENERAL_CHANNEL_ID)
        if not isinstance(chan, discord.TextChannel):
            raise ValueError("No encuentro el canal general configurado.")
        if not message_link:
            raise ValueError("Pasá el link del **mensaje tuyo** a fijar (parámetro message_link).")

        # Resolver el mensaje a partir del link
        # Link formato: https://discord.com/channels/guildId/channelId/messageId
        try:
            parts = message_link.split("/")
            msg_id = int(parts[-1])
            ch_id  = int(parts[-2])
        except Exception:
            raise ValueError("Link inválido. Pegá el link completo del mensaje.")

        if ch_id != chan.id:
            raise ValueError(f"El mensaje debe ser del canal <#{chan.id}>.")

        msg = await chan.fetch_message(msg_id)
        if msg.author.id != member.id:
            raise ValueError("El mensaje a fijar debe ser **tuyo**.")
        await ensure_balance(PIN_MESSAGE_PRICE)
        await msg.pin(reason=f"Canje tienda: pin de {member.display_name}")
        return "💬 ¡Mensaje fijado en el canal general!"

    # ---- proponer encuesta en VOTING_CHANNEL_ID ----
    if key == "poll_propose":
        if VOTING_CHANNEL_ID == 0:
            raise ValueError("El canal de votación no está configurado.")
        chan = guild.get_channel(VOTING_CHANNEL_ID)
        if not isinstance(chan, discord.TextChannel):
            raise ValueError("No encuentro el canal de votación configurado.")
        if not poll_text or len(poll_text.strip()) < 5:
            raise ValueError("Escribí el texto de la propuesta de encuesta (mín. 5 caracteres).")
        await ensure_balance(POLL_PROPOSE_PRICE)
        post = await chan.send(f"🗳️ **Propuesta de {member.mention}:**\n> {poll_text.strip()}")
        try:
            await post.add_reaction("✅")
            await post.add_reaction("❌")
        except Exception:
            pass
        return f"🍥 Tu propuesta fue publicada en {chan.mention}. ¡La comunidad decidirá!"

    raise ValueError("Recompensa desconocida.")
