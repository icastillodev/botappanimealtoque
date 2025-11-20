# cogs/economia/ayuda_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List

class EconomiaHelpView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.current_page = 0
        self.embeds: List[discord.Embed] = [
            self._create_page_1(),
            self._create_page_2(),
            self._create_page_3(),
            self._create_page_4()
        ]
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("No puedes usar esta guía, pide la tuya con `/aat_ayuda`.", ephemeral=True)
            return False
        return True

    def _create_page_1(self) -> discord.Embed:
        embed = discord.Embed(title="Ayuda de Economía 🪙 (Página 1/4)", color=discord.Color.blue())
        embed.description = "¡Bienvenido al sistema de economía y cartas del servidor!"
        embed.add_field(name="¿Qué es esto?", value="Gana Puntos y Blisters completando tareas...", inline=False)
        embed.add_field(name="Tareas (Comandos)", value=(
            "`/aat_progreso_iniciacion` - Muestra tus misiones de bienvenida.\n"
            "`/aat_progreso_diaria` - Muestra tus misiones diarias.\n"
            "`/aat_progreso_semanal` - Muestra tus misiones semanales.\n"
            "`/aat_reclamar [tipo]` - Reclama tus recompensas (inicial, diaria, semanal)."
        ), inline=False)
        embed.set_footer(text="Usa los botones para navegar.")
        return embed

    def _create_page_2(self) -> discord.Embed:
        embed = discord.Embed(title="Ayuda de Cartas y Blisters 🃏 (Página 2/4)", color=discord.Color.purple())
        embed.add_field(name="`/aat_puntos`", value="Un atajo rápido para ver solo tus puntos.", inline=False)
        embed.add_field(name="`/aat_inventario`", value="Tu comando principal. Úsalo para ver tus Puntos, Créditos y Blisters.", inline=False)
        embed.add_field(name="`/aat_abrirblister`", value="¡Abre los blisters que ganaste! Cada uno da 3 cartas aleatorias.", inline=False)
        embed.add_field(name="`/aat_miscartas`", value="Muestra tu colección de cartas (verás el ID de cada carta).", inline=False)
        # --- MODIFICADO: Nombre actualizado ---
        embed.add_field(name="`/vercarta`", value="Inspecciona una carta de tu inventario (usa el ID o el nombre).", inline=False)
        embed.add_field(name="`/aat_catalogo`", value="Muestra todas las cartas que existen en el juego.", inline=False)
        return embed
        
    def _create_page_3(self) -> discord.Embed:
        embed = discord.Embed(title="Ayuda de Cartas Trampa ⚔️ (Página 3/4)", color=discord.Color.red())
        # --- MODIFICADO: Nombre actualizado ---
        embed.add_field(name="`/usar`", value="Consume una carta de tu inventario. Puedes usarla 'al aire' o contra un usuario.", inline=False)
        embed.add_field(name="Límites", value="Las cartas son **consumibles** y tienes un límite de **5 cartas cada 10 minutos**.", inline=False)
        return embed

    def _create_page_4(self) -> discord.Embed:
        embed = discord.Embed(title="Ayuda de Tienda y Ranking 🏆 (Página 4/4)", color=discord.Color.gold())
        embed.add_field(name="`/aat_tienda_ver`", value="Muestra la tienda donde puedes gastar tus puntos 🪙.", inline=False)
        embed.add_field(name="`/aat_tienda_canjear`", value="Compra un ítem de la tienda (roles o créditos).", inline=False)
        embed.add_field(name="`/aat_tienda_fijar`", value="Usa un crédito para fijar un mensaje.", inline=False)
        embed.add_field(name="`/aat_ranking_top`", value="Muestra el Top 10 del servidor.", inline=False)
        return embed

    def _update_buttons(self):
        previous_button = self.children[0]
        next_button = self.children[1]
        if isinstance(previous_button, discord.ui.Button):
            previous_button.disabled = (self.current_page == 0)
        if isinstance(next_button, discord.ui.Button):
            next_button.disabled = (self.current_page == len(self.embeds) - 1)

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Siguiente", style=discord.ButtonStyle.primary, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

class AyudaCog(commands.Cog, name="Economia Ayuda"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(self.__class__.__name__)
        super().__init__()

    @app_commands.command(name="aat_ayuda", description="Muestra una guía interactiva de los comandos de economía.")
    async def ayuda(self, interaction: discord.Interaction):
        view = EconomiaHelpView(interaction.user.id)
        embed = view.embeds[0]
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AyudaCog(bot))