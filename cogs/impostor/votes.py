# cogs/impostor/votes.py

import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Dict, Optional, List
from collections import Counter

# Importaciones locales
from . import core
from . import chat_guard
from . import rules
from .engine import GameState, PHASE_VOTE, PHASE_END, ROLE_SOCIAL

log = logging.getLogger(__name__)

# --- Configuración ---

def get_vote_seconds() -> int:
    val = os.getenv("IMPOSTOR_VOTE_SECONDS", "180")
    return int(val)

# --- View de Votación (Dinámica) ---

class VoteView(discord.ui.View):
    """
    Vista generada dinámicamente con botones para votar a cada jugador vivo.
    """
    def __init__(self, bot: commands.Bot, lobby: GameState):
        super().__init__(timeout=None) # El timeout lo maneja el _vote_loop
        self.bot = bot
        self.lobby = lobby
        
        # Crear un botón por cada jugador vivo
        for player in lobby.alive_players:
            if player.is_bot:
                label = f"AAT-Bot #{abs(player.user_id)}"
                emoji = "🤖"
            else:
                # Intentar obtener el nombre (puede no estar en caché)
                user = bot.get_user(player.user_id)
                label = user.display_name if user else f"Jugador {player.user_id}"
                emoji = "🧑"
            
            # El custom_id identifica al votado
            self.add_item(VoteButton(
                label=label, 
                emoji=emoji, 
                custom_id=f"impvote:{player.user_id}"
            ))
            
        # Botón para quitar voto
        self.add_item(VoteButton(
            label="Quitar mi voto", 
            style=discord.ButtonStyle.secondary, 
            emoji="🔄", 
            custom_id="impvote:clear",
            row=4 # Ponerlo al final
        ))


class VoteButton(discord.ui.Button):
    """Botón genérico que maneja el callback de votación."""
    
    async def callback(self, interaction: discord.Interaction):
        # 1. Obtener el Bot y el Cog de Votación
        bot: commands.Bot = interaction.client
        cog: "ImpostorVotesCog" = bot.get_cog("ImpostorVotes")
        if not cog:
            return await interaction.response.send_message("❌ Error: Módulo de Votación no cargado.", ephemeral=True)
            
        # 2. Extraer el ID del votado desde el custom_id
        target_id_str = self.custom_id.split(":")[-1]
        target_id = None
        if target_id_str != "clear":
            try:
                target_id = int(target_id_str)
            except ValueError:
                return await interaction.response.send_message("❌ Error: Botón inválido.", ephemeral=True)
        
        # 3. Llamar a la lógica centralizada
        await cog.handle_vote_logic(interaction, target_id)


# --- Cog: Fase de Votación ---

