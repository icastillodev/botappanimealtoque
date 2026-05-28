# cogs/impostor/help.py

import discord
from discord.ext import commands
from discord import app_commands
import logging

from .config import get_min_impo_players

log = logging.getLogger(__name__)


def build_main_embed() -> discord.Embed:
    min_p = get_min_impo_players()
    return discord.Embed(
        title="Bienvenido a Impostor",
        description=(
            f"Juego de deducción social (**mínimo {min_p} jugadores**).\n\n"
            "Hay uno o más **Impostores** que no conocen el **secreto** (personaje, anime u objeto). "
            "Los **Sociales** sí lo conocen y deben descubrir quién miente.\n\n"
            "El host puede elegir **cuántos impostores** hay (+1 cada ~3 jugadores). "
            "Usá los botones para ver reglas y comandos."
        ),
        color=discord.Color.blurple(),
    )


# --- Contenido de los Embeds de Ayuda ---

EMBED_COMO_JUGAR = discord.Embed(
    title="¿Cómo jugar?",
    description="Flujo de una partida:",
    color=discord.Color.green(),
)
EMBED_COMO_JUGAR.add_field(
    name="1. Lobby",
    value="**Ready** → el host pulsa **Comenzar** (o **Forzar inicio**). "
          "Cuenta regresiva corta y reparto de roles.",
    inline=False,
)
EMBED_COMO_JUGAR.add_field(
    name="2. Roles",
    value="**Ver mi rol** (secreto) → **Listo**. Los Sociales ven el secreto; "
          "los Impostores solo la **temática** y un **detalle** de cómo dar pistas.",
    inline=False,
)
EMBED_COMO_JUGAR.add_field(
    name="3. Pistas",
    value="Por turnos: **1–5 palabras** en el chat o `/palabra`. "
          "Solo quien tiene el turno puede escribir en el canal.",
    inline=False,
)
EMBED_COMO_JUGAR.add_field(
    name="4. Votación",
    value="Botones en el mensaje del bot o `/votar` / `/vote @jugador`.",
    inline=False,
)
EMBED_COMO_JUGAR.add_field(
    name="5. Victoria",
    value="**Sociales:** eliminan a **todos** los impostores.\n"
          "**Impostores:** quedan con **2 sociales o menos** vivos, o sobreviven hasta el límite de rondas.",
    inline=False,
)
EMBED_COMO_JUGAR.add_field(
    name="6. Revancha",
    value="Al terminar: **host** → **Revancha** / `/revancha` / `?revancha` · **jugadores** → "
          "**Quiero revancha**, `/quiero-revancha` o `?quierorevancha` (mayoría reinicia).",
    inline=False,
)

EMBED_COMANDOS = discord.Embed(
    title="Comandos",
    description="Slash principales (también hay botones en el lobby):",
    color=discord.Color.orange(),
)
EMBED_COMANDOS.add_field(
    name="Crear / unirse (fuera del lobby)",
    value="`/crearsimpostor` o **`?crearsimpostor <nombre>`** [abierto|cerrado] [cupo].\n"
          "`/entrar` o **`?entrar <nombre>`** — lobby abierto.\n"
          "**`?impostor`** / cartelera — ver salas.",
    inline=False,
)
EMBED_COMANDOS.add_field(
    name="Lobby (en el canal de la sala)",
    value="`/leave` · `/salir` o **`?salir`** · `/ready` · `/listo`\n"
          "Panel: **+ Imp** / **− Imp** · **Cerrar sala** (host) · **Forzar inicio**",
    inline=False,
)
EMBED_COMANDOS.add_field(
    name="En partida",
    value="`/palabra` — pista en tu turno (o escribí 1–5 palabras).\n"
          "`/votar` · `/vote` — votar.",
    inline=False,
)
EMBED_COMANDOS.add_field(
    name="Estadísticas (cualquier canal)",
    value="`/impostor-stats` · **`?impostorstats`**\n"
          "`/impostor-ranking` · **`?impostorrang`**\n"
          "`?impostoractivos` · `?impostorhistorial` · `?helpimpostor`",
    inline=False,
)


class HelpView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=180)
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Solo quien abrió la ayuda puede usar estos botones.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="¿Cómo jugar?", style=discord.ButtonStyle.success, emoji="📖")
    async def como_jugar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=EMBED_COMO_JUGAR, view=HelpBackView(self.author))

    @discord.ui.button(label="Comandos", style=discord.ButtonStyle.primary, emoji="⌨️")
    async def comandos(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=EMBED_COMANDOS, view=HelpBackView(self.author))


class HelpBackView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=180)
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Solo quien abrió la ayuda puede usar estos botones.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Volver", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def volver(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_main_embed(), view=HelpView(self.author))


class ImpostorHelpCog(commands.Cog, name="ImpostorHelp"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="helpimpostor", description="Ayuda del modo Impostor.")
    async def helpimpostor(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            embed=build_main_embed(),
            view=HelpView(interaction.user),
            ephemeral=True,
        )

    @app_commands.command(name="ayudaimpostor", description="(Alias) Ayuda Impostor.")
    async def ayudaimpostor(self, interaction: discord.Interaction):
        await self.helpimpostor.callback(self, interaction)

    @commands.command(name="helpimpostor", aliases=["ayudaimpostor", "impostorhelp"])
    async def helpimpostor_prefix(self, ctx: commands.Context):
        await ctx.send(embed=build_main_embed(), view=HelpView(ctx.author))


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorHelpCog(bot))
