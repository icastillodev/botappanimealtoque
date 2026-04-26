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
        # Solo en servidor (en DM no hay roles ni permisos de guild).
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        hokage_id = getattr(interaction.client, "hokage_role_id", None)
        if not hokage_id:
            return False
        role = interaction.guild.get_role(int(hokage_id))
        if role is None:
            return False
        return role in interaction.user.roles
    return app_commands.check(predicate)

# --- ¡¡¡CLASE QUE FALTABA!!! ---
# Esta es la vista (botones) para el comando /aat-admin-vercartas
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
        embed.add_field(name="Poder (duelos)", value=str(carta.get("poder", 50)), inline=True)
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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Backstop de permisos: asegura que los slash de este Cog sean solo admin/Hokage,
        incluso si el decorator de clase no se aplicara como se espera.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        hokage_id = getattr(interaction.client, "hokage_role_id", None)
        if not hokage_id:
            return False
        role = interaction.guild.get_role(int(hokage_id))
        if role is None:
            return False
        return role in interaction.user.roles

    async def card_stock_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        cartas = self.card_db.get_cartas_stock_by_name(current)
        choices: List[app_commands.Choice[str]] = []
        for c in cartas:
            cid = int(c["carta_id"])
            num = (c.get("numeracion") or "—").strip()
            nom = (c.get("nombre") or "?").strip()
            label = f"#{cid} · {num} · {nom}"
            if len(label) > 100:
                label = label[:97] + "…"
            choices.append(app_commands.Choice(name=label, value=str(cid)))
        return choices[:25]

    @app_commands.command(name="aat-admin-darpuntos", description="[ADMIN] Da puntos a un usuario.")
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

    @app_commands.command(name="aat-admin-sacarpuntos", description="[ADMIN] Quita puntos a un usuario.")
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

    @app_commands.command(
        name="aat-admin-quitarhistorico",
        description="[ADMIN] Quita puntos del histórico (total conseguido) de un usuario.",
    )
    @app_commands.describe(usuario="El usuario", cantidad="Cuántos puntos históricos quitar", razon="Opcional: Razón")
    async def quitar_historico(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        cantidad: int,
        razon: Optional[str] = None,
    ):
        if cantidad <= 0:
            await interaction.response.send_message("La cantidad debe ser positiva.", ephemeral=True)
            return
        res = self.economia_db.remove_historic_points(usuario.id, int(cantidad))
        await interaction.response.send_message(
            (
                f"🧾 Se quitaron **{cantidad}** puntos del **histórico** de {usuario.mention}.\n"
                f"Ahora: actuales **{res['actual']}** · histórico **{res['conseguidos']}** · gastados **{res['gastados']}**."
            ),
            ephemeral=True,
        )
        try:
            msg = f"Un admin ajustó tu **histórico**: -{cantidad} puntos."
            if razon:
                msg += f"\n**Razón:** {razon}"
            await usuario.send(msg)
        except discord.Forbidden:
            pass

    @app_commands.command(name="aat-admin-darblister", description="[ADMIN] Da blisters (sobres) a un usuario.")
    @app_commands.rename(tipo_blister="tipo-blister")
    @app_commands.describe(usuario="El usuario", tipo_blister="El tipo de blister (ej: 'trampa')", cantidad="Cuántos blisters dar")
    async def dar_blister(self, interaction: discord.Interaction, usuario: discord.Member, tipo_blister: str, cantidad: int):
        if cantidad <= 0:
            await interaction.response.send_message("La cantidad debe ser positiva.", ephemeral=True)
            return
        tipo_blister = tipo_blister.lower().strip()
        nuevo_total, bcol = self.economia_db.modify_blisters(usuario.id, tipo_blister, cantidad)
        extra = ("\n" + "\n".join(bcol)) if bcol else ""
        await interaction.response.send_message(
            f"🎁 Se dieron {cantidad} blister(s) de tipo '{tipo_blister}' a {usuario.mention}. Ahora tiene {nuevo_total} de ese tipo.{extra}",
            ephemeral=True,
        )
        try:
            await usuario.send(f"¡Has recibido **{cantidad} Blister(s) de tipo '{tipo_blister}'** de un administrador!")
        except discord.Forbidden: pass

    @app_commands.command(name="aat-admin-quitarblister", description="[ADMIN] Quita blisters (sobres) a un usuario.")
    @app_commands.rename(tipo_blister="tipo-blister")
    @app_commands.describe(
        usuario="El usuario",
        tipo_blister="El tipo de blister (ej: 'trampa')",
        cantidad="Cuántos blisters quitar (si no tiene, queda en 0)",
    )
    async def quitar_blister(self, interaction: discord.Interaction, usuario: discord.Member, tipo_blister: str, cantidad: int):
        if cantidad <= 0:
            await interaction.response.send_message("La cantidad debe ser positiva.", ephemeral=True)
            return
        tipo_blister = tipo_blister.lower().strip()
        nuevo_total, _ = self.economia_db.modify_blisters(usuario.id, tipo_blister, -abs(int(cantidad)))
        await interaction.response.send_message(
            f"🗑️ Se quitaron {cantidad} blister(s) de tipo '{tipo_blister}' a {usuario.mention}. Ahora tiene {nuevo_total}.",
            ephemeral=True,
        )
        try:
            await usuario.send(f"Un admin te quitó **{cantidad}** blister(s) de tipo '{tipo_blister}'. Ahora tenés {nuevo_total}.")
        except discord.Forbidden:
            pass

    @app_commands.command(
        name="aat-admin-vereconomia",
        description="[ADMIN] Ver puntos (actual/hist/gastado) y blisters de un usuario.",
    )
    @app_commands.describe(usuario="El usuario")
    async def ver_economia_usuario(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer(ephemeral=True)
        self.economia_db.ensure_user_exists(usuario.id)
        eco = self.economia_db.get_user_economy(usuario.id) or {}
        blisters = self.economia_db.get_blisters_for_user(usuario.id)

        puntos_actuales = int(eco.get("puntos_actuales") or 0)
        puntos_conseguidos = int(eco.get("puntos_conseguidos") or 0)
        puntos_gastados = int(eco.get("puntos_gastados") or 0)
        creditos_pin = int(eco.get("creditos_pin") or 0)

        if blisters:
            b_lines = []
            for b in blisters:
                t = str(b.get("blister_tipo") or "?")
                c = int(b.get("cantidad") or 0)
                if c <= 0:
                    continue
                b_lines.append(f"• **{t}**: x**{c}**")
            b_txt = "\n".join(b_lines) if b_lines else "—"
        else:
            b_txt = "—"

        embed = discord.Embed(
            title=f"📊 Economía — {usuario.display_name}",
            description=f"ID: `{usuario.id}`",
            color=discord.Color.dark_teal(),
        )
        embed.add_field(name="Toque points (actual)", value=str(puntos_actuales), inline=True)
        embed.add_field(name="Histórico (conseguidos)", value=str(puntos_conseguidos), inline=True)
        embed.add_field(name="Gastados", value=str(puntos_gastados), inline=True)
        embed.add_field(name="Créditos pin", value=str(creditos_pin), inline=True)
        embed.add_field(name="Blisters", value=b_txt, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aat-admin-setcreditos", description="[ADMIN] Establece los créditos para fijar mensajes de un usuario.")
    @app_commands.describe(usuario="El usuario", cantidad="El número total de créditos que tendrá")
    async def set_creditos(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        if cantidad < 0:
            await interaction.response.send_message("La cantidad no puede ser negativa.", ephemeral=True)
            return
        self.economia_db.set_credits(usuario.id, cantidad)
        await interaction.response.send_message(f"📌 Se establecieron los créditos de {usuario.mention} a {cantidad}.", ephemeral=True)

    @app_commands.command(name="aat-admin-crear-carta", description="[ADMIN] Añade una nueva carta al stock global.")
    @app_commands.rename(tipo_carta="tipo-carta", url_imagen="url-imagen")
    @app_commands.describe(
        nombre="Nombre exacto",
        rareza="Rareza",
        tipo_carta="Tipo",
        url_imagen="Link PERMANENTE",
        numeracion="Código (ej: AAT-001)",
        descripcion="Texto 'flavor'",
        efecto="Código de efecto (ej: MUTE_10_MIN, BROMA_DM, BROMA_EPHEMERAL) — mecánicos solo Rara/Legendaria",
        poder="Número de poder para duelos (default 50)",
    )
    async def crear_carta(
        self,
        interaction: discord.Interaction,
        nombre: str,
        rareza: RarezaCarta,
        tipo_carta: TipoCarta,
        url_imagen: str,
        numeracion: str,
        descripcion: Optional[str] = "Sin descripción.",
        efecto: Optional[str] = "Sin efecto.",
        poder: int = 50,
    ):
        await interaction.response.defer(ephemeral=True)
        ok, err = self.card_db.add_carta_stock(
            nombre, descripcion, efecto, url_imagen, rareza, tipo_carta, numeracion, poder=int(poder)
        )
        if not ok:
            await interaction.followup.send(err or "❌ No se pudo crear la carta.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Nueva Carta Creada: {nombre}", description=f"*{descripcion}*", color=discord.Color.green())
        embed.set_image(url=url_imagen)
        embed.add_field(name="Efecto", value=efecto, inline=False)
        embed.add_field(name="Rareza", value=rareza, inline=True)
        embed.add_field(name="Tipo", value=tipo_carta, inline=True)
        embed.add_field(name="Numeración", value=numeracion, inline=True)
        embed.add_field(name="Poder", value=str(poder), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="aat-admin-modificar-carta", description="[ADMIN] Modifica una carta existente en el stock.")
    @app_commands.rename(carta_id="carta-id")
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

    @app_commands.command(name="aat-admin-borrar-carta", description="[ADMIN] BORRA una carta del stock (¡PELIGRO!).")
    @app_commands.rename(carta_id="carta-id")
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

    @app_commands.command(name="aat-admin-vercartas", description="[ADMIN] Muestra todas las cartas creadas en el stock.")
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