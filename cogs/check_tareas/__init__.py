# cogs/check_tareas/__init__.py
from .cog import CheckTareasCog

async def setup(bot):
    await bot.add_cog(CheckTareasCog(bot))