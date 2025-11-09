# cogs/economia/cartas_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List, Literal, Dict, Any
import logging
import datetime

from .db_manager import EconomiaDBManagerV2
from .card_db_manager import CardDBManager

TipoBlister = Literal["trampa"] 
CantidadBlister = Literal["1", "5", "todos"]
# --- MODIFICADO: "Todas" es ahora una opción y es la por defecto ---
TipoCartaCatalogo = Literal["Todas", "Trampa", "Hechizo", "Monstruo", "Especial"]

# --- VISTA DE PAGINACIÓN PARA EL CATÁLOGO PÚBLICO ---
class StockCatalogView(discord.ui.View):
    def __init__(self, author_id: int, all_cards: List[Dict[str, Any]], title: str):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.all_cards = all_cards
        self.title = title
        self.current_page = 0
        self.cards_per_page = 15
        self.max_pages = (len(all_cards) + self.cards_per_page - 1) // self.cards_per_page
        
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("No puedes usar este paginador. Usa `/aat_catalogo` para ver el tuyo.", ephemeral=True)
            return False
        return True

    def get_page_embed(self) -> discord.Embed:
        """Crea el embed para la página actual."""
        start_index = self.current_page * self.cards_per_page
        end_index = start_index + self.cards_per_page
        cards_on_page = self.all_cards[start_index:end_index]
        
        embed = discord.Embed(
            title=self.title,
            color=discord.Color.blue()
        )
        
        desc = ""
        
        # --- MODIFICADO: Formato de "Tabla" ---
        for card in cards_on_page:
            # Formato: • (AAT-001) Tornado Polvo (Común | Trampa)
            desc += f"• (`{card['numeracion']}`) **{card['nombre']}** ({card['rareza']} | {card['tipo_carta']})\n"
            
        embed.description = desc
        embed.set_footer(text=f"Página {self.current_page + 1} / {self.max_pages} ({len(self.all_cards)} cartas en total)")
        return embed

    def _update_buttons(self):
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
        embed = self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Siguiente", style=discord.ButtonStyle.primary, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self._update_buttons()
        embed = self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)
# --- FIN DE LA VISTA DE PAGINACIÓN ---


