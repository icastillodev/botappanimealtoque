# cogs/votacion/cog.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, List, Literal, TYPE_CHECKING
import logging
import time
import datetime

if TYPE_CHECKING:
    from .db_manager import PollDBManagerV5

from .poll_view import PollView, create_poll_embed
from .poll_modal import PollEditModal

VoteDisplayFormat = Literal["Ambos (Números y %)", "Solo Números", "Solo Porcentaje", "Ocultar hasta el cierre"]
UserPollDuration = Literal["10 Minutos", "20 Minutos", "30 Minutos", "60 Minutos"]

def is_hokage():
    async def predicate(interaction: discord.Interaction) -> bool:
        hokage_id = interaction.client.hokage_role_id
        if not hokage_id: return False
        role = interaction.guild.get_role(hokage_id)
        if role in interaction.user.roles: return True
        if interaction.user.guild_permissions.administrator: return True
        return False
    return app_commands.check(predicate)

# --- VISTA DE AYUDA ---
class PollHelpView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.current_page = 0
        
        self.embeds = [
            self._create_page_1(),
            self._create_page_2(),
            self._create_page_3(),
        ]
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("No puedes usar esta guía, pide la tuya con `/ayudaencuesta`.", ephemeral=True)
            return False
        return True

    def _create_page_1(self) -> discord.Embed:
        embed = discord.Embed(
            title="Ayuda de Votaciones 🗳️ (Página 1/3)",
            description="¡Bienvenido! Aquí aprenderás a crear tus propias votaciones.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="¿Qué es esto?",
            value="Este sistema te permite crear votaciones simples con botones. Tienen un límite de 4 opciones y una duración máxima de 60 minutos.",
            inline=False
        )
        embed.add_field(
            name="Comandos Disponibles",
            value="`/crear_votacion` - Inicia el proceso para crear tu encuesta.\n"
                  "`/mis_resultados` - Muestra (en privado) quién votó qué en una encuesta que tú creaste.",
            inline=False
        )
        embed.set_footer(text="Usa los botones para navegar.")
        return embed

    def _create_page_2(self) -> discord.Embed:
        embed = discord.Embed(
            title="Cómo Crear una Votación (Página 2/3)",
            description="Usar el comando `/crear_votacion` es muy fácil.",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Argumentos Obligatorios",
            value="`titulo`: El nombre de tu encuesta.\n"
                  "`opcion1`: El texto para la primera opción.\n"
                  "`opcion2`: El texto para la segunda opción.\n"
                  "`duracion`: Elige cuánto tiempo durará (10, 20, 30 o 60 minutos).",
            inline=False
        )
        embed.add_field(
            name="Argumentos Opcionales",
            value="`descripcion`: Un texto explicativo bajo el título.\n"
                  "`opcion3`: Texto para la tercera opción.\n"
                  "`opcion4`: Texto para la cuarta opción.\n"
                  "`url_imagen`: Un link (ej: de Imgur) para poner una imagen en la encuesta.",
            inline=False
        )
        return embed
        
    def _create_page_3(self) -> discord.Embed:
        embed = discord.Embed(
            title="Ver tus Resultados (Página 3/3)",
            description="¿Quieres saber quién votó en tu encuesta?",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="Comando `/mis_resultados`",
            value="Este comando es **privado**. Solo tú puedes usarlo y solo tú verás la respuesta.",
            inline=False
        )
        embed.add_field(
            name="¿Cómo funciona?",
            value="1. Escribe `/mis_resultados`.\n"
                  "2. En la opción `votacion_id`, empieza a escribir el título de la votación que creaste.\n"
                  "3. El bot te mostrará una lista (con un ID, ej: `#123: Mi Votación`). ¡Selecciónala!\n"
                  "4. El bot te responderá con un mensaje privado listando quién votó por cada opción.",
            inline=False
        )
        embed.set_footer(text="¡Eso es todo!")
        return embed

    def _update_buttons(self):
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page == len(self.embeds) - 1)

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

    # --- BOTÓN 'CERRAR' ELIMINADO ---
# --- FIN DE LA VISTA DE AYUDA ---


class VotacionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: "PollDBManagerV5" = bot.db_manager
        self.log = logging.getLogger(self.__class__.__name__)
        self.check_expired_polls.start()

    def cog_unload(self):
        self.check_expired_polls.cancel()

    async def votacion_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        polls = self.db.get_active_polls_by_title(current)
        return [
            app_commands.Choice(name=f"#{poll['poll_id']}: {poll['title']}", value=str(poll['message_id']))
            for poll in polls
        ]

    async def my_votacion_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        creator_id = interaction.user.id
        polls = self.db.get_active_polls_by_creator_and_title(creator_id, current)
        return [
            app_commands.Choice(name=f"#{poll['poll_id']}: {poll['title']}", value=str(poll['message_id']))
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

    async def _close_poll_and_update_message(self, poll_data: dict) -> bool:
        message_id = poll_data['message_id']
        channel_id = poll_data['channel_id']
        self.db.close_poll(message_id)
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                self.log.warning(f"No se encontró el canal {channel_id} para cerrar la votación {message_id}")
                return False
            poll_message = await channel.fetch_message(message_id)
            final_poll_data = self.db.get_poll_data(message_id)
            if not final_poll_data:
                self.log.error(f"No se encontraron datos en la DB para {message_id} después de cerrarla.")
                return False
            author = None
            if poll_message.embeds and poll_message.embeds[0].footer:
                footer = poll_message.embeds[0].footer
                if footer.text.startswith("Votación creada por "):
                    class FakeAuthor:
                        display_name = footer.text.replace("Votación creada por ", "")
                        display_avatar = footer.icon_url
                    author = FakeAuthor()
            final_embed = create_poll_embed(final_poll_data, author=author)
            final_view = PollView(poll_options=final_poll_data.get('options'), db_manager=self.db)
            for item in final_view.children:
                item.disabled = True
            await poll_message.edit(embed=final_embed, view=final_view)
            return True
        except discord.NotFound:
            self.log.warning(f"No se encontró el mensaje {message_id} en el canal {channel_id} para cerrarlo.")
            return False
        except Exception as e:
            self.log.exception(f"Error al actualizar el mensaje de votación {message_id}: {e}")
            return False
            
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
            if not poll_data.get('is_active', True):
                for item in new_view.children:
                    item.disabled = True
            await poll_message.edit(embed=new_embed, view=new_view)
            return True, ""
        except Exception as e:
            self.log.error(f"Error al actualizar el mensaje de votación {message_id}: {e}")
            return False, str(e)

    @app_commands.command(name="crear_votacion", description="Crea una votación de usuario simple (max 4 opciones).")
    @app_commands.describe(
        titulo="El título de la votación",
        opcion1="Opción 1",
        opcion2="Opción 2",
        duracion="Cuándo debe terminar la votación.",
        descripcion="Descripción opcional",
        opcion3="Opción 3 (opcional)",
        opcion4="Opción 4 (opcional)",
        url_imagen="URL de una imagen (ej: link de Imgur)"
    )
    async def crear_votacion(self, interaction: discord.Interaction,
                                   titulo: str,
                                   opcion1: str,
                                   opcion2: str,
                                   duracion: UserPollDuration,
                                   descripcion: Optional[str] = None,
                                   opcion3: Optional[str] = None,
                                   opcion4: Optional[str] = None,
                                   url_imagen: Optional[str] = None):
        
        duration_map = {"10 Minutos": 10, "20 Minutos": 20, "30 Minutos": 30, "60 Minutos": 60}
        minutes = duration_map[duracion]
        end_timestamp = int(time.time() + (minutes * 60))
        
        options_labels = [op for op in [opcion1, opcion2, opcion3, opcion4] if op is not None]

        await interaction.response.defer() 

        temp_poll_data = {
            "title": titulo,
            "description": descripcion,
            "link_url": None,
            "image_url": url_imagen,
            "options": [{"label": label, "vote_count": 0} for label in options_labels],
            "limite_votos": 1,
            "formato_votos": "ambos",
            "is_active": True,
            "end_timestamp": end_timestamp
        }

        embed = create_poll_embed(temp_poll_data, author=interaction.user)
        view = PollView(poll_options=None, db_manager=self.db) 
        
        poll_message = await interaction.followup.send(embed=embed, view=view)

        try:
            self.db.add_poll(
                message_id=poll_message.id,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                creator_id=interaction.user.id,
                title=titulo,
                options=options_labels,
                description=descripcion,
                image_url=url_imagen,
                link_url=None,
                limite_votos=1,
                formato_votos="ambos",
                end_timestamp=end_timestamp
            )
        except Exception as e:
            self.log.exception(f"Error al guardar votacion (basica) en DB: {e}")
            await poll_message.delete()
            await interaction.followup.send(f"Error al guardar en la base de datos: {e}", ephemeral=True)
            return

        final_poll_data = self.db.get_poll_data(poll_message.id)
        final_view = PollView(poll_options=final_poll_data['options'], db_manager=self.db)
        final_embed = create_poll_embed(final_poll_data, author=interaction.user)
        await poll_message.edit(embed=final_embed, view=final_view)
        
        await interaction.followup.send(f"¡Votación creada! Terminará automáticamente {discord.utils.format_dt(datetime.datetime.fromtimestamp(end_timestamp), style='R')}.", ephemeral=True)

    @app_commands.command(name="crear_votacionadmin", description="[ADMIN] Crea una votación avanzada.")
    @app_commands.describe(
        titulo="El título de la votación",
        opcion1="Opción de votación 1",
        opcion2="Opción de votación 2",
        duracion_minutos="Opcional: En cuántos minutos debe terminar (ej: 60)",
        fecha_limite="Opcional: Fecha/hora de fin (ej: 25/12/2025 18:00) (ignora minutos)",
        descripcion="Descripción opcional de la votación",
        limite_votos="Cuántas opciones puede elegir un usuario (default: 1)", 
        formato_votos="Cómo mostrar los resultados (default: Ambos)",
        opcion3="Opción 3",
        opcion4="Opción 4",
        opcion5="Opción 5",
        opcion6="Opción 6",
        opcion7="Opción 7",
        opcion8="Opción 8",
        opcion9="Opción 9",
        opcion10="Opción 10",
        url_imagen="URL de una imagen para el embed (ej: link de Imgur)",
        link_referencia="Un link opcional",
        rol_1="Rol 1 para notificar (etiquetar)",
        rol_2="Rol 2 para notificar (etiquetar)",
        rol_3="Rol 3 para notificar (etiquetar)"
    )
    @is_hokage()
    async def crear_votacion_admin(self, interaction: discord.Interaction,
                             titulo: str,
                             opcion1: str,
                             opcion2: str,
                             duracion_minutos: Optional[int] = None,
                             fecha_limite: Optional[str] = None,
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
                             url_imagen: Optional[str] = None, 
                             link_referencia: Optional[str] = None,
                             rol_1: Optional[discord.Role] = None,
                             rol_2: Optional[discord.Role] = None,
                             rol_3: Optional[discord.Role] = None
                             ):
        
        end_timestamp = None
        if fecha_limite:
            try:
                dt_obj = datetime.datetime.strptime(fecha_limite, '%d/%m/%Y %H:%M')
                end_timestamp = int(dt_obj.timestamp())
            except ValueError:
                await interaction.response.send_message("Formato de fecha inválido. Debe ser `DD/MM/YYYY HH:MM` (ej: `25/12/2025 18:00`)", ephemeral=True)
                return
        elif duracion_minutos and duracion_minutos > 0:
            end_timestamp = int(time.time() + (duracion_minutos * 60))

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
            "image_url": url_imagen,
            "options": [{"label": label, "vote_count": 0} for label in options_labels],
            "limite_votos": limite_votos,
            "formato_votos": formato_db,
            "is_active": True,
            "end_timestamp": end_timestamp
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
                image_url=url_imagen,
                link_url=link_referencia,
                limite_votos=limite_votos,
                formato_votos=formato_db,
                end_timestamp=end_timestamp
            )
        except Exception as e:
            self.log.exception(f"Error al guardar votacion (admin) en DB: {e}")
            await poll_message.delete()
            await interaction.followup.send(f"Error al guardar en la base de datos: {e}", ephemeral=True)
            return

        final_poll_data = self.db.get_poll_data(poll_message.id)
        final_view = PollView(poll_options=final_poll_data['options'], db_manager=self.db)
        final_embed = create_poll_embed(final_poll_data, author=interaction.user)
        await poll_message.edit(embed=final_embed, view=final_view)
        
        await interaction.followup.send("¡Votación creada con éxito!", ephemeral=True)

    
    @app_commands.command(name="modificarvotacion", description="[ADMIN] Modifica el título o descripción de una votación activa.")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación que quieres modificar.")
    @is_hokage()
    async def modificar_votacion(self, interaction: discord.Interaction, votacion_id: str):
        if not votacion_id.isdigit():
            await interaction.response.send_message("Error: ID de votación no válida.", ephemeral=True)
            return
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        if not poll_data:
            await interaction.response.send_message("No encontré esa votación.", ephemeral=True)
            return
        if not poll_data['is_active']:
            await interaction.response.send_message("No puedes modificar una votación cerrada.", ephemeral=True)
            return
        modal = PollEditModal(poll_data=poll_data, db=self.db)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="finalizarvotacion", description="[ADMIN] Finaliza una votación manualmente.")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación que quieres finalizar.")
    @is_hokage()
    async def finalizar_votacion(self, interaction: discord.Interaction, votacion_id: str):
        await interaction.response.defer(ephemeral=True)
        if not votacion_id.isdigit():
            await interaction.followup.send("Error: ID de votación no válida.", ephemeral=True)
            return
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        if not poll_data:
            await interaction.followup.send("No encontré esa votación.", ephemeral=True)
            return
        if not poll_data['is_active']:
            await interaction.followup.send("Esa votación ya estaba cerrada.", ephemeral=True)
            return
        
        success = await self._close_poll_and_update_message(poll_data)
        
        if success:
            await interaction.followup.send("Votación cerrada con éxito.", ephemeral=True)
        else:
            await interaction.followup.send("Votación cerrada en la DB, pero no se pudo editar el mensaje.", ephemeral=True)

    @app_commands.command(name="borrarvotacion", description="[ADMIN] Borra una votación permanentemente.")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación que quieres borrar.")
    @is_hokage()
    async def borrar_votacion(self, interaction: discord.Interaction, votacion_id: str):
        await interaction.response.defer(ephemeral=True)
        if not votacion_id.isdigit():
            await interaction.followup.send("Error: ID de votación no válida.", ephemeral=True)
            return
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        if not poll_data:
            await interaction.followup.send("No encontré esa votación.", ephemeral=True)
            return
        self.db.delete_poll(message_id)
        try:
            channel = self.bot.get_channel(poll_data['channel_id'])
            if not channel:
                raise discord.NotFound("Canal no encontrado")
            poll_message = await channel.fetch_message(message_id)
            await poll_message.delete()
        except (discord.NotFound, discord.Forbidden):
            await interaction.followup.send("No pude borrar el mensaje (¿ya fue borrado?), pero la borré de la DB.", ephemeral=True)
            return
        await interaction.followup.send("Votación borrada con éxito.", ephemeral=True)

    @app_commands.command(name="agregaropcion", description="[ADMIN] Añade una nueva opción a una votación activa.")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación.", nombre_opcion="El texto de la nueva opción")
    @is_hokage()
    async def agregar_opcion(self, interaction: discord.Interaction, votacion_id: str, nombre_opcion: str):
        await interaction.response.defer(ephemeral=True)
        if not votacion_id.isdigit():
            await interaction.followup.send("Error: ID de votación no válida.", ephemeral=True)
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
            await interaction.followup.send("Límite de opciones alcanzado.", ephemeral=True)
            return
        if not self.db.add_poll_option(message_id, nombre_opcion):
            await interaction.followup.send("Error al guardar la nueva opción en la DB.", ephemeral=True)
            return
        success, error_msg = await self._update_poll_message(message_id, poll_data['channel_id'])
        if success:
            await interaction.followup.send("¡Opción añadida con éxito!", ephemeral=True)
        else:
            await interaction.followup.send(f"Opción añadida, pero no se pudo editar el mensaje: {error_msg}", ephemeral=True)

    @app_commands.command(name="quitaropcion", description="[ADMIN] Quita una opción de una votación (si no tiene votos).")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete, nombre_opcion=option_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación.", nombre_opcion="Elige la opción que quieres borrar.")
    @is_hokage()
    async def quitar_opcion(self, interaction: discord.Interaction, votacion_id: str, nombre_opcion: str):
        await interaction.response.defer(ephemeral=True)
        if not votacion_id.isdigit():
            await interaction.followup.send("Error: ID de votación no válida.", ephemeral=True)
            return
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        if not poll_data:
            await interaction.followup.send("No se encontró esa votación.", ephemeral=True)
            return
        if not poll_data['is_active']:
            await interaction.followup.send("No puedes quitar opciones de una votación cerrada.", ephemeral=True)
            return
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
            await interaction.followup.send(f"Opción quitada, pero no se pudo editar el mensaje: {error_msg}", ephemeral=True)

    @app_commands.command(name="resultados", description="[ADMIN] Muestra quién votó por qué opción.")
    @app_commands.autocomplete(votacion_id=votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige la votación de la que quieres ver los resultados.")
    @is_hokage()
    async def resultados_votacion(self, interaction: discord.Interaction, votacion_id: str):
        await interaction.response.defer(ephemeral=True)
        if not votacion_id.isdigit():
            await interaction.followup.send("Error: ID de votación no válida.", ephemeral=True)
            return
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        if not poll_data:
            await interaction.followup.send("No se encontró esa votación.", ephemeral=True)
            return
        all_votes = self.db.get_all_votes_for_poll(message_id)
        embed = discord.Embed(title=f"Resultados Detallados: {poll_data['title']}", color=discord.Color.blue())
        if not all_votes:
            embed.description = "Aún no hay votos para esta encuesta."
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        votes_by_option = {}
        for vote in all_votes:
            label = vote['label']
            if label not in votes_by_option:
                votes_by_option[label] = []
            votes_by_option[label].append(vote['user_id'])
        
        for label, user_ids in votes_by_option.items():
            user_mentions = []
            for user_id in user_ids:
                try:
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    user_mentions.append(f"- {user.mention} (`{user.name}`)")
                except discord.NotFound:
                    user_mentions.append(f"- *Usuario Desconocido (`{user_id}`)*")
            value_str = "\n".join(user_mentions) if user_mentions else "*(Sin votos)*"
            if len(value_str) > 1024:
                value_str = value_str[:1020] + "\n..."
            embed.add_field(name=f"Opción: {label} ({len(user_ids)} votos)", value=value_str, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="mis_resultados", description="Muestra los resultados de una votación que tú creaste.")
    @app_commands.autocomplete(votacion_id=my_votacion_autocomplete)
    @app_commands.describe(votacion_id="Elige una de tus votaciones activas.")
    async def mis_resultados(self, interaction: discord.Interaction, votacion_id: str):
        await interaction.response.defer(ephemeral=True)
        if not votacion_id.isdigit():
            await interaction.followup.send("Error: ID de votación no válida.", ephemeral=True)
            return
        message_id = int(votacion_id)
        poll_data = self.db.get_poll_data(message_id)
        if not poll_data or poll_data['creator_id'] != interaction.user.id:
            await interaction.followup.send("No se encontró esa votación o no eres el creador.", ephemeral=True)
            return
        all_votes = self.db.get_all_votes_for_poll(message_id)
        embed = discord.Embed(title=f"Resultados Detallados: {poll_data['title']}", color=discord.Color.blue())
        if not all_votes:
            embed.description = "Aún no hay votos para esta encuesta."
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        votes_by_option = {}
        for vote in all_votes:
            label = vote['label']
            if label not in votes_by_option:
                votes_by_option[label] = []
            votes_by_option[label].append(vote['user_id'])
        for label, user_ids in votes_by_option.items():
            user_mentions = []
            for user_id in user_ids:
                try:
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    user_mentions.append(f"- {user.mention} (`{user.name}`)")
                except discord.NotFound:
                    user_mentions.append(f"- *Usuario Desconocido (`{user_id}`)*")
            value_str = "\n".join(user_mentions) if user_mentions else "*(Sin votos)*"
            if len(value_str) > 1024:
                value_str = value_str[:1020] + "\n..."
            embed.add_field(name=f"Opción: {label} ({len(user_ids)} votos)", value=value_str, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ayudaencuesta", description="Muestra una guía interactiva de los comandos de votación.")
    async def ayudaencuesta(self, interaction: discord.Interaction):
        view = PollHelpView(interaction.user.id)
        embed = view.embeds[0]
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


    @tasks.loop(minutes=1.0)
    async def check_expired_polls(self):
        try:
            current_time = int(time.time())
            expired_polls = self.db.get_expired_polls(current_time)
            
            for poll_data in expired_polls:
                self.log.info(f"Votación {poll_data['message_id']} ha expirado. Cerrando automáticamente...")
                await self._close_poll_and_update_message(poll_data)
                
        except Exception as e:
            self.log.error(f"Error en el loop de expirar votaciones: {e}")

    @check_expired_polls.before_loop
    async def before_check_expired_polls(self):
        await self.bot.wait_until_ready()
        self.log.info("Iniciando loop de revisión de votaciones expiradas.")
        
    @crear_votacion.error
    @crear_votacion_admin.error
    @finalizar_votacion.error
    @borrar_votacion.error
    @modificar_votacion.error
    @agregar_opcion.error
    @quitar_opcion.error
    @resultados_votacion.error
    @mis_resultados.error
    @ayudaencuesta.error
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