# cogs/impostor/help.py

import discord
from discord.ext import commands
from discord import app_commands
import logging

log = logging.getLogger(__name__)

# --- Contenido de los Embeds de Ayuda ---

EMBED_MAIN = discord.Embed(
    title="Bienvenido a Impostor",
    description="Impostor es un juego de deducción social (mínimo **2** jugadores; el **cupo** es solo un tope).\n\n"
                "Un **Impostor** intenta sobrevivir sin conocer el **secreto** que comparten los **Sociales** "
                "(personaje, anime u objeto, según la **temática** de la partida).\n\n"
                "Al crear partida podés fijar el cupo máximo u omitirlo y usar el valor por defecto del servidor.\n\n"
                "Usa los botones de abajo para aprender más.",
    color=discord.Color.blurple()
)

EMBED_COMO_JUGAR = discord.Embed(
    title="¿Cómo Jugar?",
    description="El flujo del juego es simple y se divide en rondas.",
    color=discord.Color.green()
)
EMBED_COMO_JUGAR.add_field(
    name="1. Fase de Roles",
    value="Al empezar se anuncia la **temática** del secreto (personaje, anime u objeto). "
          "Los Sociales ven el **mismo** secreto; si es **personaje**, también **de qué anime es** "
          "(el Impostor no lo sabe). El Impostor solo ve la temática. Todos pulsan 'Listo'.",
    inline=False
)
EMBED_COMO_JUGAR.add_field(
    name="2. Fase de Pistas (Rondas)",
    value="Por turnos, cada jugador da **una pista** sobre el secreto (acorde a la temática). "
          "El Impostor finge sin conocer el secreto exacto.",
    inline=False
)
EMBED_COMO_JUGAR.add_field(
    name="3. Fase de Votación",
    value="Después de las pistas, todos votan para expulsar a quien creen que es el impostor. Los bots se votan a sí mismos.",
    inline=False
)
EMBED_COMO_JUGAR.add_field(
    name="4. Fin de la Partida",
    value="**Ganan los Sociales** si expulsan al Impostor.\n"
          "**Gana el Impostor** si sobrevive 4 rondas o si quedan solo 2 jugadores vivos.",
    inline=False
)

EMBED_COMANDOS = discord.Embed(
    title="Comandos del Lobby",
    description="Estos son los comandos que usarás para jugar.",
    color=discord.Color.orange()
)
EMBED_COMANDOS.add_field(
    name="Generales",
    value="`/helpimpostor` o `/ayudaimpostor` - Muestra esta ayuda.\n"
          "`/crearsimpostor nombre: …` — `jugadores` es **opcional** (cupo máx. del lobby).\n"
          "`/entrar nombre: [nombre]` - Te une a un lobby abierto.\n"
          "En la **cartelera** hay un botón para darte o quitarte el rol de avisos de partidas.",
    inline=False
)
EMBED_COMANDOS.add_field(
    name="Dentro del Lobby",
    value="`/leave` o `/salir` - Abandona el lobby (solo antes de empezar).\n"
          "`/ready` o `/listo` - Te marca como listo para empezar.\n"
          "`/addbot` - (Host) Añade un bot.\n"
          "`/removebot` - (Host) Quita un bot.",
    inline=False
)
EMBED_COMANDOS.add_field(
    name="En Partida",
    value="`/palabra pista: [tu pista]` - Envía tu pista secreta en tu turno.\n"
          "`/votar @usuario` - Vota por un jugador.",
    inline=False
)

# --- Vistas (Botones) ---

class HelpView(discord.ui.View):
    """Vista principal con los botones de navegación."""
    def __init__(self, author: discord.Member):
        super().__init__(timeout=180) # 3 minutos de timeout
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Asegura que solo el autor del comando pueda usar los botones."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Solo la persona que escribió el comando puede usar estos botones.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="¿Cómo Jugar?", style=discord.ButtonStyle.success, emoji="📖")
    async def como_jugar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=EMBED_COMO_JUGAR, view=HelpBackView(self.author))

    @discord.ui.button(label="Comandos", style=discord.ButtonStyle.primary, emoji="⌨️")
    async def comandos(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=EMBED_COMANDOS, view=HelpBackView(self.author))


class HelpBackView(discord.ui.View):
    """Vista con solo el botón de 'Volver'."""
    def __init__(self, author: discord.Member):
        super().__init__(timeout=180)
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Asegura que solo el autor del comando pueda usar los botones."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Solo la persona que escribió el comando puede usar estos botones.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Volver", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def volver(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=EMBED_MAIN, view=HelpView(self.author))


# --- Cog y Comando ---

class ImpostorHelpCog(commands.Cog, name="ImpostorHelp"):
    """
    Comando de ayuda para el modo Impostor.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="helpimpostor", description="Muestra la ayuda del modo de juego Impostor.")
    async def helpimpostor(self, interaction: discord.Interaction):
        
        # FIX: Añadir 'defer' para evitar el error "La aplicación no ha respondido"
        await interaction.response.defer(ephemeral=True)
        
        await interaction.followup.send(
            embed=EMBED_MAIN,
            view=HelpView(interaction.user),
            ephemeral=True # Se envía oculto
        )

    @app_commands.command(name="ayudaimpostor", description="(Alias) Muestra la ayuda del modo Impostor.")
    async def ayudaimpostor(self, interaction: discord.Interaction):
        await self.helpimpostor.callback(self, interaction)

async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorHelpCog(bot))