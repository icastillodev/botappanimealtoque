# cogs/impostor/roles.py

import os
import discord
from discord.ext import commands
import logging
import asyncio
from typing import Optional

# Importaciones locales
from . import core
from .engine import GameState, ROLE_IMPOSTOR, ROLE_SOCIAL, PHASE_TURNS
from . import chars

log = logging.getLogger(__name__)

def _tematica_publica(lobby: GameState) -> str:
    t = lobby.secret_theme or "personaje"
    return chars.SECRET_THEME_LABELS_ES.get(t, t)

# --- Configuración ---

def get_role_review_seconds() -> int:
    val = os.getenv("IMPOSTOR_ROLE_REVIEW_SECONDS", "20")
    return int(val)

# --- Funciones de Ayuda ---

def _build_role_embed(player: GameState.Player, lobby: GameState) -> discord.Embed:
    """Crea el embed efímero para mostrar el rol."""
    
    if player.role == ROLE_IMPOSTOR:
        embed = discord.Embed(
            title="🕵️ ROL: IMPOSTOR",
            description="Tu objetivo es simple: no dejes que te descubran.\n\n"
                        "Da pistas creíbles sobre el **secreto** que comparten los Sociales "
                        "(no sabés cuál es ni —si es un personaje— de qué anime es; "
                        "solo la **temática** de abajo).\n"
                        "¡Engáñalos a todos!",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Temática del secreto (pública en el canal)",
            value=_tematica_publica(lobby),
            inline=False,
        )
    elif player.role == ROLE_SOCIAL:
        embed = discord.Embed(
            title="🧑‍🤝‍🧑 ROL: SOCIAL",
            description="Tu objetivo es descubrir al impostor.\n\n"
                        "Todos los Sociales tienen el mismo personaje. "
                        "Da pistas que solo otro Social entendería.",
            color=discord.Color.green()
        )
        
        # Añadir información del personaje (el Impostor no recibe esta vista)
        char_name = lobby.character_name or "Personaje Desconocido"
        char_slug = lobby.character_slug or ""
        char_url = chars.get_character_url(char_slug)
        tema = lobby.secret_theme or ""
        lines = [f"**{char_name}**"]
        if tema == "personaje" and lobby.character_anime:
            lines.append(f"**📺 De qué anime / obra es:** {lobby.character_anime}")
        lines.append(f"[Ver ficha / enlace]({char_url})")

        embed.add_field(
            name="Tu secreto (compartido con los Sociales)",
            value="\n".join(lines),
            inline=False,
        )
        embed.add_field(
            name="Temática",
            value=_tematica_publica(lobby),
            inline=False,
        )
    else:
        # Esto no debería ocurrir
        embed = discord.Embed(title="Error", description="No se te asignó un rol.", color=discord.Color.orange())
        
    embed.set_footer(text="Esta información es solo para ti.")
    return embed


# --- View de Asignación de Roles ---

