# cogs/votacion/cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List, Literal, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .db_manager import PollDBManagerV4

from .poll_view import PollView, create_poll_embed
from .poll_modal import PollEditModal

VoteDisplayFormat = Literal["Ambos (Números y %)", "Solo Números", "Solo Porcentaje", "Ocultar hasta el cierre"]

def is_hokage():
    async def predicate(interaction: discord.Interaction) -> bool:
        hokage_id = interaction.client.hokage_role_id
        if not hokage_id: return False
        role = interaction.guild.get_role(hokage_id)
        if role in interaction.user.roles: return True
        if interaction.user.guild_permissions.administrator: return True
        return False
    return app_commands.check(predicate)

class VotacionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: "PollDBManagerV4" = bot.db_manager
        self.log = logging.getLogger(self.__class__.__name__)

    async def votacion_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        polls = self.db.get_active_polls_by_title(current)
        return [
            app_commands.Choice(name=poll['title'], value=str(poll['message_id']))
            for poll in polls
        ]

    async def option_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        votacion_id_str = interaction.namespace.votacion_id
        if not votacion_id_str or not votacion_id_str.isdigit():
            return []
            
        poll_data = self.db.get_poll_data(int(votacion_id_str))
        if not poll_data or not poll_data.get('options'):
            return []
        
        return [
            app_commands.Choice(name=opt['label'], value=opt['label'])
            for opt in poll_data['options']
            if current.lower() in opt['label'].lower()
        ]

    async def _update_poll_message(self, message_id: int, channel_id: int):
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                raise Exception("Canal no encontrado")
            
            poll_message = await channel.fetch_message(message_id)
            poll_data = self.db.get_poll_data(message_id)
            
            if not poll_data:
                raise Exception("Votación no encontrada en DB")

            author = None
            if poll_message.embeds and poll_message.embeds[0].footer:
                footer = poll_message.embeds[0].footer
                if footer.text.startswith("Votación creada por "):
                    class FakeAuthor:
                        display_name = footer.text.replace("Votación creada por ", "")
                        display_avatar = footer.icon_url
                    author = FakeAuthor()

            new_embed = create_poll_embed(poll_data, author=author)
            new_view = PollView(poll_options=poll_data.get('options'), db_manager=self.db)
            
            await poll_message.edit(embed=new_embed, view=new_view)
            return True, ""
            
        except Exception as e:
            self.log.error(f"Error al actualizar el mensaje de votación {message_id}: {e}")
            return False, str(e)

    @app_commands.command(name="crearvotacion", description="Crea una nueva votación con botones.")
    @app_commands.describe(
        titulo="El título de la votación",
        opcion1="Opción de votación 1",
        opcion2="Opción de votación 2",
        descripcion="Descripción opcional de la votación",
        limite_votos="Cuántas opciones puede elegir un usuario (default: 1)", 
        formato_votos="Cómo mostrar los resultados (default: Ambos)",
        opcion3="Opción de votación 3",
        opcion4="Opción de votación 4",
        opcion5="Opción de votación 5",
        opcion6="Opción de votación 6",
        opcion7="Opción de votación 7",
        opcion8="Opción de votación 8",
        opcion9="Opción de votación 9",
        opcion10="Opción de votación 10",
        imagen="Una imagen para el embed",
        link_referencia="Un link opcional",
        rol_1="Rol 1 para notificar (etiquetar)",
        rol_2="Rol 2 para notificar (etiquetar)",
        rol_3="Rol 3 para notificar (etiquetar)"
    )
    @is_hokage()
    async def crear_votacion(self, interaction: discord.Interaction,
                             titulo: str,
                             opcion1: str,
                             opcion2: str,
                             descripcion: Optional[str] = None,
                             limite_votos: Optional[app_commands.Range[int, 1, 10]] = 1,
                             formato_votos: Optional[VoteDisplayFormat] = "Ambos (Números y %)",
                             opcion3: Optional[str] = None,
                             opcion4: Optional[str] = None,
                             opcion5: Optional[str] = None,
                             opcion6: Optional[str] = None,
                             opcion7: Optional[str] = None,
                             opcion8: Optional[str] = None,
                             opcion9: Optional[str] = None,
                             opcion10: Optional[str] = None,
                             imagen: Optional[discord.Attachment] = None,
                             link_referencia: Optional[str] = None,
                             rol_1: Optional[discord.Role] = None,
                             rol_2: Optional[discord.Role] = None,
                             rol_3: Optional[discord.Role] = None
                             ):
        
        options_labels = [
            op for op in [opcion1, opcion2, opcion3, opcion4, opcion5, 
                           opcion6, opcion7, opcion8, opcion9, opcion10] 
            if op is not None
        ]

        await interaction.response.defer() 

        roles_to_ping = [r for r in [rol_1, rol_2, rol_3] if r is not None]
        notification_content = ""
        if roles_to_ping:
            mentions = ' '.join([r.mention for r in roles_to_ping])
            notification_content = f"¡Atención {mentions}! Nueva votación:"

        formato_db = {
            "Ambos (Números y %)": "ambos",
            "Solo Números": "numeros",
            "Solo Porcentaje": "porcentaje",
            "Ocultar hasta el cierre": "oculto"
        }.get(formato_votos, "ambos")

        temp_poll_data = {
            "title": titulo,
            "description": descripcion,
            "link_url": link_referencia,
            "image_url": imagen.url if imagen else None,
            "options": [{"label": label, "vote_count": 0} for label in options_labels],
            "limite_votos": limite_votos,
            "formato_votos": formato_db,
            "is_active": True
        }

        embed = create_poll_embed(temp_poll_data, author=interaction.user)
        view = PollView(poll_options=None, db_manager=self.db) 
        
        poll_message = await interaction.followup.send(
            content=notification_content,
            embed=embed, 
            view=view
        )

        try:
            self.db.add_poll(
                message_id=poll_message.id,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                creator_id=interaction.user.id,
                title=titulo,
                options=options_labels,
                description=descripcion,
                image_url=imagen.url if imagen else None,
                link_url=link_referencia,
                limite_votos=limite_votos,
                formato_votos=formato_db,
                end_timestamp=None
            )
        except Exception as e:
            self.log.exception(f"Error al guardar votacion en DB: {e}")
            await poll_message.delete()
            await interaction.followup.send(f"Error al guardar en la base de datos: {e}", ephemeral=True)
            return

        final_poll_data = self.db.get_poll_data(poll_message.id)
        final_view = PollView(poll_options=final_poll_data['options'], db_manager=self.db)
        await poll_message.edit(view=final_view)
        
        await interaction.followup.send("¡Votación creada con éxito!", ephemeral=True)


    @app_commands.command(name="modificarvotacion", description="Modifica el título o descripción de una votación activa.")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación que quieres modificar (empieza a escribir el título).")
    @is_hokage()
    async def modificar_votacion(self, interaction: discord.Interaction, votacion_id: str):
        
        if not votacion_id.isdigit():
            await interaction.response.send_message("Error: La votación seleccionada no tiene una ID válida.", ephemeral=True)
            return
            
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        
        if not poll_data:
            await interaction.response.send_message("No encontré una votación con esa ID.", ephemeral=True)
            return
        if not poll_data['is_active']:
            await interaction.response.send_message("No puedes modificar una votación que ya está cerrada.", ephemeral=True)
            return

        modal = PollEditModal(poll_data=poll_data, db=self.db)
        await interaction.response.send_modal(modal)


    @app_commands.command(name="finalizarvotacion", description="Finaliza una votación y muestra los resultados.")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación que quieres finalizar (empieza a escribir el título).")
    @is_hokage()
    async def finalizar_votacion(self, interaction: discord.Interaction, votacion_id: str):
        
        await interaction.response.defer(ephemeral=True)

        if not votacion_id.isdigit():
            await interaction.followup.send("Error: La votación seleccionada no tiene una ID válida.", ephemeral=True)
            return
            
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        
        if not poll_data:
            await interaction.followup.send("No encontré una votación con esa ID.", ephemeral=True)
            return
        if not poll_data['is_active']:
            await interaction.followup.send("Esa votación ya estaba cerrada.", ephemeral=True)
            return

        self.db.close_poll(message_id)
        
        success, error_msg = await self._update_poll_message(message_id, poll_data['channel_id'])
        
        if success:
            await interaction.followup.send("Votación cerrada con éxito.", ephemeral=True)
        else:
            await interaction.followup.send(f"Votación cerrada en la DB, pero no se pudo editar el mensaje: {error_msg}", ephemeral=True)


    @app_commands.command(name="borrarvotacion", description="Borra una votación permanentemente (el mensaje y de la DB).")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación que quieres borrar (empieza a escribir el título).")
    @is_hokage()
    async def borrar_votacion(self, interaction: discord.Interaction, votacion_id: str):
        
        await interaction.response.defer(ephemeral=True)
        
        if not votacion_id.isdigit():
            await interaction.response.send_message("Error: La votación seleccionada no tiene una ID válida.", ephemeral=True)
            return
            
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        
        if not poll_data:
            await interaction.response.send_message("No encontré una votación con esa ID. (Quizás ya fue borrada)", ephemeral=True)
            return

        self.db.delete_poll(message_id)
        
        try:
            channel = self.bot.get_channel(poll_data['channel_id'])
            if not channel:
                raise discord.NotFound("Canal no encontrado")
            poll_message = await channel.fetch_message(message_id)
            await poll_message.delete()
            
        except (discord.NotFound, discord.Forbidden):
            await interaction.followup.send("No pude borrar el mensaje original (¿ya fue borrado?), pero la borré de la base de datos.", ephemeral=True)
            return
            
        await interaction.followup.send("Votación borrada con éxito.", ephemeral=True)

    @app_commands.command(name="agregaropcion", description="Añade una nueva opción a una votación activa.")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(
        votacion_id="Elige la votación (empieza a escribir el título).",
        nombre_opcion="El texto de la nueva opción (ej: 'Opción C')"
    )
    @is_hokage()
    async def agregar_opcion(self, interaction: discord.Interaction, votacion_id: str, nombre_opcion: str):
        await interaction.response.defer(ephemeral=True)
        
        if not votacion_id.isdigit():
            await interaction.followup.send("Error: La votación seleccionada no tiene una ID válida.", ephemeral=True)
            return
        
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)

        if not poll_data:
            await interaction.followup.send("No se encontró esa votación.", ephemeral=True)
            return
        if not poll_data['is_active']:
            await interaction.followup.send("No puedes añadir opciones a una votación cerrada.", ephemeral=True)
            return
        
        if len(poll_data.get('options', [])) >= 24:
            await interaction.followup.send("No se pueden añadir más opciones, se alcanzó el límite.", ephemeral=True)
            return
            
        success = self.db.add_poll_option(message_id, nombre_opcion)
        if not success:
            await interaction.followup.send("Error al guardar la nueva opción en la DB.", ephemeral=True)
            return
            
        success, error_msg = await self._update_poll_message(message_id, poll_data['channel_id'])
        if success:
            await interaction.followup.send("¡Opción añadida con éxito!", ephemeral=True)
        else:
            await interaction.followup.send(f"Opción añadida a la DB, pero no se pudo editar el mensaje: {error_msg}", ephemeral=True)

    @app_commands.command(name="quitaropcion", description="Quita una opción de una votación (si no tiene votos).")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete, nombre_opcion=option_autocomplete)
    @app_commands.describe(
        votacion_id="Elige la votación (empieza a escribir el título).",
        nombre_opcion="Elige la opción que quieres borrar."
    )
    @is_hokage()
    async def quitar_opcion(self, interaction: discord.Interaction, votacion_id: str, nombre_opcion: str):
        await interaction.response.defer(ephemeral=True)

        if not votacion_id.isdigit():
            await interaction.followup.send("Error: La votación seleccionada no tiene una ID válida.", ephemeral=True)
            return

        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)

        if not poll_data:
            await interaction.followup.send("No se encontró esa votación.", ephemeral=True)
            return
        if not poll_data['is_active']:
            await interaction.followup.send("No puedes quitar opciones de una votación cerrada.", ephemeral=True)
            return
            
        # --- ¡¡¡MODIFICADO!!! ---
        # Llama a la v2 (que usa TRIM)
        option_to_remove = self.db.get_option_by_label_v2(message_id, nombre_opcion)
        if not option_to_remove:
            await interaction.followup.send(f"No se encontró una opción con el nombre exacto: '{nombre_opcion}'", ephemeral=True)
            return
            
        option_id = option_to_remove['option_id']
        remove_status = self.db.remove_poll_option(option_id)
        
        if remove_status != "Opción borrada con éxito.":
            await interaction.followup.send(f"Error: {remove_status}", ephemeral=True)
            return
            
        success, error_msg = await self._update_poll_message(message_id, poll_data['channel_id'])
        if success:
            await interaction.followup.send("¡Opción quitada con éxito!", ephemeral=True)
        else:
            await interaction.followup.send(f"Opción quitada de la DB, pero no se pudo editar el mensaje: {error_msg}", ephemeral=True)


    @crear_votacion.error
    @finalizar_votacion.error
    @borrar_votacion.error
    @modificar_votacion.error
    @agregar_opcion.error
    @quitar_opcion.error
    async def on_poll_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("Este comando es solo para el rol 'Hokage' o Administradores.", ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("No tienes permisos para hacer esto.", ephemeral=True)
        else:
            self.log.exception(f"Error inesperado en VotacionCog: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Ocurrió un error inesperado.", ephemeral=True)
            else:
                await interaction.followup.send("Ocurrió un error inesperado.", ephemeral=True)