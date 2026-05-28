# cogs/impostor/turns.py

import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import random
import re
from typing import Dict, Optional

# Importaciones locales
from . import core
from . import chat_guard
from .engine import GameState, PHASE_END, PHASE_TURNS, PHASE_VOTE
from .bot_hints import pick_bot_hint

log = logging.getLogger(__name__)

# --- Configuración ---

def get_turn_seconds() -> int:
    val = os.getenv("IMPOSTOR_TURN_SECONDS", "50")
    return int(val)

# --- Regex de Validación ---
WORD_REGEX = re.compile(
    r"([a-zA-Z0-9áéíóúÁÉÍÓÚñÑ-]{1,20})(\s+[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ-]{1,20}){0,4}"
)


# --- Cog: Fase de Turnos ---

class ImpostorTurnsCog(commands.Cog, name="ImpostorTurns"):
    """
    Gestiona la fase de turnos (pistas) y el comando /palabra.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Diccionario para sincronizar el /palabra con el _turn_loop
        self._turn_events: Dict[int, asyncio.Event] = {} # {channel_id: Event}

    async def start_turn_phase(self, lobby: GameState):
        """Inicia el bucle de turnos como una tarea de fondo."""
        
        if lobby._turn_task:
            log.warning(f"C:{lobby.channel_id}: Se intentó iniciar un turn_task cuando ya existía uno.")
            try:
                lobby._turn_task.cancel()
            except Exception:
                pass 
                
        lobby._turn_task = asyncio.create_task(self._turn_loop(lobby))

    async def _turn_loop(self, lobby: GameState):
        """
        Bucle principal que gestiona el flujo de turnos (palabras).
        """
        channel = self.bot.get_channel(lobby.channel_id)
        if not channel:
            log.error(f"Turn loop C:{lobby.channel_id}: Canal no encontrado.")
            return

        try:
            # 1. Setup
            async with lobby._lock:
                alive_ids = [p.user_id for p in lobby.alive_players]
                random.shuffle(alive_ids)
                lobby.alive_order = alive_ids
                lobby.current_turn_idx = -1
            
            turn_seconds = get_turn_seconds()
            
            # 2. Anunciar fase
            order_mentions = [f"<@{uid}>" for uid in lobby.alive_order]
            await channel.send(
                f"🟢 **¡Comienza la Fase de PISTAS!** (Ronda {lobby.round_num})\n"
                f"Cada jugador tiene **{turn_seconds} segundos** para dar su pista.\n\n"
                f"**Vivos:** {len(lobby.alive_order)}\n"
                f"**Orden de turnos:** {' ➡️ '.join(order_mentions)}"
            )
            
            # 3. Iterar turnos
            for idx, user_id in enumerate(lobby.alive_order):
                async with lobby._lock:
                    if lobby.phase != PHASE_TURNS:
                        log.warning(f"C:{lobby.channel_id}: Fase cambió, cancelando turn_loop.")
                        return
                    lobby.current_turn_idx = idx
                
                player = lobby.get_player(user_id)
                if not player or not player.alive:
                    log.warning(f"C:{lobby.channel_id}: Jugador {user_id} no encontrado o muerto, saltando turno.")
                    continue

                await asyncio.sleep(1.5)

                if player.is_bot:
                    await asyncio.sleep(0.8)
                    hint = pick_bot_hint(lobby, player)
                    player.word = hint
                    await channel.send(
                        f"🤖 `AAT-Bot #{abs(user_id)}` dice: **{hint}**"
                    )
                    continue

                # --- Turno Humano ---
                event = asyncio.Event()
                self._turn_events[lobby.channel_id] = event
                
                await channel.send(
                    f"▶️ Turno de <@{user_id}>. Tienes **{turn_seconds} segundos**.\n"
                    f"Escribí **1 a 5 palabras** acá (sin comando) **o** usá `/palabra <tu pista>`.\n"
                    f"*(El resto del canal queda en silencio hasta tu pista.)*"
                )
                
                try:
                    # Esperar al evento (de /palabra) o al timeout
                    await asyncio.wait_for(event.wait(), timeout=turn_seconds)
                    
                    # --- INICIO DE CAMBIO ---
                    # El evento fue seteado por /palabra.
                    # Anunciamos públicamente la palabra que el jugador guardó.
                    if player.word:
                        await channel.send(f"🗣️ <@{user_id}> dice: **{player.word}**")
                    else:
                        # Esto no debería pasar si el evento se seteó, pero por si acaso.
                        log.warning(f"C:{lobby.channel_id}: Evento de turno seteado pero player.word estaba vacío.")
                        player.word = "—" # Asignar valor por defecto
                        await channel.send(f"⌛ ¡Tiempo! <@{user_id}> no respondió. Su pista se registra como **'—'**.")
                    # --- FIN DE CAMBIO ---

                except asyncio.TimeoutError:
                    # Timeout
                    player.word = "—"
                    await channel.send(f"⌛ ¡Tiempo! <@{user_id}> no respondió. Su pista se registra como **'—'**.")
                
                finally:
                    # Limpiar el evento
                    self._turn_events.pop(lobby.channel_id, None)

            # --- 4. Fin de Fase ---
            log.info(f"Fase de turnos completada en C:{lobby.channel_id}")
            await channel.send("Todas las pistas han sido dadas. Pasando a votación...")
            await asyncio.sleep(3)
            
            async with lobby._lock:
                lobby.phase = PHASE_VOTE
                lobby.current_turn_idx = -1
                lobby.alive_order.clear()
            
            # 5. Llamar al Cog de Votaciones
            votes_cog = self.bot.get_cog("ImpostorVotes")
            if votes_cog:
                await votes_cog.start_vote_phase(lobby)
            else:
                log.error(f"FATAL: No se pudo encontrar 'ImpostorVotes' en C:{lobby.channel_id}")
                await channel.send("❌ ERROR FATAL: Módulo de Votación no cargado.")

        except asyncio.CancelledError:
            log.info(f"Turn loop C:{lobby.channel_id} cancelado.")
        except Exception as e:
            log.exception(f"Error catastrófico en _turn_loop C:{lobby.channel_id}: {e}")
            if channel:
                await channel.send(f"❌ Ocurrió un error grave en el bucle de turnos. {e}")
        finally:
            async with lobby._lock:
                if lobby._turn_task:
                    lobby._turn_task = None
            self._turn_events.pop(lobby.channel_id, None)

    # --- COMANDO /palabra (VUELVE A TENER ARGUMENTO) ---

    @app_commands.command(name="palabra", description="Envía tu palabra/pista secreta durante tu turno.")
    @app_commands.describe(pista="Tu pista (entre 1 y 5 palabras).")
    async def palabra(self, interaction: discord.Interaction, pista: str):
        
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        
        # --- Validaciones ---
        if not lobby:
            return await interaction.response.send_message("❌ Este comando solo se usa en un canal de partida.", ephemeral=True)
        if lobby.phase != PHASE_TURNS:
            return await interaction.response.send_message("❌ No es la fase de dar pistas.", ephemeral=True)
            
        player = lobby.get_player(interaction.user.id)
        if not player or player.is_bot:
            return await interaction.response.send_message("❌ No eres un jugador humano en esta partida.", ephemeral=True)
            
        if lobby.current_turn_idx < 0 or lobby.current_turn_idx >= len(lobby.alive_order):
            return await interaction.response.send_message("❌ Error de turno. Espera...", ephemeral=True)
            
        current_turn_player_id = lobby.alive_order[lobby.current_turn_idx]
        if player.user_id != current_turn_player_id:
            return await interaction.response.send_message("❌ No es tu turno.", ephemeral=True)
            
        if player.word is not None:
             return await interaction.response.send_message("❌ Ya has dado tu pista para esta ronda.", ephemeral=True)
             
        # Validar regex
        pista_limpia = pista.strip()
        match = WORD_REGEX.fullmatch(pista_limpia)
        
        if not match:
            return await interaction.response.send_message(
                "❌ Pista inválida. Debe tener **entre 1 y 5 palabras**, "
                "y cada palabra un máximo de 20 caracteres (letras, números, guiones, acentos/ñ).",
                ephemeral=True
            )
            
        # --- Éxito ---
        
        # 1. Almacenar la palabra (para que el _turn_loop la lea)
        player.word = pista_limpia
        
        # 2. Señalar al bucle de turnos que continúe
        event = self._turn_events.get(lobby.channel_id)
        if event:
            event.set()
        else:
            log.warning(f"/palabra C:{lobby.channel_id}: No se encontró evento para setear.")
            
        # 3. Confirmar al usuario (efímero, como pediste)
        await interaction.response.send_message("✅ Pista registrada.", ephemeral=True)

    def _try_accept_plain_word(self, lobby: GameState, player: GameState.Player, text: str) -> bool:
        pista_limpia = text.strip()
        if not WORD_REGEX.fullmatch(pista_limpia):
            return False
        if player.word is not None:
            return False
        player.word = pista_limpia
        event = self._turn_events.get(lobby.channel_id)
        if event:
            event.set()
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        lobby = core.get_lobby_by_channel(message.channel.id)
        if not lobby or lobby.phase == PHASE_END:
            return
        content = (message.content or "").strip()
        if not content or content.startswith("/"):
            return

        author_id = message.author.id
        if author_id in lobby.eliminated_user_ids:
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        if lobby.phase == PHASE_TURNS:
            player = lobby.get_player(author_id)
            if not player or player.is_bot:
                return
            if chat_guard.is_message_allowed_during_turns(lobby, author_id):
                if self._try_accept_plain_word(lobby, player, content):
                    return
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        if lobby.phase == PHASE_VOTE and lobby.votes_open:
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorTurnsCog(bot))