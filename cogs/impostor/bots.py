# cogs/impostor/bots.py
import discord
from discord import app_commands
from discord.ext import commands

from .core import manager, is_admin_member, MAX_PLAYERS
from .ui import update_panel  # refrescamos el panel tras cambios

class BotsCog(commands.Cog):
    """Comandos admin/host para bots simulados y arranque forzado."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="addbot", description="(Host/Admin) Agregar un bot simulado al lobby")
    async def addbot(self, interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Usá este comando en el servidor.", ephemeral=True)

        lob = manager.by_user(interaction.user.id)
        if not lob:
            return await interaction.response.send_message("No estás en un lobby.", ephemeral=True)

        es_host = (lob.host_id == interaction.user.id)
        es_admin = is_admin_member(interaction.user)
        if not (es_host or es_admin):
            return await interaction.response.send_message("Solo el host o un admin puede agregar bots.", ephemeral=True)

        if len(lob.players) >= MAX_PLAYERS:
            return await interaction.response.send_message("El lobby está lleno (5/5).", ephemeral=True)

        uid = manager.add_sim_bot(lob)
        if uid == 0:
            return await interaction.response.send_message("No se pudo agregar el bot.", ephemeral=True)

        if interaction.guild and lob.channel_id:
            ch = interaction.guild.get_channel(lob.channel_id)
            if isinstance(ch, discord.TextChannel):
                await ch.send(f"🤖 **AAT-Bot** se unió (listo). {lob.slots()}")

        # refrescar panel
        if interaction.guild:
            await update_panel(self.bot, interaction.guild, lob)

        await interaction.response.send_message("Bot agregado y listo ✅", ephemeral=True)

    @app_commands.command(name="forzar_inicio", description="(Host/Admin) Iniciar partida con 5/5 aunque falte 'ready'")
    async def forzar_inicio(self, interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Usá este comando en el servidor.", ephemeral=True)

        lob = manager.by_user(interaction.user.id)
        if not lob:
            return await interaction.response.send_message("No estás en un lobby.", ephemeral=True)

        es_host = (lob.host_id == interaction.user.id)
        es_admin = is_admin_member(interaction.user)
        if not (es_host or es_admin):
            return await interaction.response.send_message("Solo host o admin.", ephemeral=True)

        if lob.in_game:
            return await interaction.response.send_message("La partida ya está en curso.", ephemeral=True)
        if len(lob.players) != MAX_PLAYERS:
            return await interaction.response.send_message("Se necesitan exactamente 5 jugadores para iniciar.", ephemeral=True)

        # import local para evitar ciclos
        from .game_core import start_game

        gs = await start_game(interaction.guild, lob.name)
        if not gs:
            return await interaction.response.send_message("No se pudo iniciar la partida.", ephemeral=True)

        lob.in_game = True

        # refrescar panel
        if interaction.guild:
            await update_panel(self.bot, interaction.guild, lob)

        await interaction.response.send_message("🚀 Partida iniciada (forzado).", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BotsCog(bot))
