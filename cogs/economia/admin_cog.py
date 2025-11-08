# cogs/economia/admin_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List, Literal, Dict, Any
import logging

from .db_manager import EconomiaDBManagerV2
from .card_db_manager import CardDBManager
from .admin_card_modal import CartaEditModal

TipoCarta = Literal["Trampa", "Hechizo", "Monstruo", "Especial"]
RarezaCarta = Literal["Común", "Rara", "Legendaria"]

def is_hokage():
    async def predicate(interaction: discord.Interaction) -> bool:
        hokage_id = interaction.client.hokage_role_id
        if not hokage_id: return False
        role = interaction.guild.get_role(hokage_id)
        if role in interaction.user.roles: return True
        if interaction.user.guild_permissions.administrator: return True
        return False
    return app_commands.check(predicate)

# --- ¡¡¡CLASE QUE FALTABA!!! ---
# Esta es la vista (botones) para el comando /aat_admin_vercartas
class CardStockView(discord.ui.View):
    def __init__(self, author_id: int, all_cards: List[Dict[str, Any]]):
        super().__init__(timeout=300) # 5 minutos
        self.author_id = author_id
        self.all_cards = all_cards
        self.current_page = 0
        self.max_pages = len(all_cards)
        
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("No puedes usar este paginador.", ephemeral=True)
            return False
        return True

    def _create_card_embed(self) -> discord.Embed:
        if not self.all_cards:
            return discord.Embed(title="Stock de Cartas", description="No hay cartas creadas en la base de datos.", color=discord.Color.red())

        carta = self.all_cards[self.current_page]
        
        embed = discord.Embed(
            title=f"Carta: {carta['nombre']} (ID: {carta['carta_id']})",
            description=f"*{carta['descripcion']}*",
            color=discord.Color.blue()
        )
        if carta.get('url_imagen'):
            embed.set_image(url=carta['url_imagen'])
        embed.add_field(name="Efecto", value=f"`{carta['efecto']}`", inline=False)
        embed.add_field(name="Rareza", value=carta['rareza'], inline=True)
        embed.add_field(name="Tipo", value=carta['tipo_carta'], inline=True)
        embed.add_field(name="Numeración", value=carta['numeracion'], inline=True)
        embed.set_footer(text=f"Carta {self.current_page + 1} / {self.max_pages}")
        return embed

    def _update_buttons(self):
        # children[0] es 'Anterior', children[1] es 'Siguiente'
        previous_button = self.children[0]
        next_button = self.children[1]

        if isinstance(previous_button, discord.ui.Button):
            previous_button.disabled = (self.current_page == 0)
        if isinstance(next_button, discord.ui.Button):
            next_button.disabled = (self.current_page >= self.max_pages - 1)

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self._update_buttons()
        embed = self._create_card_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Siguiente", style=discord.ButtonStyle.primary, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self._update_buttons()
        embed = self._create_card_embed()
        await interaction.response.edit_message(embed=embed, view=self)
# --- FIN DE LA CLASE QUE FALTABA ---