class RoleAssignmentView(discord.ui.View):
    """
    Vista persistente con los botones 'Ver mi rol' y 'Listo'.
    Esta vista maneja su propia lógica de actualización y transición de fase.
    """
    
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None) # Vista persistente
        self.bot = bot

    @discord.ui.button(label="Ver mi rol", style=discord.ButtonStyle.primary, emoji="👁️", custom_id="imp:verrol_global")
    async def ver_rol_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Muestra el rol asignado al jugador de forma efímera."""
        
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.response.send_message("❌ Error: No se encontró este lobby.", ephemeral=True)
            
        player = lobby.get_player(interaction.user.id)
        if not player or player.is_bot:
            return await interaction.response.send_message("❌ No eres un jugador humano en esta partida.", ephemeral=True)
            
        if not player.role:
            return await interaction.response.send_message("❌ Tus roles aún no han sido asignados. Espera...", ephemeral=True)
            
        embed = _build_role_embed(player, lobby)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Listo", style=discord.ButtonStyle.success, emoji="✅", custom_id="imp:ready_after_roles")
    async def listo_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Marca al jugador como listo después de ver su rol."""
        
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.response.send_message("❌ Error: No se encontró este lobby.", ephemeral=True)
            
        player = lobby.get_player(interaction.user.id)
        if not player or player.is_bot:
            return await interaction.response.send_message("❌ No eres un jugador humano en esta partida.", ephemeral=True)
            
        if player.ready_after_roles:
            return await interaction.response.send_message("✅ Ya habías marcado que estabas listo.", ephemeral=True)
            
        # Marcar como listo y acusar recibo
        player.ready_after_roles = True
        await interaction.response.defer() # Acusar recibo, no enviar mensaje
        
        # Actualizar el mensaje principal
        await self.update_ready_message(interaction.message, lobby)

    async def update_ready_message(self, message: discord.Message, lobby: GameState):
        """
        Edita el mensaje principal para mostrar quiénes están listos.
        Si todos están listos, inicia la cuenta regresiva.
        """
        humans = lobby.human_players
        ready_humans = [p for p in humans if p.ready_after_roles]
        
        content = "Roles entregados. Tocá `Ver mi rol` (es secreto) y `Listo` cuando termines."
        content += f"\n\n**Listos {len(ready_humans)}/{len(humans)}:**"
        
        if ready_humans:
            content += "\n" + ", ".join([f"<@{p.user_id}>" for p in ready_humans])
        else:
            content += "\n*(Nadie ha marcado 'Listo' aún...)*"
            
        if lobby.all_humans_ready_after_roles:
            # Todos listos. Detener la vista y empezar cuenta regresiva.
            self.stop()
            await message.edit(content=content, view=self)
            
            # Iniciar tarea de cuenta regresiva
            asyncio.create_task(self._start_game_countdown(lobby, message))
        else:
            # Aún falta gente, solo editar el mensaje
            await message.edit(content=content, view=self)

    async def _start_game_countdown(self, lobby: GameState, message: discord.Message):
        """
        Maneja la cuenta regresiva y la transición a la primera ronda.
        """
        seconds = get_role_review_seconds()
        log.info(f"Todos listos en lobby C:{lobby.channel_id}. Iniciando cuenta regresiva de {seconds}s.")
        
        for i in range(seconds, 0, -1):
            if i % 5 == 0 or i <= 5: # No spamear
                new_content = f"✅ ¡Todos listos! Revisen su rol por última vez.\n**Comenzando la Ronda 1 en {i} segundos...**"
                await message.edit(content=new_content)
            await asyncio.sleep(1)
            
        # --- Transición a la siguiente fase ---
        await message.edit(content="⏱️ **¡Tiempo! Comenzando la Ronda 1...**", view=None)
        
        async with lobby._lock:
            lobby.phase = PHASE_TURNS
            lobby.round_num = 1
        
        # Llamar al Cog 'game_core' para que maneje la primera ronda
        game_cog = self.bot.get_cog("ImpostorGameCore")
        if not game_cog:
            log.error(f"FATAL: No se pudo encontrar 'ImpostorGameCore' para iniciar la ronda 1 en C:{lobby.channel_id}")
            await message.channel.send("❌ ERROR FATAL: El módulo 'game_core' no está cargado. La partida no puede continuar.")
            return

        # Esta función la definiremos en game_core.py
        await game_cog.start_round(lobby)


# --- Cog Principal ---

class ImpostorRolesCog(commands.Cog, name="ImpostorRoles"):
    """
    Gestiona la fase de asignación de roles y la transición a la partida.
    """
    
    _view_registered = False

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Registrar la vista persistente una sola vez
        if not ImpostorRolesCog._view_registered:
            bot.add_view(RoleAssignmentView(bot))
            ImpostorRolesCog._view_registered = True
            log.info("Vista 'RoleAssignmentView' registrada persistentemente.")

    async def send_role_assignment_ui(self, lobby: GameState):
        """
Halfpública llamada por 'game_core' para iniciar esta fase."""
        
        channel = self.bot.get_channel(lobby.channel_id)
        if not channel:
            log.error(f"No se pudo encontrar el canal C:{lobby.channel_id} para enviar UI de roles.")
            return

        view = RoleAssignmentView(self.bot)
        
        # Enviar el mensaje inicial (sin lista de listos)
        tematica = _tematica_publica(lobby)
        content = (
            f"🎲 **Temática de esta partida:** {tematica}\n"
            "(No revela el secreto; solo indica si es personaje, anime u objeto.)\n\n"
            "Roles entregados. Tocá `Ver mi rol` (es secreto) y `Listo` cuando termines."
        )
        content += f"\n\n**Listos 0/{len(lobby.human_players)}:**\n*(Nadie ha marcado 'Listo' aún...)*"

        await channel.send(content, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorRolesCog(bot))