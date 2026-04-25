# cogs/economia/ayuda_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List

from .guia_contenido import guia_fixed_channel_blurb
from .toque_labels import guia_toque_explicacion, toque_emote

class EconomiaHelpView(discord.ui.View):
    def __init__(self, author_id: int, bot: commands.Bot):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.bot = bot
        self.current_page = 0
        self.embeds: List[discord.Embed] = [
            self._create_page_1(),
            self._create_page_2(),
            self._create_page_3(),
            self._create_page_4(),
            self._create_page_5(),
            self._create_page_6(),
        ]
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("No puedes usar esta guía, pide la tuya con `/aat-ayuda`.", ephemeral=True)
            return False
        return True

    def _create_page_1(self) -> discord.Embed:
        tq = toque_emote()
        embed = discord.Embed(title=f"Ayuda de Economía {tq} (Página 1/6)", color=discord.Color.blue())
        guia_ch = guia_fixed_channel_blurb(self.bot)
        embed.description = (
            f"{guia_ch}"
            f"Con las tareas sumás **{tq} Toque points** (moneda del canal) y **sobres**; "
            "gastás **Toque points** en la **tienda** y minijuegos.\n"
            "**Flujo:** tareas → `/aat-reclamar` → saldo → `/aat-tienda-ver` (u otras tiendas) → disfrutás.\n\n"
            f"{guia_toque_explicacion()}"
        )
        embed.add_field(
            name="¿Qué es esto?",
            value=f"{tq} **Toque points**, blisters, cartas trampa, tienda y ranking del servidor.",
            inline=False,
        )
        embed.add_field(name="Tareas (Comandos)", value=(
            "`/aat-progreso-iniciacion` - Discord + perfil (wishlist/top/odiados) para la bienvenida.\n"
            "`/aat-progreso-diaria` - Diaria en **dos partes**: (1) 10 mensajes + 3 reacciones + 1× oráculo · (2) Trampa aparte.\n"
            "`/aat-progreso-semanal` - **Media**, **foro/#videos-nuevos**, **Impostor** y **minijuegos** en bloques separados.\n"
            "`/aat-reclamar [tipo]` - `inicial`, `diaria`, `semanal`, `semanal_especial`, `semanal_minijuegos`.\n"
            "**Top anime (hasta 33 casillas):** `/aat-anime-top-set` · `/aat-anime-top-ver` · `?animetop` — bonos únicos al completar 10 y 30."
        ), inline=False)
        embed.set_footer(text="Usa los botones para navegar.")
        return embed

    def _create_page_2(self) -> discord.Embed:
        embed = discord.Embed(title="Ayuda de Cartas y Blisters 🃏 (Página 2/6)", color=discord.Color.purple())
        embed.add_field(
            name="`/aat-puntos`",
            value="Atajo para ver solo tu saldo de **Toque points** (en público también: `?puntos`).",
            inline=False,
        )
        embed.add_field(
            name="`/aat-inventario`",
            value="Tu comando principal: **Toque points**, créditos pin y blisters.",
            inline=False,
        )
        embed.add_field(name="`/aat-abrirblister`", value="¡Abre los blisters que ganaste! Cada uno da 3 cartas aleatorias.", inline=False)
        embed.add_field(name="`/aat-miscartas`", value="Muestra tu colección de cartas (verás el ID de cada carta).", inline=False)
        # --- MODIFICADO: Nombre actualizado ---
        embed.add_field(name="`/vercarta`", value="Inspecciona una carta de tu inventario (usa el ID o el nombre).", inline=False)
        embed.add_field(name="`/aat-catalogo`", value="Muestra todas las cartas que existen en el juego.", inline=False)
        return embed
        
    def _create_page_3(self) -> discord.Embed:
        embed = discord.Embed(title="Ayuda de Cartas Trampa ⚔️ (Página 3/6)", color=discord.Color.red())
        # --- MODIFICADO: Nombre actualizado ---
        embed.add_field(
            name="`/usar`",
            value=(
                "Consume una carta (solo **slash**). **Diaria (Trampa):** **un** uso **con** mención **o** **sin** objetivo (sola). "
                "Cartas **Rara/Legendaria** pueden tener efectos extra (mute breve, broma, etc.) según el campo `efecto` en la DB. "
                "Efecto **`ROLE_TRAMPA_24H`**: asigna al objetivo el rol configurado en `TRAMPA_CARTA_ROL_24H_ROLE_ID` por "
                "`TRAMPA_CARTA_ROL_24H_HOURS` horas (máx. 168); el bot lo quita solo al vencer."
            ),
            inline=False,
        )
        embed.add_field(name="Límites", value="Las cartas son **consumibles** y tienes un límite de **5 cartas cada 10 minutos**.", inline=False)
        return embed

    def _create_page_4(self) -> discord.Embed:
        embed = discord.Embed(title="Tienda paso a paso 🏪 (Página 4/6)", color=discord.Color.gold())
        embed.description = "Todo con **slash**; los precios dependen del servidor."
        embed.add_field(
            name="1 · Ver catálogo",
            value="`/aat-tienda-ver` — saldo, precios e ítems activos.",
            inline=False,
        )
        embed.add_field(
            name="2 · Canje clásico",
            value=(
                "`/aat-tienda-canjear` → **akatsuki** / **jonin** / **pin** / **blister_trampa**\n"
                "· **pin** suma 1 crédito; después `/aat-tienda-fijar` con la **ID** del mensaje **en ese canal**.\n"
                "· **blister_trampa** suma 1 sobre trampa para abrir con `/aat-abrirblister`."
            ),
            inline=False,
        )
        embed.add_field(
            name="3 · Pin solo en #general",
            value="`/aat-tienda-pin-general` — pagás de una vez (sin crédito) si está `SHOP_PRICE_PIN_GENERAL`.",
            inline=False,
        )
        embed.add_field(
            name="4 · Encuesta de pago",
            value="`/aat-tienda-encuesta` — publica en el canal de votaciones (`VOTACION_CHANNEL_ID` o `VOTING_CHANNEL_ID` + precio `SHOP_PRICE_POLL_TIENDA`).",
            inline=False,
        )
        embed.add_field(
            name="5 · Rol decorativo temporal",
            value="`/aat-tienda-rol-temporal` — creás un rol con nombre, se lo das a alguien (o a vos) **30 días** (configurable).",
            inline=False,
        )
        embed.add_field(name="Ranking", value="`/aat-ranking-top` — top 10 del servidor.", inline=False)
        return embed

    def _create_page_5(self) -> discord.Embed:
        embed = discord.Embed(title="Minijuegos y semanal extra 🎲 (Página 5/6)", color=discord.Color.teal())
        embed.description = (
            "Cumplí las 4 marcas en `/aat-progreso-semanal` y reclamá con `/aat-reclamar` → **`semanal_minijuegos`**."
        )
        embed.add_field(
            name="Comandos",
            value=(
                "`/aat-roll` — dado casual (rango acotado).\n"
                "`/aat-roll-retar` (apuesta **0** = sin puntos; 1–5000 = con apuesta) + `/aat-roll-aceptar` — roll 1–100 vs otro; gana el mayor.\n"
                "En #general también: `?rollp @rival` · `?rollc @rival <pts>` · `?rollpaceptar`.\n"
                "`/aat-duelo-retar` + `/aat-duelo-aceptar` — apuestan **Toque points** y **cartas**; total = **poder** + dado; el retador elige si gana **mayor** o **menor**.\n"
                "`/aat-voto-semanal` — voto A/B (opciones por variables de entorno del bot)."
            ),
            inline=False,
        )
        embed.add_field(
            name="Notas",
            value="No podés retar a alguien que ya tenga un reto pendiente. Tenés **5 minutos** para aceptar; si no, se cancela y el bot avisa en el canal (la apuesta del retador se devuelve).",
            inline=False,
        )
        return embed

    def _create_page_6(self) -> discord.Embed:
        embed = discord.Embed(
            title="Resumen: Toque points y reclamos 📋 (Página 6/6)",
            color=discord.Color.dark_green(),
        )
        embed.description = "Checklist para no perderte."
        embed.add_field(
            name="Ganar",
            value=(
                "`/aat-progreso_*` para ver qué falta.\n"
                "`/aat-reclamar` sin tipo intenta **todo** lo listo.\n"
                "Tipos: `inicial`, `diaria`, `semanal`, `semanal_especial`, `semanal_minijuegos`."
            ),
            inline=False,
        )
        embed.add_field(
            name="Gastar",
            value="Tienda (pág. 4), minijuegos con apuesta (pág. 5), tienda de roles fijos.",
            inline=False,
        )
        embed.add_field(
            name="Otras ideas que suman",
            value=(
                "Canje por **título en /nick** temporal; sorteo de **Toque points** entre reacciones; "
                "**doble Toque points** un día a la semana; ítem **color de rol** (sin permisos extra); "
                "donación de **Toque points** a otro usuario con comisión."
            ),
            inline=False,
        )
        return embed

    def _update_buttons(self):
        previous_button = self.children[0]
        next_button = self.children[1]
        if isinstance(previous_button, discord.ui.Button):
            previous_button.disabled = (self.current_page == 0)
        if isinstance(next_button, discord.ui.Button):
            next_button.disabled = (self.current_page == len(self.embeds) - 1)

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

class AyudaCog(commands.Cog, name="Economia Ayuda"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(self.__class__.__name__)
        super().__init__()

    @app_commands.command(name="aat-ayuda", description="Muestra una guía interactiva de los comandos de economía.")
    async def ayuda(self, interaction: discord.Interaction):
        # Por ahora, restringimos la guía larga a staff (admin o rol Hokage) para evitar spam.
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Este comando solo se puede usar en servidor.", ephemeral=True)
        if not interaction.user.guild_permissions.administrator:
            hokage_id = getattr(interaction.client, "hokage_role_id", None)
            role = interaction.guild.get_role(int(hokage_id)) if hokage_id else None
            if role is None or role not in interaction.user.roles:
                return await interaction.response.send_message(
                    "🚫 Este comando está restringido al staff por ahora.",
                    ephemeral=True,
                )
        view = EconomiaHelpView(interaction.user.id, self.bot)
        embed = view.embeds[0]
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AyudaCog(bot))