# cogs/creador/cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging

from cogs.economia.db_manager import EconomiaDBManagerV2

class CreadorCog(commands.Cog, name="Rol de Creador"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(self.__class__.__name__)
        self.economia_db: EconomiaDBManagerV2 = bot.economia_db
        self.shop_config = bot.shop_config
        self.task_config = bot.task_config
        self.costo_rol = 20000 
        self.rol_creador_id = self.shop_config.get("id_rol_contenidos")
        self.canal_contenido_id = self.task_config.get("channels", {}).get("contenido_comunidad")
        self.hokage_role_id = bot.hokage_role_id

    @app_commands.command(name="solicitar_rol_creador", description="Verifica si tienes 20,000+ puntos para obtener el rol Creador (1 sola vez).")
    async def solicitar_rol_creador(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        if not self.rol_creador_id:
            await interaction.followup.send("Error: El ID del Rol de Creador no está configurado. Contacta a un admin.", ephemeral=True)
            return
            
        role = interaction.guild.get_role(self.rol_creador_id)
        if not role:
            await interaction.followup.send("Error: No pude encontrar el rol en el servidor. Contacta a un admin.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.followup.send("¡Ya tienes el rol de Creador de Contenido!", ephemeral=True)
            return

        status = self.economia_db.get_rol_creador_status(user_id)
        if status == 1:
            await interaction.followup.send("Ya has canjeado este rol en el pasado. Si no lo tienes, debes hablar con un administrador para que te lo devuelva.", ephemeral=True)
            return

        user_data = self.economia_db.get_user_economy(user_id)
        if user_data['puntos_actuales'] < self.costo_rol:
            await interaction.followup.send(f"No tienes suficientes puntos. Necesitas **{self.costo_rol}** y tienes **{user_data['puntos_actuales']}**.", ephemeral=True)
            return

        try:
            # self.economia_db.modify_points(user_id, self.costo_rol, gastar=True) # <-- Desactivado como pediste
            self.economia_db.claim_rol_creador(user_id)
            await interaction.user.add_roles(role, reason=f"Verificó {self.costo_rol} puntos")
            
            canal_mention = f"en <#{self.canal_contenido_id}>" if self.canal_contenido_id else "en el canal de comunidad"

            embed = discord.Embed(
                title="¡Felicidades, Creador!",
                description=f"¡Has verificado tus **{self.costo_rol}** puntos y ahora tienes el rol {role.mention}!\n\n"
                            f"**Beneficios:**\n"
                            f"Puedes publicar tu contenido {canal_mention} 2 veces por semana.",
                color=role.color or discord.Color.gold()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("¡Error! Tengo tus puntos, pero no tengo permisos para darte el rol. Contacta a un admin.", ephemeral=True)
        except Exception as e:
            self.log.exception(f"Error al canjear el rol de creador: {e}")
            await interaction.followup.send("Ocurrió un error inesperado.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not self.rol_creador_id or not self.canal_contenido_id:
            return
        if message.channel.id != self.canal_contenido_id:
            return
        if self.hokage_role_id and message.author.get_role(self.hokage_role_id):
            return
        if message.author.guild_permissions.administrator:
            return

        role = message.guild.get_role(self.rol_creador_id)
        if not role:
            self.log.warning(f"No se pudo encontrar el ID_ROL_CONTENIDOS ({self.rol_creador_id})")
            return
            
        if role not in message.author.roles:
            try:
                await message.delete()
                
                # --- ¡¡¡ARREGLO!!! (Añadido '()' ) ---
                embed = discord.Embed(title="Publicación Borrada", description=f"Tu mensaje en <#{message.channel.id}> fue borrado.", color=discord.Color.red())
                embed.add_field(name="Razón", value=f"Solo los usuarios con el rol **{role.name}** pueden publicar en este canal.")
                embed.add_field(name="¿Cómo consigo el rol?", value=f"Puedes obtenerlo si tienes **{self.costo_rol} puntos** de economía.\n"
                                                              f"Usa el comando `/solicitar_rol_creador` para verificar tus puntos.", inline=False)
                await message.author.send(embed=embed)
                
            except discord.Forbidden:
                self.log.warning(f"No pude borrar el mensaje de {message.author.name} ni enviarle DM (ID: {message.id})")
            except Exception as e:
                self.log.error(f"Error al manejar mensaje sin rol de creador: {e}")
            return

        _, semana_key = self.economia_db.get_current_date_keys()
        posts_esta_semana = self.economia_db.get_creator_posts_this_week(message.author.id, semana_key)
        
        post_limit = 2
        
        if len(posts_esta_semana) >= post_limit:
            try:
                await message.delete()
                
                # --- ¡¡¡ARREGLO!!! (Añadido '()' ) ---
                embed = discord.Embed(title="Publicación Borrada", description=f"Tu mensaje en <#{message.channel.id}> fue borrado.", color=discord.Color.orange())
                embed.add_field(name="Razón", value=f"Has alcanzado tu límite de **{post_limit} posts** en el canal de contenido para esta semana.\n"
                                                  f"Podrás volver a postear la próxima semana.")
                await message.author.send(embed=embed)
            except Exception as e:
                self.log.error(f"Error al borrar mensaje de creador (límite alcanzado): {e}")
            return
            
        self.economia_db.log_creator_post(message.author.id, message.id, semana_key)
        self.log.info(f"Post de creador registrado para {message.author.name}. (Post {len(posts_esta_semana) + 1}/{post_limit} esta semana)")

async def setup(bot):
    await bot.add_cog(CreadorCog(bot))