# cogs/presentaciones.py
import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()
log = logging.getLogger(__name__)

CHANNEL_ID_PRESENTACION = int(os.getenv("TRIGGER_CHANNEL_ID_PRESENTACION", "0"))
CHUNIN_ROLE_ID = int(os.getenv("CHUNIN_ROLE_ID", "0"))
HOKAGE_ROLE_ID = int(os.getenv("HOKAGE_ROLE_ID", "0"))
EMOJI_ID_TOJITOOK = int(os.getenv("TOJITOOK_EMOJI_ID", "0"))
EMOJI_NAME_TOJITOOK = os.getenv("TOJITOOK_EMOJI_NAME", "tojitook")
MAX_SCAN_PER_CHANNEL = int(os.getenv("MAX_SCAN_PER_CHANNEL", "300"))


class PresentacionesCog(commands.Cog):
    """
    Solo aplica: una publicación por usuario en el canal de presentaciones.
    Sin validación de formato. Hokage hace bypass total.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _tiene_bypass(member: discord.Member) -> bool:
        return bool(HOKAGE_ROLE_ID and any(r.id == HOKAGE_ROLE_ID for r in member.roles))

    @staticmethod
    async def _buscar_msg_prev_en_canal(
        member: discord.Member,
        channel: discord.TextChannel,
        exclude_id: Optional[int] = None,
    ) -> Optional[discord.Message]:
        try:
            async for msg in channel.history(limit=MAX_SCAN_PER_CHANNEL, oldest_first=False):
                if msg.author.id == member.id and (exclude_id is None or msg.id != exclude_id):
                    return msg
        except (discord.Forbidden, Exception):
            return None
        return None

    async def _reaccionar(self, msg: discord.Message):
        try:
            await msg.add_reaction("🔥")
        except Exception:
            pass
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not CHANNEL_ID_PRESENTACION or message.channel.id != CHANNEL_ID_PRESENTACION:
            return

        member: discord.Member = message.author  # type: ignore

        if self._tiene_bypass(member):
            return

        previo = await self._buscar_msg_prev_en_canal(member, message.channel, exclude_id=message.id)
        if previo:
            user_msg_deleted = False
            try:
                await message.delete()
                user_msg_deleted = True
            except Exception:
                pass
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
            try:
                dm = await member.create_dm()
                await dm.send(
                    "👋 En el canal de presentaciones solo se permite **una** publicación por usuario.\n"
                    f"Editá tu mensaje previo: {previo.jump_url}"
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

        await self._reaccionar(message)

        role = message.guild.get_role(CHUNIN_ROLE_ID) if CHUNIN_ROLE_ID else None
        if role and role not in member.roles:
            me = message.guild.get_member(self.bot.user.id)
            if me and role >= me.top_role:
                try:
                    await message.channel.send(
                        "No puedo asignar **Chūnin** por jerarquía. Subí el **rol del bot** por encima de ese rol."
                    )
                except Exception:
                    pass
            else:
                try:
                    await member.add_roles(role, reason="Primera presentación en canal")
                except discord.Forbidden:
                    try:
                        await message.channel.send(
                            "Me falta **Manage Roles** o jerarquía correcta para asignar **Chūnin**."
                        )
                    except Exception:
                        pass
                except Exception as e:
                    log.warning("Error asignando rol Chūnin: %s", e)


async def setup(bot: commands.Bot):
    await bot.add_cog(PresentacionesCog(bot))
