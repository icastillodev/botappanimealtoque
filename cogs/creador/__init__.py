# cogs/creador/__init__.py
from .cog import CreadorCog

async def setup(bot):
    await bot.add_cog(CreadorCog(bot))