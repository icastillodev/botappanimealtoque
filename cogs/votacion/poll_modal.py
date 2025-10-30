# cogs/votacion/poll_modal.py
import discord
from typing import Dict, Any, TYPE_CHECKING

# Importamos las clases que necesitamos para actualizar el embed
from .poll_view import create_poll_embed, PollView

if TYPE_CHECKING:
    from .db_manager import PollDBManagerV4

class PollEditModal(discord.ui.Modal):
    def __init__(self, poll_data: Dict[str, Any], db: "PollDBManagerV4"):
        super().__init__(title="Modificar Votación")
        
        self.poll_data = poll_data
        self.db = db
        self.message_id = poll_data['message_id']

        # Campo 1: Título
        self.title_input = discord.ui.TextInput(
            label="Título de la Votación",
            style=discord.TextStyle.short,
            default=poll_data.get('title'),
            required=True,
            max_length=256
        )
        self.add_item(self.title_input)

        # Campo 2: Descripción
        self.desc_input = discord.ui.TextInput(
            label="Descripción",
            style=discord.TextStyle.paragraph,
            default=poll_data.get('description'),
            required=False,
            max_length=4000
        )
        self.add_item(self.desc_input)

        # Campo 3: Link de Referencia
        self.link_input = discord.ui.TextInput(
            label="Link de Referencia (opcional)",
            style=discord.TextStyle.short,
            default=poll_data.get('link_url'),
            required=False
        )
        self.add_item(self.link_input)

        # Campo 4: URL de Imagen
        self.image_input = discord.ui.TextInput(
            label="URL de Imagen (opcional)",
            style=discord.TextStyle.short,
            default=poll_data.get('image_url'),
            required=False
        )
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Se llama cuando el admin presiona 'Enviar' en el modal."""
        await interaction.response.defer(ephemeral=True)

        # 1. Obtenemos los nuevos valores
        new_title = self.title_input.value
        new_desc = self.desc_input.value or None # Guardar None si está vacío
        new_link = self.link_input.value or None
        new_image = self.image_input.value or None

        # 2. Actualizamos la Base de Datos
        try:
            self.db.update_poll(self.message_id, new_title, new_desc, new_link, new_image)
        except Exception as e:
            await interaction.followup.send(f"Error al actualizar la base de datos: {e}", ephemeral=True)
            return

        # 3. Actualizamos el mensaje original
        try:
            # Buscamos el canal y el mensaje
            channel = interaction.client.get_channel(self.poll_data['channel_id'])
            if not channel:
                raise discord.NotFound("Canal no encontrado")
            
            poll_message = await channel.fetch_message(self.message_id)
            
            # Obtenemos los datos actualizados
            updated_data = self.db.get_poll_data(self.message_id)
            
            # Recreamos el autor original del embed
            author = None
            if poll_message.embeds and poll_message.embeds[0].footer:
                footer = poll_message.embeds[0].footer
                if footer.text.startswith("Votación creada por "):
                    class FakeAuthor:
                        display_name = footer.text.replace("Votación creada por ", "")
                        display_avatar = footer.icon_url
                    author = FakeAuthor()
            
            # Creamos el nuevo embed con los datos actualizados
            new_embed = create_poll_embed(updated_data, author=author)
            
            # Editamos el mensaje original (la vista de botones no cambia)
            await poll_message.edit(embed=new_embed)
            
            await interaction.followup.send("¡Votación modificada con éxito!", ephemeral=True)

        except (discord.NotFound, discord.Forbidden):
            await interaction.followup.send("No pude encontrar el mensaje original para editarlo, pero la DB fue actualizada.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error al editar el mensaje: {e}", ephemeral=True)