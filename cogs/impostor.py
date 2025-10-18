"""
Shim/loader para el módulo IMPOSITOR modular.

Estructura esperada:
cogs/
  impostor/
    __init__.py          # carga submódulos
    core.py
    feed.py
    lobby.py
    chars.py
    game_core.py
    game.py
    stats.py
    stats_commands.py
"""

from discord.ext import commands

# Importa el paquete y delega el setup hacia adentro
from .impostor import setup as setup_package  # cogs/impostor/__init__.py

async def setup(bot: commands.Bot):
    # Esto carga lobby, game y stats según lo definas en cogs/impostor/__init__.py
    await setup_package(bot)
