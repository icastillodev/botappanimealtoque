# cogs/impostor/lobby.py

import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import re
import asyncio
from typing import Optional, List, Set

# Importaciones locales (de nuestros otros archivos)
from . import core
from . import feed
from .engine import GameState, PHASE_IDLE, PHASE_ROLES, ROLE_IMPOSTOR, ROLE_SOCIAL

log = logging.getLogger(__name__)

# --- Funciones de Configuración ---

def get_category_id() -> Optional[int]:
    val = os.getenv("IMPOSTOR_CATEGORY_ID")
    return int(val) if val else None

def get_max_players() -> int:
    val = os.getenv("IMPOSTOR_MAX_PLAYERS", "5")
    return int(val)

def get_admin_role_ids() -> Set[int]:
    ids_str = os.getenv("IMPOSTOR_ADMIN_ROLE_IDS", "")
    return {int(id.strip()) for id in ids_str.split(',') if id.strip()}

def get_hud_update_interval() -> float:
    val = os.getenv("IMPOSTOR_HUD_EDIT_INTERVAL", "5")
    return float(val)

# --- Funciones de Utilidad ---

def _slugify(name: str) -> str:
    """Convierte un nombre de lobby en un nombre de canal válido."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s-]", "", name) # Quitar caracteres no alfanuméricos
    name = re.sub(r"[\s-]+", "-", name.strip()) # Reemplazar espacios por guiones
    return f"impostor-{name[:50]}" # Limitar longitud

async def _can_use_admin_commands(interaction: discord.Interaction) -> bool:
    """Verifica si el usuario es host O un admin del bot."""
    lobby = core.get_lobby_by_channel(interaction.channel_id)
    if lobby and lobby.host_id == interaction.user.id:
        return True
        
    admin_roles = get_admin_role_ids()
    if any(role.id in admin_roles for role in interaction.user.roles):
        return True
        
    return False

# --- Generación del HUD (Embed + View) ---

def _generate_lobby_embed(lobby: GameState, bot_user: discord.User) -> discord.Embed:
    """Crea el Embed para el panel de control del lobby."""
    
    max_players = get_max_players()
    
    if lobby.in_progress:
        # Si la partida está en curso, el embed es diferente
        # (Esto lo manejará game_core.py, pero dejamos un placeholder)
        embed = discord.Embed(
            title=f"Partida en Curso: {lobby.lobby_name}",
            description="La partida está en juego... ¡Mucha suerte!",
            color=discord.Color.red()
        )
        embed.add_field(name="Ronda", value=lobby.round_num, inline=True)
        embed.add_field(name="Fase", value=lobby.phase.capitalize(), inline=True)
        return embed

    # --- Embed de Lobby (Esperando jugadores) ---
    status_emoji = "🟢" if lobby.is_open else "🔒"
    status_text = "Abierto" if lobby.is_open else "Cerrado"
    
    embed = discord.Embed(
        title=f"{status_emoji} Lobby: {lobby.lobby_name} ({lobby.all_players_count}/{max_players})",
        description=f"Host: <@{lobby.host_id}> | Estado: **{status_text}**",
        color=discord.Color.blurple() if lobby.is_open else discord.Color.greyple()
    )

    player_list = []
    if not lobby.players:
        player_list.append("El lobby está vacío.")
    else:
        for player in lobby.players.values():
            ready_emoji = "✅" if (player.is_bot or player.ready_in_lobby) else "⏳"
            
            if player.user_id == bot_user.id:
                # El bot no necesita mostrarse en la lista
                continue

            if player.is_bot:
                player_list.append(f"{ready_emoji} 🤖 `AAT-Bot #{player.user_id}`")
            else:
                player_list.append(f"{ready_emoji} <@{player.user_id}>")
                
    embed.add_field(name="Jugadores", value="\n".join(player_list), inline=False)
    
    # Instrucciones
    if lobby.all_players_count < max_players:
        embed.set_footer(text=f"El host puede añadir bots o esperar más jugadores. Pulsa 'Ready' cuando estés listo.")
    else:
        if not lobby.all_humans_ready_in_lobby:
            embed.set_footer(text="¡Lobby lleno! Esperando que todos los jugadores humanos pulsen 'Ready'.")
        else:
            embed.set_footer(text="¡Todos listos! El Host puede comenzar la partida.")
            
    return embed


def _generate_lobby_view(lobby: GameState) -> discord.ui.View:
    """Crea la View (botones) para el panel de control del lobby."""
    view = discord.ui.View(timeout=None)
    
    # --- Fila 1: Acciones de Lobby ---
    # Botón de Ready
    ready_style = discord.ButtonStyle.success if lobby.all_humans_ready_in_lobby else discord.ButtonStyle.secondary
    view.add_item(LobbyButton(
        label="Ready", 
        style=ready_style,
        emoji="✅", 
        custom_id="imp:ready"
    ))

    # Botón de Abrir/Cerrar
    toggle_label = "Cerrar Lobby" if lobby.is_open else "Abrir Lobby"
    toggle_emoji = "🔒" if lobby.is_open else "🟢"
    view.add_item(LobbyButton(
        label=toggle_label, 
        emoji=toggle_emoji, 
        custom_id="imp:toggle_open"
    ))

    # --- Fila 2: Bots ---
    max_players = get_max_players()
    # Botón de Añadir Bot (deshabilitado si está lleno)
    view.add_item(LobbyButton(
        label="Add Bot", 
        emoji="➕", 
        custom_id="imp:addbot",
        disabled=(lobby.all_players_count >= max_players)
    ))

    # Botón de Quitar Bot (deshabilitado si no hay bots)
    view.add_item(LobbyButton(
        label="Quitar Bot", 
        emoji="➖", 
        custom_id="imp:removebot",
        disabled=(len(lobby.bot_players) == 0)
    ))

    # --- Fila 3: Acciones Críticas ---
    # Botón de Comenzar
    can_start = (lobby.all_players_count == max_players and lobby.all_humans_ready_in_lobby)
    view.add_item(LobbyButton(
        label="Comenzar", 
        style=discord.ButtonStyle.primary, 
        emoji="▶️", 
        custom_id="imp:start",
        disabled=(not can_start)
    ))

    # Botón de Salir
    view.add_item(LobbyButton(
        label="Leave", 
        style=discord.ButtonStyle.danger, 
        emoji="🚪", 
        custom_id="imp:leave"
    ))
    
    return view


# --- Actualizador de HUD ---
# Esta función es la única responsable de editar el mensaje del HUD.
# Será llamada por los botones y por el loop periódico.

_hud_update_queue: Set[int] = set()
_hud_update_lock = asyncio.Lock()

async def queue_hud_update(channel_id: int):
    """Agrega un lobby a la cola de actualización."""
    _hud_update_queue.add(channel_id)


async def _process_hud_updates(bot: commands.Bot):
    """Procesa todos los HUDs en la cola."""
    global _hud_update_queue
    if not _hud_update_queue:
        return

    async with _hud_update_lock:
        # Copiamos la cola y la limpiamos
        channel_ids_to_update = list(_hud_update_queue)
        _hud_update_queue.clear()
        
        # log.debug(f"Procesando {len(channel_ids_to_update)} actualizaciones de HUD...")

        for channel_id in channel_ids_to_update:
            lobby = core.get_lobby_by_channel(channel_id)
            if not lobby:
                # log.debug(f"HUD Update: Lobby C:{channel_id} no encontrado, omitiendo.")
                continue

            # No actualizamos HUD si la partida está en fase de roles o terminando
            if lobby.phase not in [PHASE_IDLE]:
                 # log.debug(f"HUD Update: Lobby C:{channel_id} está en fase '{lobby.phase}', omitiendo.")
                 continue

            channel = bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                log.warning(f"No se pudo encontrar el canal C:{channel_id} para actualizar HUD.")
                continue

            try:
                # Generar contenido nuevo
                embed = _generate_lobby_embed(lobby, bot.user)
                view = _generate_lobby_view(lobby)

                if lobby.hud_message_id:
                    msg = await channel.fetch_message(lobby.hud_message_id)
                    await msg.edit(embed=embed, view=view)
                else:
                    # Si no hay ID, publicar uno nuevo y guardarlo
                    log.warning(f"HUD Message ID faltante para C:{channel_id}. Re-publicando...")
                    # Borrar mensajes viejos del bot para evitar spam
                    await channel.purge(limit=10, check=lambda m: m.author.id == bot.user.id)
                    new_msg = await channel.send(embed=embed, view=view)
                    lobby.hud_message_id = new_msg.id
            
            except discord.NotFound:
                log.warning(f"Mensaje HUD {lobby.hud_message_id} no encontrado en C:{channel_id}. Re-publicando.")
                lobby.hud_message_id = None # Forzar re-publicación
                _hud_update_queue.add(channel_id) # Re-encolar para el próximo ciclo
            except discord.Forbidden:
                log.error(f"No tengo permisos para editar/enviar HUD en C:{channel_id}")
            except Exception as e:
                log.exception(f"Error desconocido al actualizar HUD en C:{channel_id}: {e}")

# --- Clase del Botón (Callback Handler) ---

class LobbyButton(discord.ui.Button):
    """Botón genérico que maneja todos los callbacks del lobby."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        # 1. Obtener el Bot y el Lobby
        bot: commands.Bot = interaction.client
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        
        if not lobby:
            return await interaction.response.send_message(
                "❌ Este lobby parece estar corrupto o no existe. Avisa a un admin.", 
                ephemeral=True
            )

        # 2. Validar que el usuario está en el lobby (excepto para 'Leave')
        player = lobby.get_player(interaction.user.id)
        if not player and self.custom_id != "imp:leave":
            # Si el usuario no es jugador, no puede tocar nada (excepto Leave)
            return await interaction.response.send_message(
                "❌ No eres parte de este lobby.", ephemeral=True
            )
            
        # 3. Manejar según el custom_id
        try:
            handler = _BUTTON_HANDLERS.get(self.custom_id)
            if handler:
                # Llamamos al handler específico (definidos abajo)
                await handler(interaction, bot, lobby, player)
            else:
                await interaction.response.send_message("Botón no implementado.", ephemeral=True)
        
        except Exception as e:
            log.exception(f"Error procesando botón {self.custom_id} por {interaction.user.name}: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Ocurrió un error inesperado.", ephemeral=True)
        
        # 4. Encolar actualización de HUD (si la partida no ha empezado)
        if not lobby.in_progress:
            await queue_hud_update(lobby.channel_id)


