# cogs/presentaciones.py
import os
import unicodedata
import asyncio
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# Carga ENV (usamos tus nuevos nombres)
# =========================
load_dotenv()

# Canal donde se validan presentaciones
CHANNEL_ID_PRESENTACION = int(os.getenv("TRIGGER_CHANNEL_ID_PRESENTACION", "0"))  # 🪪・presentacion

# Roles
CHUNIN_ROLE_ID = int(os.getenv("CHUNIN_ROLE_ID", "0"))          # 🥷 Chūnin (se asigna al aprobar)
HOKAGE_ROLE_ID = int(os.getenv("HOKAGE_ROLE_ID", "0"))          # Hokage (bypass total de reglas)

# Reacciones
EMOJI_ID_TOJITOOK = int(os.getenv("TOJITOOK_EMOJI_ID", "0"))    # si tenés el ID del emoji personalizado
EMOJI_NAME_TOJITOOK = os.getenv("TOJITOOK_EMOJI_NAME", "tojitook")  # fallback por nombre

# Límites
MAX_SCAN_PER_CHANNEL = int(os.getenv("MAX_SCAN_PER_CHANNEL", "300"))  # historial a revisar para "1 post por usuario"


# =========================
# Helpers de formato
# =========================
def _normalize(txt: str) -> str:
    """minusculiza y elimina tildes/acentos para comparar 'categoria' == 'categoría'."""
    nfkd = unicodedata.normalize("NFKD", txt).encode("ASCII", "ignore").decode("ASCII")
    return nfkd.lower()


def cumple_formato(contenido: str) -> bool:
    """
    Debe CONTENER (como substring) estas 4 claves:
    - list
    - personaje
    - top
    - categoria
    (insensible a mayúsculas y acentos)
    """
    t = _normalize(contenido)
    claves = ["list", "personaje", "top", "categoria"]
    return all(k in t for k in claves)


FORMATO_TXT = (
    "Formato presentación al toque (copiá/pegá y completá):\n\n"
    "🧾 **AnimeList:** (tu perfil o lista, o nada si no tenés)\n\n"
    "⚔️ **Personaje que pelearías espalda con espalda:** (ej: Itachi, Zoro, Goku, Gojo...)\n\n"
    "🥇 **Top 3 animes:**\n"
    "1.\n2.\n3.\n\n"
    "🌀 **Categoría anime que más te gusta:** (isekai, shonen, seinen, romance, slice of life, etc.)\n\n"
    "Recordá incluir las palabras **list**, **personaje**, **top** y **categoria**."
)


