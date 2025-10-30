# cogs/votacion/cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List, Literal, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .db_manager import PollDBManagerV4

from .poll_view import PollView, create_poll_embed

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

    # --- ¡¡¡NUEVA FUNCIÓN DE AUTOCOMPLETADO!!! ---
    async def votacion_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Muestra una lista de votaciones activas que coinciden con el título."""
        polls = self.db.get_active_polls_by_title(current)
        return [
            # El 'name' es lo que ve el usuario (el título)
            # El 'value' es lo que recibe el bot (la ID del mensaje)
            app_commands.Choice(name=poll['title'], value=str(poll['message_id']))
            for poll in polls
        ]

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


    # --- ¡¡¡NUEVO COMANDO!!! ---
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
        
        try:
            channel = self.bot.get_channel(poll_data['channel_id'])
            if not channel:
                raise discord.NotFound("Canal no encontrado")
            poll_message = await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden):
            await interaction.followup.send("No pude encontrar el mensaje original de la votación.", ephemeral=True)
            return

        final_poll_data = self.db.get_poll_data(message_id)
        final_embed = create_poll_embed(final_poll_data)

        # Deshabilitar botones en la vista
        final_view = PollView(poll_options=final_poll_data['options'], db_manager=self.db)
        for item in final_view.children:
            item.disabled = True
        
        await poll_message.edit(embed=final_embed, view=final_view)
        await interaction.followup.send("Votación cerrada con éxito.", ephemeral=True)


    # --- ¡¡¡NUEVO COMANDO!!! ---
    @app_commands.command(name="borrarvotacion", description="Borra una votación permanentemente (el mensaje y de la DB).")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación que quieres borrar (empieza a escribir el título).")
    @is_hokage()
    async def borrar_votacion(self, interaction: discord.Interaction, votacion_id: str):
        
        await interaction.response.defer(ephemeral=True)
        
        if not votacion_id.isdigit():
            await interaction.followup.send("Error: La votación seleccionada no tiene una ID válida.", ephemeral=True)
            return
            
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        
        if not poll_data:
            await interaction.followup.send("No encontré una votación con esa ID. (Quizás ya fue borrada)", ephemeral=True)
            return

        # 1. Borrar de la DB
        self.db.delete_poll(message_id)
        
        # 2. Borrar el mensaje de Discord
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


    @crear_votacion.error
    @finalizar_votacion.error # <-- AÑADIDO
    @borrar_votacion.error    # <-- AÑADIDO
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