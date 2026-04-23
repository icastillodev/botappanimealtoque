# cogs/economia/ranking_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal, List, Dict, Any
import logging

from .db_manager import EconomiaDBManagerV2
from .mi_resumen import render_mi_embed, render_top_embed
from .toque_labels import toque_emote

# Opciones más claras y opción 'General' por defecto
TipoRanking = Literal["General", "Puntos Actuales", "Puntos Conseguidos", "Puntos Gastados"]

class RankingCog(commands.Cog, name="Economia Ranking"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economia_db: EconomiaDBManagerV2 = bot.economia_db
        self.log = logging.getLogger(self.__class__.__name__)
        super().__init__()

    async def _get_leaderboard_text(self, data: List[Dict[str, Any]], key_name: str) -> str:
        """Genera el texto de la lista (1. Usuario - Puntos) para el embed."""
        if not data:
            return "*Nadie todavía.*"
        
        text = ""
        medals = ["🥇", "🥈", "🥉"]
        
        # Itera sobre los datos (que ya vienen limitados a 5 o 10 según la llamada)
        for i, user_data in enumerate(data):
            medal = medals[i] if i < 3 else f"**{i+1}.**"
            try:
                # Intentamos obtener el usuario de la caché o API
                user = self.bot.get_user(user_data['user_id']) or await self.bot.fetch_user(user_data['user_id'])
                user_name = user.display_name # Usamos display_name para que sea más corto en la tabla
            except discord.NotFound:
                user_name = "Desconocido"
            
            points = user_data[key_name]
            # Formato: 🥇 Tojito • 1000
            text += f"{medal} {user_name} • **{points}**\n"
            
        return text

    @app_commands.command(name="aat-ranking-top", description="Muestra los rankings de economía del servidor.")
    @app_commands.describe(tipo="Elige qué ranking ver. 'General' muestra un resumen de todos.")
    async def top(self, interaction: discord.Interaction, tipo: TipoRanking = "General"):
        await interaction.response.defer()
        
        # --- CASO 1: VISTA GENERAL (Resumen de los 3 tops) ---
        if tipo == "General":
            # Obtenemos el Top 5 de cada categoría
            top_actual = self.economia_db.get_top_users("actual", limit=5)
            top_conseguidos = self.economia_db.get_top_users("conseguidos", limit=5)
            top_gastados = self.economia_db.get_top_users("gastados", limit=5)
            
            embed = discord.Embed(title="🏆 Tablas de Clasificación Global", color=discord.Color.gold())
            
            # --- CAMBIO SOLICITADO AQUÍ ---
            embed.description = "Aquí están los líderes de la comunidad de AnimeAlToque en las distintas categorías."
            
            # Generamos los textos (cada función devuelve las 5 líneas)
            text_actual = await self._get_leaderboard_text(top_actual, "puntos_actuales")
            text_conseguidos = await self._get_leaderboard_text(top_conseguidos, "puntos_conseguidos")
            text_gastados = await self._get_leaderboard_text(top_gastados, "puntos_gastados")
            
            # Añadimos los campos (inline=True para que intenten estar lado a lado si hay espacio)
            embed.add_field(name="💰 Puntos Actuales", value=text_actual, inline=True)
            embed.add_field(name="📈 Total Conseguido", value=text_conseguidos, inline=True)
            embed.add_field(name="💸 Total Gastado", value=text_gastados, inline=True)
            
            embed.set_footer(text="Usa /aat-ranking-top [tipo] para ver el Top 10 completo de una categoría.")
            await interaction.followup.send(embed=embed)
            return

        # --- CASO 2: VISTA DETALLADA (Top 10 específico) ---
        
        # Mapear la opción legible a la clave interna de la DB
        db_key_map = {
            "Puntos Actuales": "actual",
            "Puntos Conseguidos": "conseguidos",
            "Puntos Gastados": "gastados"
        }
        db_key = db_key_map.get(tipo, "actual")
        col_by_key = {
            "actual": "puntos_actuales",
            "conseguidos": "puntos_conseguidos",
            "gastados": "puntos_gastados",
        }
        column_name = col_by_key[db_key]

        top_users = self.economia_db.get_top_users(db_key, limit=10)
        
        embed = discord.Embed(title=f"🏆 Top 10 - {tipo}", color=discord.Color.blue())
        
        text_list = await self._get_leaderboard_text(top_users, column_name)
        
        if text_list == "*Nadie todavía.*":
             embed.description = text_list
        else:
             embed.description = text_list

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="aat-mi", description="Tu saldo, posición en tops, cartas e histórico ganado.")
    async def aat_mi(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.economia_db.ensure_user_exists(interaction.user.id)
        embed = await render_mi_embed(self.bot, self.economia_db, interaction.user)
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="aat-top-hist",
        description="Top 5 del servidor por total histórico ganado (puntos conseguidos de por vida).",
    )
    async def aat_top_hist(self, interaction: discord.Interaction):
        await interaction.response.defer()
        tq = toque_emote()
        embed = await render_top_embed(
            self.bot,
            self.economia_db,
            ranking_type="conseguidos",
            points_key="puntos_conseguidos",
            title=f"{tq} Top 5 — histórico ganado (total conseguido)",
            limit=5,
        )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RankingCog(bot))