# --- Lógica de los Botones ---

async def _handle_ready(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    if player.is_bot:
        return await interaction.response.send_message("Los bots siempre están listos.", ephemeral=True)
        
    player.ready_in_lobby = not player.ready_in_lobby
    status = "LISTO" if player.ready_in_lobby else "NO LISTO"
    
    await interaction.response.send_message(f"Te has marcado como **{status}**.", ephemeral=True)

async def _handle_toggle_open(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    if lobby.host_id != player.user_id:
        return await interaction.response.send_message("❌ Solo el host puede abrir o cerrar el lobby.", ephemeral=True)
        
    lobby.is_open = not lobby.is_open
    status = "ABIERTO" if lobby.is_open else "CERRADO"
    
    await interaction.response.send_message(f"El lobby ahora está **{status}**.", ephemeral=True)
    await feed.update_feed(bot) # Actualizar cartelera

async def _handle_add_bot(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    if not await _can_use_admin_commands(interaction):
        return await interaction.response.send_message("❌ Solo el host o un admin pueden añadir bots.", ephemeral=True)

    max_players = get_max_players()
    if lobby.all_players_count >= max_players:
        return await interaction.response.send_message("❌ El lobby está lleno.", ephemeral=True)

    # Lógica de bots.py
    cog = bot.get_cog("ImpostorBots")
    if not cog:
        return await interaction.response.send_message("Error: Módulo de Bots no cargado.", ephemeral=True)
        
    bot_name = await cog.add_bot_logic(lobby)
    await interaction.response.send_message(f"🤖 Bot `{bot_name}` añadido.", ephemeral=True)
    await feed.update_feed(bot)

async def _handle_remove_bot(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    if not await _can_use_admin_commands(interaction):
        return await interaction.response.send_message("❌ Solo el host o un admin pueden quitar bots.", ephemeral=True)

    if not lobby.bot_players:
        return await interaction.response.send_message("❌ No hay bots para quitar.", ephemeral=True)

    # Lógica de bots.py
    cog = bot.get_cog("ImpostorBots")
    if not cog:
        return await interaction.response.send_message("Error: Módulo de Bots no cargado.", ephemeral=True)
        
    bot_name = await cog.remove_bot_logic(lobby)
    await interaction.response.send_message(f"🤖 Bot `{bot_name}` eliminado.", ephemeral=True)
    await feed.update_feed(bot)

async def _handle_start(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    if lobby.host_id != player.user_id:
        return await interaction.response.send_message("❌ Solo el host puede iniciar la partida.", ephemeral=True)

    max_players = get_max_players()
    if lobby.all_players_count != max_players:
        return await interaction.response.send_message(f"❌ Se necesitan {max_players} jugadores (humanos + bots).", ephemeral=True)
        
    if not lobby.all_humans_ready_in_lobby:
        return await interaction.response.send_message("❌ No todos los jugadores humanos están listos.", ephemeral=True)
        
    if lobby.in_progress:
        return await interaction.response.send_message("❌ La partida ya ha comenzado.", ephemeral=True)

    # --- ¡Comenzar la partida! ---
    await interaction.response.send_message("▶️ Iniciando la partida...", ephemeral=True)
    
    # 1. Marcar el lobby como "en progreso"
    lobby.in_progress = True
    lobby.phase = PHASE_ROLES
    
    # 2. Actualizar el feed (el lobby desaparecerá de la lista)
    await feed.update_feed(bot)
    
    # 3. Llamar al Cog 'game_core' para que maneje el inicio
    game_cog = bot.get_cog("ImpostorGameCore")
    if not game_cog:
        log.error("¡¡FATAL: No se pudo encontrar el Cog 'ImpostorGameCore'!!")
        return await interaction.followup.send("❌ ERROR FATAL: El módulo 'game_core' no está cargado.", ephemeral=True)
    
    # Esta función (start_game) se definirá en game_core.py
    # y se encargará de asignar roles, etc.
    await game_cog.start_game(lobby)
    
    # 4. El HUD se actualizará por la lógica de game_core, no aquí.

async def _handle_leave(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    # 'player' puede ser None si el usuario ya no estaba en el lobby (p.ej. fue kickeado)
    # pero aún así pulsa el botón 'Leave'.
    
    await interaction.response.send_message("Saliendo del lobby...", ephemeral=True)
    
    # Llamar a la lógica de salida (definida en el Cog)
    lobby_cog = bot.get_cog("ImpostorLobby")
    if lobby_cog:
        # Esta función maneja la eliminación del canal si es necesario
        await lobby_cog.handle_leave_logic(interaction.user, lobby)
    else:
        log.error("No se pudo encontrar el Cog 'ImpostorLobby' para manejar la salida.")

# Mapa de Handlers para los botones
_BUTTON_HANDLERS = {
    "imp:ready": _handle_ready,
    "imp:toggle_open": _handle_toggle_open,
    "imp:addbot": _handle_add_bot,
    "imp:removebot": _handle_remove_bot,
    "imp:start": _handle_start,
    "imp:leave": _handle_leave,
}


# --- Cog: Comandos y Tareas ---

class ImpostorLobbyCog(commands.Cog, name="ImpostorLobby"):
    """
    Gestiona la creación, unión y panel de control (HUD) de los lobbies.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Iniciar el loop periódico de actualización de HUDs
        self.hud_updater_task.start()

    def cog_unload(self):
        # Detener el loop al descargar el cog
        self.hud_updater_task.cancel()

    @tasks.loop(seconds=get_hud_update_interval())
    async def hud_updater_task(self):
        """
        Tarea periódica que actualiza todos los HUDs de lobbies
        que están en fase 'idle' (esperando).
        """
        try:
            # 1. Encolar todos los lobbies activos
            all_lobbies = core.get_all_lobbies()
            for lobby in all_lobbies:
                if not lobby.in_progress:
                    await queue_hud_update(lobby.channel_id)
            
            # 2. Procesar la cola
            await _process_hud_updates(self.bot)

        except Exception as e:
            log.exception(f"Error en el loop hud_updater_task: {e}")

    @hud_updater_task.before_loop
    async def before_hud_updater(self):
        await self.bot.wait_until_ready()
        log.info(f"Iniciando loop de actualización de HUD (Intervalo: {get_hud_update_interval()}s)")

    # --- Lógica de Salida (Usada por /leave y botón 'Leave') ---
    
    async def handle_leave_logic(self, user: discord.Member, lobby: Optional[GameState] = None):
        """
        Lógica centralizada para que un usuario abandone un lobby.
        """
        if not lobby:
            lobby = core.get_lobby_by_user(user.id)
        
        if not lobby:
            # El usuario no está en ningún lobby
            return

        # 1. Quitar al usuario del registro
        core.remove_user_from_lobby(user.id)
        log.info(f"{user.name} ha salido del lobby {lobby.lobby_name} (C:{lobby.channel_id})")

        # 2. Comprobar si el lobby debe ser borrado
        # (Si solo quedan bots, o si el host se fue y no hay humanos)
        remaining_humans = lobby.human_players
        
        # Regla: Si el host se va, el lobby se cierra
        if lobby.host_id == user.id:
            log.info(f"El Host {user.name} ha abandonado el lobby {lobby.lobby_name}. Cerrando lobby.")
            # Transferir host al siguiente humano, o borrar si no hay
            if remaining_humans:
                lobby.host_id = remaining_humans[0].user_id
                log.info(f"Nuevo host: {remaining_humans[0].user_id}")
                # Avisar en el canal
                try:
                    channel = await self.bot.fetch_channel(lobby.channel_id)
                    await channel.send(f"👑 <@{user.id}> ha abandonado. El nuevo host es <@{lobby.host_id}>.")
                except (discord.NotFound, discord.Forbidden):
                    pass # El canal puede estar borrándose
            else:
                # No quedan humanos, marcar para borrar
                remaining_humans = [] 

        if not remaining_humans:
            log.info(f"No quedan humanos en el lobby {lobby.lobby_name}. Borrando canal...")
            try:
                channel = await self.bot.fetch_channel(lobby.channel_id)
                await channel.delete(reason="Lobby de Impostor vacío (sin humanos)")
            except discord.NotFound:
                log.warning(f"Se intentó borrar el canal C:{lobby.channel_id} pero no se encontró.")
            except discord.Forbidden:
                log.error(f"No tengo permisos para borrar el canal C:{lobby.channel_id}")
            finally:
                # Quitar el lobby del registro
                core.remove_lobby(lobby.channel_id)
        
        # 3. Actualizar el feed (el lobby puede haberse borrado o tener menos jugadores)
        await feed.update_feed(self.bot)
        
        # 4. Actualizar el HUD (si el lobby aún existe)
        if core.get_lobby_by_channel(lobby.channel_id):
            await queue_hud_update(lobby.channel_id)


    # --- Comandos Slash ---

    @app_commands.command(name="crearsimpostor", description="Crea un nuevo lobby para el juego Impostor.")
    @app_commands.describe(nombre="Nombre para tu lobby (ej: 'Pros Only')")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Abierto (Cualquiera puede unirse)", value="abierto"),
        app_commands.Choice(name="Cerrado (Solo con invitación, no implementado)", value="cerrado")
    ])
    async def crearsimpostor(self, interaction: discord.Interaction, nombre: str, tipo: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        
        # 1. Validar si ya está en un lobby
        if core.get_lobby_by_user(interaction.user.id):
            await interaction.followup.send(
                "❌ Ya estás en un lobby. Usa `/leave` para salir del actual antes de crear uno nuevo.", 
                ephemeral=True
            )
            return

        # 2. Validar categoría
        category_id = get_category_id()
        category = interaction.guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            log.error(f"IMPOSTOR_CATEGORY_ID ({category_id}) no se encuentra o no es una categoría.")
            await interaction.followup.send(
                "❌ Error de configuración del servidor: No se encuentra la categoría de juegos. Avisa a un admin.", 
                ephemeral=True
            )
            return
            
        is_open = (tipo.value == "abierto")
        channel_name = _slugify(nombre)
        
        # 3. Definir permisos
        # (Oculto para todos, visible solo para el host y el bot)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        # 4. Crear canal
        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Lobby de Impostor: {nombre} | Host: {interaction.user.name}"
            )
        except discord.Forbidden:
            log.error(f"No tengo permisos para crear canales en la categoría {category.name}")
            await interaction.followup.send("❌ Error: No tengo permisos para crear canales en esa categoría.", ephemeral=True)
            return
        except Exception as e:
            log.exception(f"Error al crear canal: {e}")
            await interaction.followup.send("❌ Ocurrió un error inesperado al crear el canal.", ephemeral=True)
            return
            
        # 5. Crear y registrar el lobby (GameState)
        lobby = core.create_lobby(
            guild_id=interaction.guild_id,
            channel_id=channel.id,
            host_id=interaction.user.id,
            lobby_name=nombre,
            is_open=is_open
        )
        
        # 6. Publicar el HUD
        try:
            embed = _generate_lobby_embed(lobby, self.bot.user)
            view = _generate_lobby_view(lobby)
            msg = await channel.send(embed=embed, view=view)
            lobby.hud_message_id = msg.id
        except Exception as e:
            log.exception(f"Error al publicar el HUD en C:{channel.id}: {e}")
            # No fallamos, el HUD se re-publicará en el próximo ciclo
            
        # 7. Actualizar el feed
        await feed.update_feed(self.bot)
        
        # 8. Responder al usuario
        await interaction.followup.send(
            f"✅ ¡Lobby **{nombre}** creado! Entra aquí: <#{channel.id}>", 
            ephemeral=True
        )

    @app_commands.command(name="entrar", description="Únete a un lobby de Impostor abierto.")
    @app_commands.describe(nombre="El nombre exacto del lobby al que quieres unirte.")
    async def entrar(self, interaction: discord.Interaction, nombre: str):
        await interaction.response.defer(ephemeral=True)

        # 1. Validar si ya está en un lobby
        if core.get_lobby_by_user(interaction.user.id):
            await interaction.followup.send(
                "❌ Ya estás en un lobby. Usa `/leave` para salir del actual.", 
                ephemeral=True
            )
            return

        # 2. Buscar el lobby por nombre
        target_lobby: Optional[GameState] = None
        for lobby in core.get_all_lobbies():
            if lobby.lobby_name.lower() == nombre.lower():
                target_lobby = lobby
                break
        
        if not target_lobby:
            await interaction.followup.send(f"❌ No se encontró ningún lobby llamado **{nombre}**.", ephemeral=True)
            return

        # 3. Validar estado del lobby
        if not target_lobby.is_open:
            await interaction.followup.send(f"❌ El lobby **{nombre}** está cerrado.", ephemeral=True)
            return
        if target_lobby.in_progress:
            await interaction.followup.send(f"❌ La partida en **{nombre}** ya ha comenzado.", ephemeral=True)
            return
        
        max_players = get_max_players()
        if target_lobby.all_players_count >= max_players:
            await interaction.followup.send(f"❌ El lobby **{nombre}** está lleno.", ephemeral=True)
            return
            
        # 4. Añadir usuario al canal
        channel = interaction.guild.get_channel(target_lobby.channel_id)
        if not channel:
            await interaction.followup.send("❌ Error: El canal de ese lobby no existe. Avisa a un admin.", ephemeral=True)
            core.remove_lobby(target_lobby.channel_id) # Limpieza
            return
            
        try:
            await channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Error: No tengo permisos para añadirte al canal de ese lobby.", ephemeral=True)
            return
            
        # 5. Añadir usuario al GameState (core)
        core.add_user_to_lobby(interaction.user.id, target_lobby.channel_id)
        
        # 6. Actualizar feed y HUD
        await feed.update_feed(self.bot)
        await queue_hud_update(target_lobby.channel_id)
        
        # 7. Responder
        await interaction.followup.send(
            f"✅ Te has unido al lobby **{nombre}**. Entra aquí: <#{target_lobby.channel_id}>",
            ephemeral=True
        )

    @app_commands.command(name="leave", description="Abandona el lobby de Impostor en el que te encuentras.")
    async def leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        lobby = core.get_lobby_by_user(interaction.user.id)
        if not lobby:
            await interaction.followup.send("❌ No estás en ningún lobby.", ephemeral=True)
            return

        # --- NUEVA VALIDACIÓN ---
        if lobby.in_progress:
            await interaction.followup.send(
                "❌ No puedes abandonar una partida que ya ha comenzado.\n"
                "Si la partida se ha trabado, pide a un admin que use `/cleanimpostor`.",
                ephemeral=True
            )
            return
        # --- FIN VALIDACIÓN ---
            
        await self.handle_leave_logic(interaction.user, lobby)
        
        await interaction.followup.send(f"Has abandonado el lobby **{lobby.lobby_name}**.", ephemeral=True)

    @app_commands.command(name="salir", description="Abandona el lobby de Impostor en el que te encuentras.")
    async def salir(self, interaction: discord.Interaction):
        """Esta función es un alias de /leave"""
        # Llama a la lógica del comando /leave
        await self.leave.callback(self, interaction)


    @app_commands.command(name="ready", description="Marca tu estado como Listo/No Listo en el lobby.")
    async def ready_command(self, interaction: discord.Interaction):
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby:
            return await interaction.response.send_message(
                "❌ Este comando solo se puede usar dentro de un canal de lobby.", 
                ephemeral=True
            )
            
        player = lobby.get_player(interaction.user.id)
        if not player or player.is_bot:
            return await interaction.response.send_message(
                "❌ No eres un jugador humano en este lobby.", 
                ephemeral=True
            )
            
        await _handle_ready(interaction, self.bot, lobby, player)
        await queue_hud_update(lobby.channel_id)

    @app_commands.command(name="abrirlobby", description="[Host] Abre tu lobby actual.")
    async def abrirlobby(self, interaction: discord.Interaction):
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby or lobby.host_id != interaction.user.id:
            return await interaction.response.send_message(
                "❌ Solo puedes usar esto en tu lobby y si eres el host.", 
                ephemeral=True
            )
            
        if lobby.is_open:
            return await interaction.response.send_message("El lobby ya estaba abierto.", ephemeral=True)
            
        lobby.is_open = True
        await interaction.response.send_message("El lobby ahora está **ABIERTO**.", ephemeral=True)
        await feed.update_feed(self.bot)
        await queue_hud_update(lobby.channel_id)
        
    @app_commands.command(name="cerrarlobby", description="[Host] Cierra tu lobby actual.")
    async def cerrarlobby(self, interaction: discord.Interaction):
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby or lobby.host_id != interaction.user.id:
            return await interaction.response.send_message(
                "❌ Solo puedes usar esto en tu lobby y si eres el host.", 
                ephemeral=True
            )
            
        if not lobby.is_open:
            return await interaction.response.send_message("El lobby ya estaba cerrado.", ephemeral=True)
            
        lobby.is_open = False
        await interaction.response.send_message("El lobby ahora está **CERRADO**.", ephemeral=True)
        await feed.update_feed(self.bot)
        await queue_hud_update(lobby.channel_id)


# --- Setup del Cog ---

async def setup(bot: commands.Bot):
    # Registrar la View persistente (aunque la estamos recreando, 
    # esto es bueno por si acaso)
    # bot.add_view(LobbyView(bot)) 
    # Nota: Decidimos no usar vista persistente, sino recrearla.
    
    await bot.add_cog(ImpostorLobbyCog(bot))