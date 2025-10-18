# cogs/impostor/help.py
import discord
from discord import app_commands
from discord.ext import commands

from .core import manager, MAX_PLAYERS, FEED_CHANNEL_ID

def _embed(title: str, desc: str | None = None) -> discord.Embed:
    emb = discord.Embed(title=title, color=discord.Color.teal(), description=desc or "")
    emb.set_footer(text="IMPOSITOR • AnimeAlToque")
    return emb

class HelpCog(commands.Cog):
    """Ayuda contextual: /ayuda y guía de creación /ayudacrearimp."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="ayudacrearimp",
        description="Cómo crear un lobby (abierto/cerrado), invitar, gestionar y empezar partida"
    )
    async def ayudacrearimp(self, interaction: discord.Interaction):
        emb = _embed("Creación de partidas — IMPOSITOR")
        emb.add_field(
            name="1) Crear un lobby",
            value=(
                "• `/crearimpostor nombre:<tu-lobby> tipo:abierto` → se une cualquiera hasta 5/5\n"
                "• `/crearimpostor nombre:<tu-lobby> tipo:cerrado` → solo por invitación\n"
                "Al crear, se genera un canal **impostor-<nombre>** visible solo para el lobby."
            ),
            inline=False
        )
        emb.add_field(
            name="2) Gestión del lobby (host)",
            value=(
                "• `/invitar @usuario` (cerrado)\n"
                "• `/abrirlobby` / `/cerrarlobby`\n"
                "• `/kick @usuario`\n"
                "• Todos usan `/ready`\n"
                "• **Opcional (admin/host):** `/addbot` y `/forzar_inicio`"
            ),
            inline=False
        )
        emb.add_field(
            name="3) Empezar la partida",
            value=(
                "• Requiere **5/5** y todos *ready* → `/comenzar`\n"
                "• Se reparten roles por DM (SOCIAL/IMPOSTOR) y arranca la Ronda 1"
            ),
            inline=False
        )
        emb.add_field(
            name="Tips",
            value=(
                "• Si pasan 5 min sin empezar → `/finalizar_lobby`\n"
                "• Para ver lobbys abiertos: canal **cartelera** + `/entrar nombre:...`\n"
                "• Ayuda contextual: `/ayuda`"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="ayuda", description="Ayuda contextual según etapa (feed, lobby, pistas, votación)")
    async def ayuda(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("Usá este comando en el servidor.", ephemeral=True)

        # IMPORT LOCAL para evitar ciclos
        from .game_core import get_game  # <-- aquí, no arriba

        ch = interaction.channel
        in_lobby = None
        stage = "general"

        # ¿está en un canal de lobby?
        if isinstance(ch, discord.TextChannel) and ch.name.startswith("impostor-"):
            # buscar lobby por canal
            for lob in manager.all_in_guild(interaction.guild.id):
                if lob.channel_id == ch.id:
                    in_lobby = lob
                    break
            # fallback: revisar todos los lobbies registrados
            if in_lobby is None:
                for (gid, _name), lob2 in manager._lobbies.items():  # type: ignore[attr-defined]
                    if gid == interaction.guild.id and lob2.channel_id == ch.id:
                        in_lobby = lob2
                        break

        # Determinar etapa
        if in_lobby is None:
            if ch and isinstance(ch, discord.TextChannel) and ch.id == FEED_CHANNEL_ID:
                stage = "feed"
            else:
                stage = "general"
        else:
            if not in_lobby.in_game:
                stage = "lobby"
            else:
                gs = get_game(interaction.guild.id, in_lobby.name)
                if gs is None:
                    stage = "lobby"
                else:
                    if not gs.clues_done and not gs.votes_open:
                        stage = "pistas"
                    elif gs.votes_open:
                        stage = "votacion"
                    else:
                        stage = "entre_rondas"

        # Respuesta por etapa
        if stage == "feed":
            emb = _embed("Ayuda — Cartelera de lobbys")
            emb.add_field(
                name="Ver/Entrar",
                value="• Mirá lobbys **abiertos** y unite con `/entrar nombre:<lobby>`.",
                inline=False
            )
            emb.add_field(
                name="Crear",
                value="• `/crearimpostor nombre:<tu-lobby> tipo:(abierto|cerrado)`",
                inline=False
            )
            emb.add_field(
                name="Más guías",
                value="• `/ayudacrearimp` (crear e invitar) • `/ayuda` (contextual)",
                inline=False
            )
            return await interaction.response.send_message(embed=emb)

        if stage == "general":
            emb = _embed("Ayuda — IMPOSITOR (general)")
            emb.add_field(
                name="Básico",
                value=(
                    "• `/crearimpostor` para crear sala\n"
                    "• `/entrar` para unirte a sala abierta\n"
                    "• `/ayudacrearimp` para guía de creación e invitaciones\n"
                    "• Canal **cartelera** para ver lobbys"
                ),
                inline=False
            )
            emb.add_field(
                name="En lobby",
                value="• `/ready`, `/abrirlobby`, `/cerrarlobby`, `/invitar`, `/kick`, `/leave`, `/comenzar`",
                inline=False
            )
            emb.add_field(
                name="En partida",
                value="• Pistas: `/palabra ...` (1–5 palabras)\n• Votación: `/votar @jugador`",
                inline=False
            )
            emb.add_field(
                name="Admin/Host extra",
                value="• `/addbot`, `/forzar_inicio`, `/finalizar_lobby`, `/revancha`, `/feed_refresh`",
                inline=False
            )
            return await interaction.response.send_message(embed=emb)

        if stage == "lobby":
            host_line = ""
            if in_lobby:
                host_line = f"Host: <@{in_lobby.host_id}> — Jugadores: {in_lobby.slots()} — {'abierto' if in_lobby.is_open else 'cerrado'}"
            emb = _embed("Ayuda — Lobby", host_line or None)
            emb.add_field(
                name="Todos",
                value="• `/ready` (marcar listo)  • `/leave` (salir tras 30s)",
                inline=False
            )
            emb.add_field(
                name="Host",
                value="• `/invitar @usuario` • `/abrirlobby` • `/cerrarlobby` • `/kick @usuario` • `/comenzar`",
                inline=False
            )
            emb.add_field(
                name="Admin/Host (opcional)",
                value="• `/addbot` • `/forzar_inicio` • `/finalizar_lobby`",
                inline=False
            )
            return await interaction.response.send_message(embed=emb)

        if stage == "pistas":
            emb = _embed("Ayuda — Fase de PISTAS")
            emb.add_field(
                name="Tu acción",
                value="• **`/palabra <pista>`** (1–5 palabras) durante tu turno de 15s.",
                inline=False
            )
            emb.add_field(
                name="Recordatorio",
                value="• Si no hablás, quedás **AFK** y te auto-votás.",
                inline=False
            )
            emb.add_field(
                name="Próximo paso",
                value="• Luego **votación** con `/votar @jugador`.",
                inline=False
            )
            return await interaction.response.send_message(embed=emb)

        if stage == "votacion":
            emb = _embed("Ayuda — Fase de VOTACIÓN")
            emb.add_field(
                name="Tu acción",
                value="• **`/votar @jugador`** antes de que termine el tiempo.",
                inline=False
            )
            emb.add_field(
                name="Desempates",
                value="• Si empatan, **no hay eliminación** y se abre otra ronda de pistas.",
                inline=False
            )
            return await interaction.response.send_message(embed=emb)

        if stage == "entre_rondas":
            emb = _embed("Ayuda — Entre rondas")
            emb.add_field(
                name="Siguiente",
                value="• En breve inicia la nueva **fase de PISTAS**.",
                inline=False
            )
            return await interaction.response.send_message(embed=emb)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