class ImpostorVotesCog(commands.Cog, name="ImpostorVotes"):
    """
    Gestiona la fase de votación, el conteo y la expulsión.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Diccionario para eventos de "todos han votado"
        self._vote_events: Dict[int, asyncio.Event] = {} # {channel_id: Event}
        # bot.add_view(VoteView(bot, None)) # Registrar la estructura de la vista

    def _get_clues_embed(self, lobby: GameState) -> discord.Embed:
        """Crea el embed que muestra las pistas de la ronda."""
        embed = discord.Embed(
            title=f"🗳️ Votación - Ronda {lobby.round_num}",
            description=(
                "Revisen las pistas y voten por quién creen que es el/los Impostor(es).\n"
                "**Botones** abajo, o `/votar @usuario` / `/vote @usuario`.\n"
                "*(Los bots se votan a sí mismos.)*"
            ),
            color=discord.Color.dark_orange(),
        )
        
        lines = []
        for player in lobby.alive_players:
            name = ""
            if player.is_bot:
                name = f"🤖 `AAT-Bot #{abs(player.user_id)}`"
            else:
                name = f"🧑 <@{player.user_id}>"
                
            pista = player.word if player.word is not None else "*(No dijo nada)*"
            lines.append(f"{name}: **{pista}**")
            
        embed.add_field(name="Pistas de esta Ronda", value="\n".join(lines), inline=False)
        return embed

    def _all_humans_voted(self, lobby: GameState) -> bool:
        """Verifica si todos los humanos vivos han emitido un voto."""
        return all(p.voted_for is not None for p in lobby.human_alive_players)

    async def _process_votes(self, lobby: GameState, message: discord.Message):
        """
        Lógica de conteo, expulsión y transición de fase.
        """
        log.info(f"Procesando votos para C:{lobby.channel_id}")
        channel = message.channel
        
        # 1. Deshabilitar la vista de votación
        await message.edit(view=None)
        
        # 2. Obtener y mostrar resultados
        # get_votes() incluye los auto-votos de los bots
        votes: Dict[int, int] = lobby.get_votes()
        
        embed = discord.Embed(
            title="Resultados de la Votación",
            color=discord.Color.purple()
        )
        
        if not votes:
            embed.description = "Nadie votó."
            await channel.send(embed=embed)
        else:
            # Ordenar por más votado
            sorted_votes = sorted(votes.items(), key=lambda item: item[1], reverse=True)
            lines = []
            for user_id, count in sorted_votes:
                lines.append(f"• <@{user_id}>: **{count}** voto(s)")
            embed.description = "\n".join(lines)
            await channel.send(embed=embed)
            
        # 3. Determinar expulsión
        ejected_player_id: Optional[int] = None
        if not votes:
            await channel.send("Nadie fue expulsado. (Empate a 0 votos)")
        else:
            max_votes = sorted_votes[0][1]
            if max_votes == 0:
                 await channel.send("Nadie fue expulsado. (Empate a 0 votos)")
            else:
                most_voted = [uid for uid, count in sorted_votes if count == max_votes]
                if len(most_voted) > 1:
                    await channel.send("¡Hubo un empate! Nadie es expulsado.")
                else:
                    # Expulsión
                    ejected_player_id = most_voted[0]
                    player = lobby.get_player(ejected_player_id)
                    player.alive = False
                    await channel.send(f"💥 **¡<@{ejected_player_id}> ha sido expulsado!**")
                    await chat_guard.on_player_eliminated(self.bot, lobby, ejected_player_id)

        await asyncio.sleep(4) # Pausa dramática

        # 4. Chequear condición de fin de juego (si alguien fue expulsado)
        if ejected_player_id:
            victory = rules.check_round_start_victory(lobby)
            if victory:
                win_role, reason = victory
                log.info(f"Fin de partida en C:{lobby.channel_id}: {reason}")
                endgame_cog = self.bot.get_cog("ImpostorEndgame")
                if endgame_cog:
                    await endgame_cog.trigger_end_game(lobby, win_role, reason)
                return
        
        # 5. Si el juego no terminó, pasar a la siguiente ronda
        async with lobby._lock:
            # Salir si la partida se canceló mientras tanto
            if lobby.phase == PHASE_END:
                return
            
            lobby.round_num += 1
            log.info(f"Transición a Ronda {lobby.round_num} en C:{lobby.channel_id}")
        
        # Llamar a GameCore para chequear condiciones de victoria y empezar ronda
        game_core_cog = self.bot.get_cog("ImpostorGameCore")
        if game_core_cog:
            await game_core_cog.start_round(lobby)
        else:
            log.error(f"FATAL: No se pudo encontrar 'ImpostorGameCore' en C:{lobby.channel_id}")
            await channel.send("❌ ERROR FATAL: Módulo 'game_core' no cargado.")

    async def _vote_loop(self, lobby: GameState, message: discord.Message, event: asyncio.Event):
        """Temporizador de votación."""
        vote_seconds = get_vote_seconds()
        log.debug(f"Iniciando vote_loop de {vote_seconds}s para C:{lobby.channel_id}")
        
        try:
            # Esperar al evento (todos votaron) o al timeout
            await asyncio.wait_for(event.wait(), timeout=vote_seconds)
            log.info(f"C:{lobby.channel_id}: Votación finalizada (Todos votaron).")
            await message.channel.send("✅ Todos los jugadores han votado. Cerrando votación...")
        
        except asyncio.TimeoutError:
            log.info(f"C:{lobby.channel_id}: Votación finalizada (Timeout).")
            await message.channel.send("⌛ ¡Tiempo! Cerrando la votación...")
        
        except asyncio.CancelledError:
            log.info(f"Vote loop C:{lobby.channel_id} cancelado.")
            return # No procesar votos si fue cancelado
            
        except Exception as e:
            log.exception(f"Error en _vote_loop C:{lobby.channel_id}: {e}")
            
        finally:
            # Limpiar referencia a la tarea y evento
            async with lobby._lock:
                if lobby._vote_task:
                    lobby._vote_task = None
            self._vote_events.pop(lobby.channel_id, None)

        # Solo procesar votos si la partida sigue en fase de votación
        if lobby.phase == PHASE_VOTE:
            await self._process_votes(lobby, message)

    async def start_vote_phase(self, lobby: GameState):
        """Punto de entrada para iniciar la fase de votación."""
        channel = self.bot.get_channel(lobby.channel_id)
        if not channel:
            log.error(f"Vote C:{lobby.channel_id}: Canal no encontrado.")
            return
            
        async with lobby._lock:
            if lobby.phase != PHASE_VOTE:
                log.warning(f"Se intentó iniciar votación en C:{lobby.channel_id} fuera de fase.")
                return

            # 1. Crear embed y view
            embed = self._get_clues_embed(lobby)
            view = VoteView(self.bot, lobby)
            
            # 2. Enviar mensaje
            msg = await channel.send(embed=embed, view=view)
            
            # 3. Iniciar tarea de timeout
            event = asyncio.Event()
            self._vote_events[lobby.channel_id] = event
            
            lobby._vote_task = asyncio.create_task(
                self._vote_loop(lobby, msg, event)
            )

    async def handle_vote_logic(self, interaction: discord.Interaction, target_id: Optional[int]):
        """Lógica centralizada para /votar y botones."""
        
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        
        # --- Validaciones ---
        if not lobby:
            return await interaction.response.send_message("❌ Error: No se encontró este lobby.", ephemeral=True)
        if lobby.phase != PHASE_VOTE:
            return await interaction.response.send_message("❌ La votación no está abierta.", ephemeral=True)
            
        player = lobby.get_player(interaction.user.id)
        if not player or player.is_bot or not player.alive:
            return await interaction.response.send_message("❌ No eres un jugador humano vivo en esta partida.", ephemeral=True)

        # --- Lógica de Votación ---
        if target_id is None: # "Quitar mi voto"
            player.voted_for = None
            await interaction.response.send_message("🔄 Has quitado tu voto.", ephemeral=True)
        else:
            target_player = lobby.get_player(target_id)
            if not target_player or not target_player.alive:
                return await interaction.response.send_message("❌ No puedes votar por ese jugador (no existe o ya fue expulsado).", ephemeral=True)
            
            player.voted_for = target_id
            await interaction.response.send_message(f"✅ Has votado por <@{target_id}>.", ephemeral=True)

        # --- Chequear si todos votaron ---
        if self._all_humans_voted(lobby):
            event = self._vote_events.get(lobby.channel_id)
            if event:
                event.set() # Disparar el fin de votación

    @app_commands.command(name="votar", description="Vota por un jugador durante la fase de votación.")
    @app_commands.describe(usuario="El jugador que crees que es el impostor.")
    async def votar_cmd(self, interaction: discord.Interaction, usuario: discord.Member):
        await self.handle_vote_logic(interaction, usuario.id)

    @app_commands.command(name="vote", description="Vote for a player (alias de /votar).")
    @app_commands.describe(usuario="The player you think is the impostor.")
    async def vote_cmd(self, interaction: discord.Interaction, usuario: discord.Member):
        await self.handle_vote_logic(interaction, usuario.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorVotesCog(bot))