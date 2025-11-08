# cogs/economia/ranking_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal
import logging

from .db_manager import EconomiaDBManagerV2

TipoRanking = Literal["actual", "conseguidos", "gastados"]

class RankingCog(commands.Cog, name="Economia Ranking"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economia_db: EconomiaDBManagerV2 = bot.economia_db
        self.log = logging.getLogger(self.__class__.__name__)
        super().__init__()

    @app_commands.command(name="aat_ranking_top", description="Muestra el ranking de puntos.")
    @app_commands.describe(tipo="El tipo de ranking que quieres ver.")
    async def top(self, interaction: discord.Interaction, tipo: TipoRanking = "actual"):
        await interaction.response.defer()
        
        top_users = self.economia_db.get_top_users(tipo, limit=10)
        
        embed = discord.Embed(title=f"🏆 Top 10 - Puntos {tipo.capitalize()}", color=discord.Color.gold())
        
        if not top_users:
            embed.description = "No hay nadie en el ranking todavía."
            await interaction.followup.send(embed=embed)
            return
            
        desc = ""
        medals = ["🥇", "🥈", "🥉"]
        
        for i, user_data in enumerate(top_users):
            medal = medals[i] if i < 3 else f"**{i+1}.**"
            try:
                user = self.bot.get_user(user_data['user_id']) or await self.bot.fetch_user(user_data['user_id'])
                user_name = user.mention
            except discord.NotFound:
                user_name = f"*Usuario Desconocido ({user_data['user_id']})*"
            
            points = user_data[f'puntos_{tipo}']
            desc += f"{medal} {user_name} - **{points}** Puntos\n"
            
        embed.description = desc
        await interaction.followup.send(embed=embed)

# --- ¡¡¡AQUÍ ESTÁ EL ARREGLO!!! ---
async def setup(bot):
    await bot.add_cog(RankingCog(bot))