# =========================
# Cog
# =========================
class PresentacionesCog(commands.Cog):
    """
    - Controla presentaciones solo en el canal configurado.
    - Reglas para NO-Hokage:
        * 1 (una) publicación por usuario en ese canal.
        * El mensaje debe contener list/personaje/top/categoria.
        * Si no cumple: se borra, se avisa por canal (mensaje temporal) y se manda DM con el formato.
        * Si cumple: reacciona con 🔥 + :tojitook: y asigna rol Chūnin (si no lo tiene).
    - Hokage (HOKAGE_ROLE_ID) tiene bypass total (sin límites ni validación).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- utilidades ----
    @staticmethod
    def _tiene_bypass(member: discord.Member) -> bool:
        return HOKAGE_ROLE_ID and any(r.id == HOKAGE_ROLE_ID for r in member.roles)

    @staticmethod
    async def _buscar_msg_prev_en_canal(
        member: discord.Member,
        channel: discord.TextChannel,
        exclude_id: Optional[int] = None,
    ) -> Optional[discord.Message]:
        """Devuelve un mensaje previo del usuario en ESTE canal, o None."""
        try:
            async for msg in channel.history(limit=MAX_SCAN_PER_CHANNEL, oldest_first=False):
                if msg.author.id == member.id and (exclude_id is None or msg.id != exclude_id):
                    return msg
        except discord.Forbidden:
            return None
        except Exception:
            return None
        return None

    async def _reaccionar(self, msg: discord.Message):
        # 🔥
        try:
            await msg.add_reaction("🔥")
        except Exception:
            pass

        # :tojitook:
        emoji_obj = None
        if EMOJI_ID_TOJITOOK:
            emoji_obj = self.bot.get_emoji(EMOJI_ID_TOJITOOK)
        if not emoji_obj and msg.guild:
            emoji_obj = discord.utils.find(
                lambda e: e.name.lower() == EMOJI_NAME_TOJITOOK.lower(), msg.guild.emojis
            )
        if emoji_obj:
            try:
                await msg.add_reaction(emoji_obj)
            except Exception:
                pass

    # ---- listeners ----
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorar DMs y bots
        if message.author.bot or message.guild is None:
            return

        # Easter-egg: "caca" -> "loco"
        if "caca" in message.content.lower():
            await message.channel.send("loco")

        # Solo operamos en el canal de presentaciones
        if not CHANNEL_ID_PRESENTACION or message.channel.id != CHANNEL_ID_PRESENTACION:
            return

        member: discord.Member = message.author  # type: ignore

        # BYPASS total para Hokage
        if self._tiene_bypass(member):
            # Si querés que Hokage también reciba reacciones, descomentá:
            # await self._reaccionar(message)
            return

        # (1) ÚNICA publicación en ESTE canal
        previo = await self._buscar_msg_prev_en_canal(member, message.channel, exclude_id=message.id)
        if previo:
            # Intentar borrar el nuevo
            user_msg_deleted = False
            try:
                await message.delete()
                user_msg_deleted = True
            except Exception:
                pass

            # Aviso temporal en canal
            warn = None
            try:
                txt = (
                    f"{member.mention} solo se permite **una** publicación en este canal. "
                    "Podés **editar** la que ya tenés."
                    f" (Tu mensaje previo: {previo.jump_url})"
                )
                if not user_msg_deleted:
                    txt += " *(No pude borrar tu nuevo mensaje; revisen **Manage Messages** en este canal).*"
                warn = await message.channel.send(txt)
            except Exception:
                pass

            # DM con explicación
            try:
                dm = await member.create_dm()
                await dm.send(
                    "👋 En el canal de presentaciones solo se permite **una** publicación por usuario.\n"
                    f"Editá tu mensaje previo: {previo.jump_url}"
                )
            except Exception:
                pass

            # Borrar aviso al rato
            if warn:
                try:
                    await asyncio.sleep(6)
                    await warn.delete()
                except Exception:
                    pass
            return

        # (2) Validación de formato
        if not cumple_formato(message.content):
            user_msg_deleted = False
            try:
                await message.delete()
                user_msg_deleted = True
            except Exception:
                pass

            warn = None
            try:
                aviso_txt = (
                    f"{member.mention} tu presentación no cumple el formato. "
                    "Te mandé un DM con el modelo."
                )
                if not user_msg_deleted:
                    aviso_txt += " *(No pude borrar tu mensaje; revisen **Manage Messages** en este canal).*"
                warn = await message.channel.send(aviso_txt)
            except Exception:
                pass

            # DM con el formato correcto
            try:
                dm = await member.create_dm()
                await dm.send(
                    "👋 Tu presentación no fue aceptada porque no sigue el formato.\n"
                    "Usá este modelo y volvé a enviarla en el canal de presentaciones:\n\n"
                    + FORMATO_TXT
                )
            except Exception:
                pass

            if warn:
                try:
                    await asyncio.sleep(6)
                    await warn.delete()
                except Exception:
                    pass
            return

        # (3) Formato OK: reacciones + rol Chūnin (si no lo tiene)
        await self._reaccionar(message)

        role = message.guild.get_role(CHUNIN_ROLE_ID) if CHUNIN_ROLE_ID else None
        if role and role not in member.roles:
            me = message.guild.get_member(self.bot.user.id)
            if me and role >= me.top_role:
                # Jerarquía incorrecta
                try:
                    await message.channel.send(
                        "No puedo asignar **Chūnin** por jerarquía. Subí el **rol del bot** por encima de ese rol."
                    )
                except Exception:
                    pass
            else:
                try:
                    await member.add_roles(role, reason="Presentación válida")
                except discord.Forbidden:
                    try:
                        await message.channel.send(
                            "Me falta **Manage Roles** o jerarquía correcta para asignar **Chūnin**."
                        )
                    except Exception:
                        pass
                except Exception as e:
                    print("Error asignando rol Chūnin:", e)


# Setup del cog
async def setup(bot: commands.Bot):
    await bot.add_cog(PresentacionesCog(bot))
