# cogs/impostor/game.py
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from .core import manager, MAX_PLAYERS
from .game_core import start_game, get_game

class GameCog(commands.Cog):
    """Comandos de partida: /comenzar, /palabra, /votar."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # El botón "Comenzar" llama a start_game desde la UI. De todas formas
    # exponemos /comenzar para el host (mismo chequeo).
    @app_commands.command(name="comenzar", description="(Host) Iniciar la partida (5/5, humanos listos)")
    async def comenzar(self, interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Usá este comando en el servidor.", ephemeral=True)

        lob = manager.by_user(interaction.user.id)
        if not lob or lob.host_id != interaction.user.id:
            return await interaction.response.send_message("No sos host de ningún lobby.", ephemeral=True)
        if lob.in_game:
            return await interaction.response.send_message("La partida ya está en curso.", ephemeral=True)
        if len(lob.players) != MAX_PLAYERS:
            return await interaction.response.send_message("Se necesitan exactamente 5 jugadores.", ephemeral=True)
        if not all(p.ready for p in lob.players.values() if not p.is_bot_sim):
            return await interaction.response.send_message("Todos los jugadores (no bots) deben estar **listos**.", ephemeral=True)

        gs = await start_game(interaction.guild, lob.name)
        if not gs:
            return await interaction.response.send_message("No se pudo iniciar la partida.", ephemeral=True)
        lob.in_game = True
        await interaction.response.send_message("✅ Partida iniciada.", ephemeral=True)

    @app_commands.command(name="palabra", description="Decí tu pista (1 a 5 palabras) durante tu turno")
    async def palabra(self, interaction: discord.Interaction, texto: str):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Usá este comando dentro del servidor.", ephemeral=True)

        lob = manager.by_user(interaction.user.id)
        if not lob or not lob.in_game:
            return await interaction.response.send_message("No estás en una partida en curso.", ephemeral=True)

        gs = get_game(interaction.guild_id, lob.name)  # type: ignore
        if not gs or not gs.in_progress or not gs.clues_phase:
            return await interaction.response.send_message("No es la fase de pistas ahora.", ephemeral=True)

        gp = gs.players.get(interaction.user.id)
        if not gp or not gp.alive:
            return await interaction.response.send_message("No estás vivo en esta partida.", ephemeral=True)
        if gp.clue:
            return await interaction.response.send_message("Ya diste tu pista esta ronda.", ephemeral=True)

        # Sólo el jugador cuyo turno es puede registrar pista
        # El “turno actual” es el primer vivo de gs.order que aún no tiene clue
        def _turno_actual() -> Optional[int]:
            for uid in gs.order:
                if gs.players[uid].alive and gs.players[uid].clue is None:
                    return uid
            return None

        if _turno_actual() != interaction.user.id:
            return await interaction.response.send_message("No es tu turno. Esperá a que el bot te llame.", ephemeral=True)

        wc = len([w for w in texto.strip().split() if w])
        if wc < 1 or wc > 5:
            return await interaction.response.send_message("La pista debe ser de 1 a 5 palabras.", ephemeral=True)

        gp.clue = texto.strip()

        # anunciar públicamente lo que dijo
        ch = interaction.channel
        if isinstance(ch, discord.TextChannel):
            await ch.send(f"💬 **{interaction.user.display_name}** dijo: **{gp.clue}**")

        await interaction.response.send_message("✅ Pista registrada.", ephemeral=True)

    @app_commands.command(name="votar", description="Votar al presunto impostor")
    async def votar(self, interaction: discord.Interaction, usuario: discord.Member):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Usá este comando dentro del servidor.", ephemeral=True)
        lob = manager.by_user(interaction.user.id)
        if not lob or not lob.in_game:
            return await interaction.response.send_message("No estás en una partida en curso.", ephemeral=True)

        gs = get_game(interaction.guild_id, lob.name)  # type: ignore
        if not gs or not gs.in_progress or not gs.votes_open:
            return await interaction.response.send_message("No es la fase de votación ahora.", ephemeral=True)

        voter = gs.players.get(interaction.user.id)
        target = gs.players.get(usuario.id)
        if not voter or not voter.alive:
            return await interaction.response.send_message("No estás vivo en esta partida.", ephemeral=True)
        if not target or not target.alive:
            return await interaction.response.send_message("Ese jugador no está vivo en esta partida.", ephemeral=True)

        voter.vote_target = usuario.id
        await interaction.response.send_message("🗳️ Voto registrado.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GameCog(bot))
