# cogs/economia/admin_card_modal.py
import discord
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .card_db_manager import CardDBManager # <--- Apunta a la DB de cartas

class CartaEditModal(discord.ui.Modal):
    def __init__(self, carta_data: Dict[str, Any], db: "CardDBManager"): # <--- Acepta CardDBManager
        super().__init__(title=f"Modificar Carta #{carta_data['carta_id']}")
        self.db = db
        self.carta_data = carta_data
        
        self.nombre = discord.ui.TextInput(label="Nombre", default=carta_data['nombre'], max_length=100)
        self.descripcion = discord.ui.TextInput(label="Descripción", style=discord.TextStyle.paragraph, default=carta_data['descripcion'], required=False, max_length=1000)
        self.efecto = discord.ui.TextInput(label="Efecto", style=discord.TextStyle.paragraph, default=carta_data['efecto'], required=False, max_length=1000)
        self.url_imagen = discord.ui.TextInput(label="URL de Imagen", default=carta_data['url_imagen'])
        self.numeracion = discord.ui.TextInput(label="Numeración (ej: AAT-001)", default=carta_data['numeracion'])

        self.add_item(self.nombre)
        self.add_item(self.descripcion)
        self.add_item(self.efecto)
        self.add_item(self.url_imagen)
        self.add_item(self.numeracion)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        success = self.db.update_carta_stock( # <--- Usa la DB de cartas
            carta_id=self.carta_data['carta_id'],
            nombre=self.nombre.value,
            descripcion=self.descripcion.value,
            efecto=self.efecto.value,
            url_imagen=self.url_imagen.value,
            numeracion=self.numeracion.value,
            rareza=self.carta_data['rareza'],
            tipo_carta=self.carta_data['tipo_carta']
        )
        
        if success:
            await interaction.followup.send("✅ Carta actualizada con éxito.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Error: Ya existe una carta con ese nombre.", ephemeral=True)