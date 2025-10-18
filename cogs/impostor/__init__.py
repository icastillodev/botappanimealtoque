# cogs/impostor/__init__.py
"""
Extensión principal 'cogs.impostor'.

Carga los cogs que exponen setup() y añade un listener para
redireccionar los botones de votación (custom_id 'impvote:*')
al handler de game_core.
"""

from discord.ext import commands
import discord

from .lobby import setup_lobby
from .game import setup as setup_game
from .bots import setup as setup_bots
from .help import setup as setup_help
from .stats_commands import setup as setup_stats

# --- pequeño cog con el listener de interacciones ---
class _ImpostorEvents(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener("on_interaction")
    async def _on_interaction(self, interaction: discord.Interaction):
        # Solo nos interesan componentes (botones/selects)
        if interaction.type != discord.InteractionType.component:
            return

        data = interaction.data or {}
        cid = str(data.get("custom_id") or "")
        if not cid:
            return

        # Botones de votación creados por VoteView (game_core.py)
        if cid.startswith("impvote:"):
            from .game_core import handle_vote_component
            await handle_vote_component(interaction)
            # IMPORTANTE: no devolver acá respuesta “doble”; el handler ya responde.

async def setup(bot: commands.Bot):
    # Cargar módulos funcionales
    await setup_lobby(bot)
    await setup_game(bot)
    await setup_bots(bot)
    await setup_help(bot)
    await setup_stats(bot)

    # Registrar el listener
    await bot.add_cog(_ImpostorEvents(bot))