class CartasCog(commands.Cog, name="Economia Cartas"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economia_db: EconomiaDBManagerV2 = bot.economia_db
        self.card_db: CardDBManager = bot.card_db
        self.log = logging.getLogger(self.__class__.__name__)
        super().__init__()

    # --- Autocompletados (Sin cambios) ---
    async def blister_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        blisters = self.economia_db.get_blisters_for_user(interaction.user.id)
        return [
            app_commands.Choice(name=f"{b['blister_tipo'].capitalize()} (Tienes: {b['cantidad']})", value=b['blister_tipo'])
            for b in blisters if current.lower() in b['blister_tipo'].lower()
        ]
        
    async def card_inventory_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        cartas_raw = self.economia_db.get_cards_in_inventory(interaction.user.id)
        choices = []
        for c in cartas_raw:
            carta_stock = self.card_db.get_carta_stock_by_id(c['carta_id'])
            if not carta_stock: continue
            carta_id_str = str(c['carta_id'])
            name = f"x{c['cantidad']} | #{carta_id_str}: {carta_stock['nombre']} ({carta_stock['numeracion']})"
            if len(name) > 100: name = name[:97] + "..."
            if (current.lower() in carta_stock['nombre'].lower() or 
                current.lower() in carta_stock['numeracion'].lower() or
                current == carta_id_str):
                choices.append(app_commands.Choice(name=name, value=carta_id_str))
        return choices[:25]

    # --- Comandos (Sin cambios hasta el catálogo) ---
    @app_commands.command(name="aat_puntos", description="Muestra cuántos puntos tienes.")
    async def mis_puntos(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_data = self.economia_db.get_user_economy(interaction.user.id)
        embed = discord.Embed(title=f"🪙 Puntos de {interaction.user.display_name}", description=f"Tienes **{user_data['puntos_actuales']}** puntos para gastar.", color=discord.Color.gold())
        embed.add_field(name="Total Conseguido", value=f"{user_data['puntos_conseguidos']}", inline=True)
        embed.add_field(name="Total Gastado", value=f"{user_data['puntos_gastados']}", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aat_inventario", description="Muestra tu stash de puntos, créditos y blisters.")
    async def inventario(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        eco_data = self.economia_db.get_user_economy(user_id)
        blisters = self.economia_db.get_blisters_for_user(user_id)
        embed = discord.Embed(title=f"Inventario de {interaction.user.display_name}", color=discord.Color.dark_green())
        embed.add_field(name="🪙 Puntos Actuales", value=f"{eco_data['puntos_actuales']}", inline=True)
        embed.add_field(name="📌 Créditos para Fijar", value=f"{eco_data['creditos_pin']}", inline=True)
        blister_desc = "No tienes blisters.\n¡Gana más con `/aat_reclamar diaria`!"
        if blisters:
            blister_desc = ""
            for b in blisters:
                blister_desc += f"• **Blister de {b['blister_tipo'].capitalize()}**: x{b['cantidad']}\n"
        embed.add_field(name="🃏 Blisters (Sobres)", value=blister_desc, inline=False)
        embed.set_footer(text="Usa /aat_abrirblister para abrir tus sobres.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aat_abrirblister", description="Abre blisters (sobres) de tu inventario.")
    @app_commands.autocomplete(tipo=blister_autocomplete)
    @app_commands.describe(tipo="El tipo de blister que quieres abrir.", cantidad="Cuántos quieres abrir (1, 5, o todos).")
    async def abrir_blister(self, interaction: discord.Interaction, tipo: str, cantidad: CantidadBlister):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        tipo = tipo.lower().strip()
        blisters = self.economia_db.get_blisters_for_user(user_id)
        blister_a_abrir = next((b for b in blisters if b['blister_tipo'] == tipo), None)
        if not blister_a_abrir or blister_a_abrir['cantidad'] <= 0:
            await interaction.followup.send(f"No tienes blisters de tipo '{tipo}' para abrir.", ephemeral=True)
            return
        cantidad_a_abrir = 0
        if cantidad == "todos":
            cantidad_a_abrir = blister_a_abrir['cantidad']
        else:
            cantidad_a_abrir = int(cantidad)
        if cantidad_a_abrir > blister_a_abrir['cantidad']:
            await interaction.followup.send(f"Solo tienes {blister_a_abrir['cantidad']} blister(s) de tipo '{tipo}', no puedes abrir {cantidad_a_abrir}.", ephemeral=True)
            return
        self.economia_db.modify_blisters(user_id, tipo, -cantidad_a_abrir)
        cartas_obtenidas = []
        for _ in range(cantidad_a_abrir * 3): 
            carta = self.card_db.get_random_card_by_rarity(tipo_carta=tipo) 
            if carta:
                self.economia_db.add_card_to_inventory(user_id, carta['carta_id'], 1)
                cartas_obtenidas.append(carta)
        if not cartas_obtenidas:
            self.economia_db.modify_blisters(user_id, tipo, cantidad_a_abrir)
            await interaction.followup.send(f"¡Error! No hay cartas en el stock para el tipo de blister '{tipo}'. Contacta a un admin. (Tus blisters han sido devueltos).", ephemeral=True)
            return
        embed = discord.Embed(title=f"¡Has abierto {cantidad_a_abrir} Blister(s) de {tipo.capitalize()}!", color=discord.Color.purple())
        conteo_cartas = {}
        for carta in cartas_obtenidas:
            nombre = f"**{carta['nombre']}** ({carta['rareza']})"
            conteo_cartas[nombre] = conteo_cartas.get(nombre, 0) + 1
        desc = "¡Recibiste las siguientes cartas!:\n\n"
        for nombre, num in conteo_cartas.items():
            desc += f"• {nombre} (x{num})\n"
        embed.description = desc
        embed.set_footer(text="Puedes ver tu colección completa con /aat_miscartas")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aat_miscartas", description="Muestra tu inventario de cartas.")
    async def mis_cartas(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cartas_inv = self.economia_db.get_cards_in_inventory(interaction.user.id)
        embed = discord.Embed(title=f"Inventario de Cartas de {interaction.user.display_name}", color=discord.Color.blue())
        if not cartas_inv:
            embed.description = "No tienes ninguna carta. ¡Gana blisters con `/aat_reclamar diaria`!"
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        desc = ""
        for carta_data in cartas_inv:
            carta_stock = self.card_db.get_carta_stock_by_id(carta_data['carta_id'])
            if carta_stock:
                desc += f"• **ID: {carta_stock['carta_id']}** | {carta_stock['nombre']} (`{carta_stock['numeracion']}`) - {carta_stock['rareza']} (x{carta_data['cantidad']})\n"
        if not desc:
             embed.description = "Tus cartas parecen no existir en el stock. Contacta a un admin."
        else:
            embed.description = desc
        embed.set_footer(text="Usa /aat_vermicarta [carta] para ver el detalle de una carta.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aat_usar_carta", description="Usa una carta trampa consumible de tu inventario.")
    @app_commands.autocomplete(carta_id=card_inventory_autocomplete)
    @app_commands.describe(carta_id="La carta que quieres usar", usuario_objetivo="El usuario al que quieres afectar.", mensaje_objetivo_id="Opcional: ID del mensaje al que responder.")
    async def usar_carta(self, interaction: discord.Interaction, carta_id: str, usuario_objetivo: discord.Member, mensaje_objetivo_id: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        if not carta_id.isdigit():
            await interaction.followup.send("ID de carta inválido. Debes usar el autocompletado.", ephemeral=True)
            return
        uso_reciente = self.economia_db.get_card_usage_history(user_id, minutes=10)
        if len(uso_reciente) >= 5:
            await interaction.followup.send("¡Has usado demasiadas cartas! Límite: 5 cartas cada 10 minutos.", ephemeral=True)
            return
        carta_inv = self.economia_db.get_card_from_inventory(user_id, int(carta_id))
        if not carta_inv:
            await interaction.followup.send("No tienes esa carta o no tienes copias.", ephemeral=True)
            return
        self.economia_db.use_card_from_inventory(user_id, int(carta_id))
        self.economia_db.log_card_usage(user_id)
        carta = self.card_db.get_carta_stock_by_id(int(carta_id))
        embed = discord.Embed(title="¡Carta Trampa Activada!", description=f"¡{interaction.user.mention} ha utilizado una carta trampa contra {usuario_objetivo.mention}!", color=discord.Color.red())
        if carta['url_imagen']:
            embed.set_image(url=carta['url_imagen'])
        embed.add_field(name="Título", value=carta['nombre'], inline=False)
        embed.add_field(name="Detalle", value=f"*{carta['descripcion']}*", inline=False)
        embed.add_field(name="Efecto", value=f"`{carta['efecto']}`", inline=False)
        embed.set_footer(text=f"A {interaction.user.display_name} le quedan {carta_inv['cantidad']-1} copias de esta carta.")
        reply_to_message = None
        if mensaje_objetivo_id:
            try:
                reply_to_message = await interaction.channel.fetch_message(int(mensaje_objetivo_id))
            except (discord.NotFound, discord.Forbidden, ValueError): pass
        if reply_to_message:
            await reply_to_message.reply(embed=embed)
        else:
            await interaction.channel.send(embed=embed)
        await interaction.followup.send("¡Carta usada!", ephemeral=True)
        if carta['efecto'] == "MUTE_10_MIN":
            try:
                await usuario_objetivo.timeout(datetime.timedelta(minutes=10), reason=f"Afectado por carta trampa {carta['nombre']}")
                await interaction.channel.send(f"¡{usuario_objetivo.mention} ha sido silenciado por 10 minutos!")
            except Exception as e:
                self.log.warning(f"No se pudo silenciar a {usuario_objetivo.name}: {e}")

    @app_commands.command(name="aat_vermicarta", description="Muestra el detalle de una carta que posees.")
    @app_commands.autocomplete(carta_id=card_inventory_autocomplete)
    @app_commands.describe(carta_id="La carta de tu inventario que quieres ver (puedes usar el ID o el nombre).")
    async def ver_carta(self, interaction: discord.Interaction, carta_id: str):
        await interaction.response.defer(ephemeral=True)
        if not carta_id.isdigit():
            await interaction.followup.send("ID de carta inválido. Debes usar el autocompletado y seleccionar una carta.", ephemeral=True)
            return
        carta_inv = self.economia_db.get_card_from_inventory(interaction.user.id, int(carta_id))
        if not carta_inv:
            await interaction.followup.send("No tienes esa carta en tu inventario.", ephemeral=True)
            return
        carta = self.card_db.get_carta_stock_by_id(int(carta_id))
        if not carta:
            await interaction.followup.send("Error: Esa carta existe en tu inventario pero no en el stock. Contacta a un admin.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Carta: {carta['nombre']} (Tienes x{carta_inv['cantidad']})", description=f"*{carta['descripcion']}*", color=discord.Color.dark_purple())
        if carta.get('url_imagen'):
            embed.set_image(url=carta['url_imagen'])
        embed.add_field(name="Efecto", value=f"`{carta['efecto']}`", inline=False)
        embed.add_field(name="Rareza", value=carta['rareza'], inline=True)
        embed.add_field(name="Tipo", value=carta['tipo_carta'], inline=True)
        embed.add_field(name="Numeración", value=carta['numeracion'], inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- ¡¡¡COMANDO MODIFICADO!!! ---
    @app_commands.command(name="aat_catalogo", description="Muestra todas las cartas que existen en el juego.")
    @app_commands.describe(tipo="El tipo de cartas que quieres ver (default: Todas).")
    async def catalogo(self, interaction: discord.Interaction, tipo: TipoCartaCatalogo = "Todas"):
        await interaction.response.defer(ephemeral=True) # Es un comando público, pero la respuesta es efímera
        
        all_cards = []
        title = ""
        
        if tipo == "Todas":
            all_cards = self.card_db.get_all_cards_stock()
            title = "Catálogo Global de Cartas"
        else:
            all_cards = self.card_db.get_stock_by_type(tipo)
            title = f"Catálogo de Cartas: {tipo}"
        
        if not all_cards:
            await interaction.followup.send(f"No hay cartas de tipo '{tipo}' en el stock.", ephemeral=True)
            return
            
        view = StockCatalogView(interaction.user.id, all_cards, title)
        embed = view.get_page_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(CartasCog(bot))