# cogs/economia/tienda_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal, Dict
import logging

from .db_manager import EconomiaDBManagerV2

class TiendaCog(commands.Cog, name="Economia Tienda"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economia_db: EconomiaDBManagerV2 = bot.economia_db
        self.config = bot.shop_config
        self.log = logging.getLogger(self.__class__.__name__)
        super().__init__()

    @app_commands.command(name="aat_tienda_ver", description="Muestra la tienda de recompensas.")
    async def ver_tienda(self, interaction: discord.Interaction):
        if not self.config:
            await interaction.response.send_message("La tienda está desactivada.", ephemeral=True)
            return
        try:
            price_akatsuki = self.config['price_akatsuki']
            price_jonin = self.config['price_jonin']
            price_pin = self.config['price_pin']
        except KeyError:
            await interaction.response.send_message("Error de configuración de la tienda.", ephemeral=True)
            return

        embed = discord.Embed(title="🏪 Tienda del Servidor", description="Canjea tus puntos por recompensas.", color=discord.Color.orange())
        embed.add_field(name=f"Rol: Akatsuki (ID: `akatsuki`)", value=f"**Precio:** {price_akatsuki} Puntos", inline=False)
        embed.add_field(name=f"Rol: Jonin (ID: `jonin`)", value=f"**Precio:** {price_jonin} Puntos", inline=False)
        embed.add_field(name=f"Fijar Mensaje (ID: `pin`)", value=f"**Precio:** {price_pin} Puntos", inline=False)
        embed.set_footer(text="Usa /aat_tienda_canjear [ID] para comprar.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="aat_tienda_canjear", description="Compra un item de la tienda.")
    @app_commands.describe(item_id="El ID del item que quieres comprar (ej: 'akatsuki', 'pin').")
    async def canjear_item(self, interaction: discord.Interaction, item_id: Literal["akatsuki", "jonin", "pin"]):
        await interaction.response.defer(ephemeral=True)
        if not self.config:
            await interaction.followup.send("La tienda está desactivada.", ephemeral=True)
            return
            
        user_data = self.economia_db.get_user_economy(interaction.user.id)
        item_id = item_id.lower()
        precio = 0
        
        try:
            if item_id == "akatsuki": precio = self.config['price_akatsuki']
            elif item_id == "jonin": precio = self.config['price_jonin']
            elif item_id == "pin": precio = self.config['price_pin']
        except KeyError:
            await interaction.followup.send("Error de configuración para este item.", ephemeral=True)
            return
        if user_data['puntos_actuales'] < precio:
            await interaction.followup.send(f"No tienes suficientes puntos. Necesitas {precio} y tienes {user_data['puntos_actuales']}.", ephemeral=True)
            return
        self.economia_db.modify_points(interaction.user.id, precio, gastar=True)
        if item_id == "akatsuki" or item_id == "jonin":
            role_id_key = "akatsuki_role_id" if item_id == "akatsuki" else "jonin_role_id"
            role_id = self.config.get(role_id_key)
            if not role_id:
                await interaction.followup.send("¡Compra exitosa! Pero... no se encontró el ID del rol en la config. Contacta a un admin.", ephemeral=True)
                return
            role = interaction.guild.get_role(role_id)
            if not role:
                await interaction.followup.send("¡Compra exitosa! Pero... no pude encontrar ese rol en el servidor. Contacta a un admin.", ephemeral=True)
                return
            try:
                await interaction.user.add_roles(role, reason="Comprado en la tienda")
                await interaction.followup.send(f"¡Felicidades! Has canjeado tus puntos por el rol {role.name}.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("¡Compra exitosa! Pero... no tengo permisos para darte ese rol. Contacta a un admin.", ephemeral=True)
        elif item_id == "pin":
            self.economia_db.set_credits(interaction.user.id, user_data['creditos_pin'] + 1)
            await interaction.followup.send("¡Felicidades! Has comprado 1 crédito para fijar mensajes. Úsalo con `/aat_tienda_fijar`.", ephemeral=True)

    @app_commands.command(name="aat_tienda_fijar", description="Usa un crédito de la tienda para fijar un mensaje.")
    @app_commands.describe(id_mensaje="La ID del mensaje que quieres fijar.")
    async def fijar_mensaje(self, interaction: discord.Interaction, id_mensaje: str):
        await interaction.response.defer(ephemeral=True)
        if not id_mensaje.isdigit():
            await interaction.followup.send("La ID del mensaje debe ser un número.", ephemeral=True)
            return
        if not self.economia_db.use_credit(interaction.user.id):
            await interaction.followup.send("No tienes créditos para fijar mensajes. Cómpralos en la `/aat_tienda_ver`.", ephemeral=True)
            return
        try:
            mensaje = await interaction.channel.fetch_message(int(id_mensaje))
            await mensaje.pin(reason=f"Fijado por {interaction.user.name} usando un crédito de la tienda.")
            await interaction.followup.send("¡Mensaje fijado con éxito!", ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send("No pude encontrar ese mensaje en este canal.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("No tengo permisos para fijar mensajes en este canal.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Ocurrió un error: {e}", ephemeral=True)

# --- ¡¡¡AQUÍ ESTÁ EL ARREGLO!!! ---
async def setup(bot):
    await bot.add_cog(TiendaCog(bot))