@is_hokage()
class AdminCog(commands.Cog, name="Economia Admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economia_db: EconomiaDBManagerV2 = bot.economia_db
        self.card_db: CardDBManager = bot.card_db
        self.log = logging.getLogger(self.__class__.__name__)
        super().__init__()

    async def card_stock_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        cartas = self.card_db.get_cartas_stock_by_name(current)
        return [
            app_commands.Choice(name=f"{c['numeracion']} | {c['nombre']}", value=str(c['carta_id']))
            for c in cartas
        ]

    @app_commands.command(name="aat_admin_darpuntos", description="[ADMIN] Da puntos a un usuario.")
    @app_commands.describe(usuario="El usuario", cantidad="Cuántos puntos dar", razon="Opcional: Razón")
    async def dar_puntos(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int, razon: Optional[str] = None):
        if cantidad <= 0:
            await interaction.response.send_message("La cantidad debe ser positiva.", ephemeral=True)
            return
        nuevo_total = self.economia_db.modify_points(usuario.id, cantidad, gastar=False)
        await interaction.response.send_message(f"✅ Se dieron {cantidad} puntos a {usuario.mention}. Ahora tiene {nuevo_total} puntos.", ephemeral=True)
        try:
            msg = f"Has recibido **{cantidad} puntos** de un administrador."
            if razon: msg += f"\n**Razón:** {razon}"
            await usuario.send(msg)
        except discord.Forbidden: pass

    @app_commands.command(name="aat_admin_sacarpuntos", description="[ADMIN] Quita puntos a un usuario.")
    @app_commands.describe(usuario="El usuario", cantidad="Cuántos puntos quitar", razon="Opcional: Razón")
    async def sacar_puntos(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int, razon: Optional[str] = None):
        if cantidad <= 0:
            await interaction.response.send_message("La cantidad debe ser positiva.", ephemeral=True)
            return
        nuevo_total = self.economia_db.modify_points(usuario.id, cantidad, gastar=True)
        await interaction.response.send_message(f"🗑️ Se quitaron {cantidad} puntos a {usuario.mention}. Ahora tiene {nuevo_total} puntos.", ephemeral=True)
        try:
            msg = f"Se te han quitado **{cantidad} puntos** por un administrador."
            if razon: msg += f"\n**Razón:** {razon}"
            await usuario.send(msg)
        except discord.Forbidden: pass

    @app_commands.command(name="aat_admin_darblister", description="[ADMIN] Da blisters (sobres) a un usuario.")
    @app_commands.describe(usuario="El usuario", tipo_blister="El tipo de blister (ej: 'trampa')", cantidad="Cuántos blisters dar")
    async def dar_blister(self, interaction: discord.Interaction, usuario: discord.Member, tipo_blister: str, cantidad: int):
        if cantidad <= 0:
            await interaction.response.send_message("La cantidad debe ser positiva.", ephemeral=True)
            return
        tipo_blister = tipo_blister.lower().strip()
        nuevo_total = self.economia_db.modify_blisters(usuario.id, tipo_blister, cantidad)
        await interaction.response.send_message(f"🎁 Se dieron {cantidad} blister(s) de tipo '{tipo_blister}' a {usuario.mention}. Ahora tiene {nuevo_total} de ese tipo.", ephemeral=True)
        try:
            await usuario.send(f"¡Has recibido **{cantidad} Blister(s) de tipo '{tipo_blister}'** de un administrador!")
        except discord.Forbidden: pass

    @app_commands.command(name="aat_admin_setcreditos", description="[ADMIN] Establece los créditos para fijar mensajes de un usuario.")
    @app_commands.describe(usuario="El usuario", cantidad="El número total de créditos que tendrá")
    async def set_creditos(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        if cantidad < 0:
            await interaction.response.send_message("La cantidad no puede ser negativa.", ephemeral=True)
            return
        self.economia_db.set_credits(usuario.id, cantidad)
        await interaction.response.send_message(f"📌 Se establecieron los créditos de {usuario.mention} a {cantidad}.", ephemeral=True)

    @app_commands.command(name="aat_admin_crear_carta", description="[ADMIN] Añade una nueva carta al stock global.")
    @app_commands.describe(nombre="Nombre exacto", rareza="Rareza", tipo_carta="Tipo", url_imagen="Link PERMANENTE", numeracion="Código (ej: AAT-001)", descripcion="Texto 'flavor'", efecto="Poder de la carta")
    async def crear_carta(self, interaction: discord.Interaction, nombre: str, rareza: RarezaCarta, tipo_carta: TipoCarta, url_imagen: str, numeracion: str, descripcion: Optional[str] = "Sin descripción.", efecto: Optional[str] = "Sin efecto."):
        await interaction.response.defer(ephemeral=True)
        success = self.card_db.add_carta_stock(nombre, descripcion, efecto, url_imagen, rareza, tipo_carta, numeracion)
        if not success:
            await interaction.followup.send(f"❌ Error: Ya existe una carta con el nombre '{nombre}'.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Nueva Carta Creada: {nombre}", description=f"*{descripcion}*", color=discord.Color.green())
        embed.set_image(url=url_imagen)
        embed.add_field(name="Efecto", value=efecto, inline=False)
        embed.add_field(name="Rareza", value=rareza, inline=True)
        embed.add_field(name="Tipo", value=tipo_carta, inline=True)
        embed.add_field(name="Numeración", value=numeracion, inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aat_admin_modificar_carta", description="[ADMIN] Modifica una carta existente en el stock.")
    @app_commands.autocomplete(carta_id=card_stock_autocomplete)
    @app_commands.describe(carta_id="Elige la carta a modificar (usa el autocompletado).")
    async def modificar_carta(self, interaction: discord.Interaction, carta_id: str):
        if not carta_id.isdigit():
            await interaction.response.send_message("ID de carta inválido. Debes usar el autocompletado.", ephemeral=True)
            return
        carta_data = self.card_db.get_carta_stock_by_id(int(carta_id))
        if not carta_data:
            await interaction.response.send_message("No se encontró esa carta en la base de datos.", ephemeral=True)
            return
        modal = CartaEditModal(carta_data, self.card_db)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="aat_admin_borrar_carta", description="[ADMIN] BORRA una carta del stock (¡PELIGRO!).")
    @app_commands.autocomplete(carta_id=card_stock_autocomplete)
    @app_commands.describe(carta_id="Elige la carta a borrar (usa el autocompletado).")
    async def borrar_carta(self, interaction: discord.Interaction, carta_id: str):
        if not carta_id.isdigit():
            await interaction.response.send_message("ID de carta inválido. Debes usar el autocompletado.", ephemeral=True)
            return
        carta_data = self.card_db.get_carta_stock_by_id(int(carta_id))
        if not carta_data:
            await interaction.response.send_message("No se encontró esa carta en la base de datos.", ephemeral=True)
            return
        self.card_db.delete_carta_stock(int(carta_id))
        await interaction.response.send_message(f"🗑️ Carta '{carta_data['nombre']}' borrada permanentemente del stock.", ephemeral=True)

    @app_commands.command(name="aat_admin_vercartas", description="[ADMIN] Muestra todas las cartas creadas en el stock.")
    async def ver_cartas(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        all_cards = self.card_db.get_all_cards_stock()
        
        if not all_cards:
            await interaction.followup.send("No hay cartas creadas en el stock.", ephemeral=True)
            return
            
        # --- ¡¡¡AQUÍ ESTÁ EL ARREGLO!!! ---
        # Ahora 'CardStockView' está definida en este archivo
        view = CardStockView(interaction.user.id, all_cards)
        embed = view._create_card_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))