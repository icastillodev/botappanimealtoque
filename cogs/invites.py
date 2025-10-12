# cogs/invites.py
import os
from typing import Dict, List

import discord
from discord.ext import commands

FOUNDER_ROLE_ID = int(os.getenv("FOUNDER_ROLE_ID", "0"))
FOUNDER_INVITE_CODES = {c.strip() for c in os.getenv("FOUNDER_INVITE_CODES", "").split(",") if c.strip()}

class InvitesCog(commands.Cog):
    """
    Asigna rol automáticamente según la invitación usada al entrar.
    - Cachea invites y sus 'uses' al iniciar.
    - Detecta cuál invite incrementó en on_member_join.
    - Si el código está en FOUNDER_INVITE_CODES => asigna FOUNDER_ROLE_ID.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Por guild: { invite_code: uses }
        self._invite_cache: Dict[int, Dict[str, int]] = {}

    async def _fetch_invites_uses(self, guild: discord.Guild) -> Dict[str, int]:
        uses: Dict[str, int] = {}
        try:
            invites: List[discord.Invite] = await guild.invites()
            for inv in invites:
                # inv.code e inv.uses pueden ser None → casteamos a 0
                uses[inv.code] = int(inv.uses or 0)
        except discord.Forbidden:
            # Falta MANAGE_GUILD
            pass
        except Exception:
            pass
        return uses

    @commands.Cog.listener()
    async def on_ready(self):
        # Cache inicial para todos los guilds donde está el bot
        for guild in self.bot.guilds:
            self._invite_cache[guild.id] = await self._fetch_invites_uses(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # Si el bot entra a un nuevo server, inicializar cache
        self._invite_cache[guild.id] = await self._fetch_invites_uses(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        # Ignorar bots
        if member.bot:
            return

        # Asegurar cache previa
        before = self._invite_cache.get(guild.id)
        if before is None:
            before = await self._fetch_invites_uses(guild)
            self._invite_cache[guild.id] = before

        # Leer invites actuales
        after = await self._fetch_invites_uses(guild)
        if after:
            self._invite_cache[guild.id] = after  # actualizar cache

        # Detectar código que incrementó
        used_code = None
        if before and after:
            for code, uses_after in after.items():
                uses_before = before.get(code, 0)
                if uses_after > uses_before:
                    used_code = code
                    break

        # Si no pudimos detectar, salimos silenciosamente
        if not used_code:
            return

        # Si ese código es “fundador”, asignar rol
        if FOUNDER_ROLE_ID and (used_code in FOUNDER_INVITE_CODES):
            role = guild.get_role(FOUNDER_ROLE_ID)
            if role:
                try:
                    await member.add_roles(role, reason=f"Invite fundadora usada: {used_code}")
                except discord.Forbidden:
                    # Falta Manage Roles o el rol del bot está por debajo en la jerarquía
                    pass
                except Exception:
                    pass

async def setup(bot: commands.Bot):
    await bot.add_cog(InvitesCog(bot))
