# cogs/votacion/__init__.py
from .cog import VotacionCog

async def setup(bot):
    await bot.add_cog(VotacionCog(bot))