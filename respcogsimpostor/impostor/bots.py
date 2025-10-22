# cogs/impostor/bots.py

import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, Set

# Importaciones locales
from . import core
from .engine import GameState
from . import feed
from . import lobby as lobby_cog # Importamos el módulo lobby para usar queue_hud_update

log = logging.getLogger(__name__)

# --- Funciones de Configuración ---

def get_max_players() -> int:
    val = os.getenv("IMPOSTOR_MAX_PLAYERS", "5")
    return int(val)

def get_admin_role_ids() -> Set[int]:
    ids_str = os.getenv("IMPOSTOR_ADMIN_ROLE_IDS", "")
    return {int(id.strip()) for id in ids_str.split(',') if id.strip()}

# --- Funciones de Utilidad ---

def _find_next_bot_id(lobby: GameState) -> int:
    """Encuentra el próximo ID negativo disponible para un bot."""
    bot_ids = {p.user_id for p in lobby.bot_players}
    next_id = -1
    while next_id in bot_ids:
        next_id -= 1
    return next_id

async def _can_manage_bots(interaction: discord.Interaction, lobby: GameState) -> bool:
    """Verifica si el usuario es host O un admin del bot."""
    if lobby.host_id == interaction.user.id:
        return True
        
    admin_roles = get_admin_role_ids()
    # interaction.user.roles es una lista de objetos discord.Role
    if any(role.id in admin_roles for role in interaction.user.roles):
        return True
        
    return False

# --- Cog: Lógica y Comandos de Bots ---

class ImpostorBotsCog(commands.Cog, name="ImpostorBots"):
    """
    Gestiona la adición y eliminación de bots en los lobbies.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Lógica centralizada (llamada por botones y comandos) ---

    async def add_bot_logic(self, lobby: GameState) -> Optional[str]:
        """
        Añade un bot al lobby.
        Devuelve el nombre del bot si se añade, o None si el lobby está lleno.
        """
        max_players = get_max_players()
        if lobby.all_players_count >= max_players:
            log.debug(f"Intento de añadir bot a lobby lleno C:{lobby.channel_id}")
            return None # Lobby lleno

        bot_id = _find_next_bot_id(lobby)
        bot_name = f"AAT-Bot #{abs(bot_id)}"
        
        # add_player (de engine.py) ya marca a los bots como 'ready_in_lobby=True'
        lobby.add_player(user_id=bot_id, is_bot=True)
        
        log.info(f"Bot '{bot_name}' (ID: {bot_id}) añadido al lobby {lobby.lobby_name}")
        return bot_name

    async def remove_bot_logic(self, lobby: GameState) -> Optional[str]:
        """
        Quita un bot del lobby.
        Devuelve el nombre del bot si se quita, o None si no había bots.
        """
        if not lobby.bot_players:
            log.debug(f"Intento de quitar bot de lobby C:{lobby.channel_id} sin bots")
            return None # No hay bots

        # Quitar el último bot añadido
        bot_to_remove = lobby.bot_players[-1]
        lobby.remove_player(bot_to_remove.user_id)
        
        bot_name = f"AAT-Bot #{abs(bot_to_remove.user_id)}"
        log.info(f"Bot '{bot_name}' (ID: {bot_to_remove.user_id}) quitado del lobby {lobby.lobby_name}")
        return bot_name

    # --- Comandos Slash ---

    @app_commands.command(name="addbot", description="[Host/Admin] Añade un bot al lobby actual.")
    async def addbot(self, interaction: discord.Interaction):
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.response.send_message(
                "❌ Este comando solo se puede usar dentro de un canal de lobby.", 
                ephemeral=True
            )
            
        if not await _can_manage_bots(interaction, lobby):
            return await interaction.response.send_message(
                "❌ Solo el host o un admin pueden añadir bots.", 
                ephemeral=True
            )
            
        bot_name = await self.add_bot_logic(lobby)
        
        if bot_name:
            await interaction.response.send_message(f"🤖 Bot `{bot_name}` añadido.", ephemeral=True)
            # Actualizar feed y HUD
            await feed.update_feed(self.bot)
            await lobby_cog.queue_hud_update(lobby.channel_id)
        else:
            await interaction.response.send_message("❌ El lobby está lleno.", ephemeral=True)

    @app_commands.command(name="removebot", description="[Host/Admin] Quita un bot del lobby actual.")
    async def removebot(self, interaction: discord.Interaction):
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.response.send_message(
                "❌ Este comando solo se puede usar dentro de un canal de lobby.", 
                ephemeral=True
            )
            
        if not await _can_manage_bots(interaction, lobby):
            return await interaction.response.send_message(
                "❌ Solo el host o un admin pueden quitar bots.", 
                ephemeral=True
            )
            
        bot_name = await self.remove_bot_logic(lobby)
        
        if bot_name:
            await interaction.response.send_message(f"🤖 Bot `{bot_name}` eliminado.", ephemeral=True)
            # Actualizar feed y HUD
            await feed.update_feed(self.bot)
            await lobby_cog.queue_hud_update(lobby.channel_id)
        else:
            await interaction.response.send_message("❌ No hay bots en el lobby para quitar.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorBotsCog(bot))