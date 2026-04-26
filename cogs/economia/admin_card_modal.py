# cogs/economia/admin_card_modal.py
import discord
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .card_db_manager import CardDBManager


class CartaEditModal(discord.ui.Modal):
    def __init__(self, carta_data: Dict[str, Any], db: "CardDBManager"):
        super().__init__(title=f"Modificar Carta #{carta_data['carta_id']}")
        self.db = db
        self.carta_data = carta_data

        self.nombre = discord.ui.TextInput(label="Nombre", default=carta_data["nombre"], max_length=100)
        self.descripcion = discord.ui.TextInput(
            label="Descripción",
            style=discord.TextStyle.paragraph,
            default=carta_data.get("descripcion") or "",
            required=False,
            max_length=4000,
        )
        self.efecto = discord.ui.TextInput(
            label="Efecto (código)",
            style=discord.TextStyle.paragraph,
            default=carta_data.get("efecto") or "",
            required=False,
            max_length=1000,
        )
        self.url_imagen = discord.ui.TextInput(label="URL de Imagen", default=carta_data.get("url_imagen") or "")
        self.numeracion = discord.ui.TextInput(
            label="Numeración (ej: AAT-001)", default=carta_data.get("numeracion") or ""
        )
        # Nota: Discord permite máximo 5 inputs por modal.
        # `poder` se conserva (no editable) para no romper el límite.

        self.add_item(self.nombre)
        self.add_item(self.descripcion)
        self.add_item(self.efecto)
        self.add_item(self.url_imagen)
        self.add_item(self.numeracion)

    async def on_submit(self, interaction: discord.Interaction):
        # En `modal_submit`, `defer(ephemeral=True)` sin `thinking=True` usa deferred_message_update
        # (válido para botones en un mensaje), no canal → Discord muestra "La aplicación no ha respondido".
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            poder_val = int(self.carta_data.get("poder", 50))

            ok, err = self.db.update_carta_stock(
                carta_id=self.carta_data["carta_id"],
                nombre=self.nombre.value,
                descripcion=(self.descripcion.value or "").strip() or "Sin descripción.",
                efecto=self.efecto.value or "Sin efecto.",
                url_imagen=self.url_imagen.value,
                numeracion=self.numeracion.value,
                rareza=self.carta_data["rareza"],
                tipo_carta=self.carta_data["tipo_carta"],
                poder=poder_val,
            )

            if ok:
                await interaction.followup.send("✅ Carta actualizada con éxito.", ephemeral=True)
            else:
                await interaction.followup.send(err or "❌ No se pudo guardar la carta.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error al guardar: `{type(e).__name__}` — {e}", ephemeral=True)
