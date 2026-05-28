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
from . import notify as impostor_notify
from .engine import GameState, PHASE_IDLE, PHASE_ROLES, PHASE_END
from . import rules
from .activity import touch_lobby_activity, sweep_idle_lobbies, get_lobby_idle_close_seconds
from .slots import UNLIMITED_SLOTS, format_slots_label, parse_max_players_env, _env_unlimited
from .config import get_min_impo_players
from .leave_guard import leave_block_reason

log = logging.getLogger(__name__)

# --- Funciones de Configuración ---

def get_category_id() -> Optional[int]:
    val = os.getenv("IMPOSTOR_CATEGORY_ID")
    return int(val) if val else None


def get_max_players() -> int:
    return parse_max_players_env()


def get_global_slot_ceiling() -> int:
    return max(get_min_impo_players(), get_max_players())


def get_default_lobby_slots() -> int:
    raw = (os.getenv("IMPOSTOR_DEFAULT_SLOTS") or "").strip()
    if _env_unlimited(raw):
        return get_max_players()
    try:
        v = int(raw)
        if v <= 0:
            return get_max_players()
        return min(v, get_global_slot_ceiling())
    except ValueError:
        return get_global_slot_ceiling()


async def close_lobby_channel(bot: commands.Bot, lobby: GameState, *, reason: str) -> bool:
    """Borra el canal del lobby y limpia el registro en memoria."""
    cid = lobby.channel_id
    core.remove_lobby(cid)
    await feed.update_feed(bot)
    try:
        channel = bot.get_channel(cid)
        if channel is None:
            channel = await bot.fetch_channel(cid)
        if isinstance(channel, discord.TextChannel):
            await channel.delete(reason=reason)
        return True
    except discord.NotFound:
        return True
    except (discord.Forbidden, discord.HTTPException) as e:
        log.warning("No se pudo borrar canal C:%s: %s", cid, e)
        return False


def _after_roster_change(lobby: GameState) -> None:
    touch_lobby_activity(lobby)
    if not lobby.in_progress:
        rules.clamp_impostor_count(lobby)

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
    # Asegurarse que interaction.user es Member
    if isinstance(interaction.user, discord.Member):
        if any(role.id in admin_roles for role in interaction.user.roles):
            return True
        
    return False

# --- Generación del HUD (Embed + View) ---

def _generate_lobby_embed(lobby: GameState, bot_user: discord.User) -> discord.Embed:
    """Crea el Embed para el panel de control del lobby."""
    
    max_players = lobby.max_slots
    min_p = get_min_impo_players()
    
    # --- Embed de Lobby (Esperando jugadores) ---
    status_emoji = "🟢" if lobby.is_open else "🔒"
    status_text = "Abierto" if lobby.is_open else "Cerrado"
    
    slots_txt = format_slots_label(lobby.all_players_count, max_players)
    embed = discord.Embed(
        title=f"{status_emoji} Lobby: {lobby.lobby_name} ({slots_txt})",
        description=f"Host: <@{lobby.host_id}> | Estado: **{status_text}**",
        color=discord.Color.blurple() if lobby.is_open else discord.Color.greyple()
    )

    player_list = []
    # Ordenar: Host primero, luego humanos, luego bots
    sorted_players = sorted(lobby.players.values(), key=lambda p: (
        p.user_id != lobby.host_id, # Host primero (False)
        p.is_bot # Humanos antes que bots
    ))

    if not lobby.players:
        player_list.append("El lobby está vacío.")
    else:
        for player in sorted_players:
            ready_emoji = "✅" if (player.is_bot or player.ready_in_lobby) else "⏳"
            host_indicator = "👑" if player.user_id == lobby.host_id else ""
            
            if player.user_id == bot_user.id:
                 continue # No mostrar al bot aquí

            if player.is_bot:
                player_list.append(f"{ready_emoji} 🤖 `AAT-Bot #{abs(player.user_id)}`")
            else:
                player_list.append(f"{ready_emoji} {host_indicator}<@{player.user_id}>")
                
    embed.add_field(name="Jugadores", value="\n".join(player_list), inline=False)

    if not lobby.in_progress:
        mx_imp = rules.max_impostors_for_players(lobby.all_players_count)
        rules.clamp_impostor_count(lobby)
        embed.add_field(
            name="🕵️ Impostores",
            value=f"**{lobby.impostor_count}** / **{mx_imp}** máx.\n"
            f"Host: botones **+ Imp** / **− Imp** (+1 cada ~3 jugadores).",
            inline=False,
        )
    
    # Instrucciones
    if lobby.all_players_count < max_players:
        embed.set_footer(
            text=f"Mínimo {min_p} jugadores para empezar (el cupo solo limita el máximo). "
            f"Host: /invitar o Add Bot. Jugadores: Ready."
        )
    else:
        if not lobby.all_humans_ready_in_lobby:
            embed.set_footer(text="¡Cupo lleno! Esperando que todos los humanos pulsen 'Ready'.")
        else:
            embed.set_footer(text="¡Todos listos! El host puede comenzar la partida.")
            
    return embed


def _generate_lobby_view(lobby: GameState) -> discord.ui.View:
    """Crea la View (botones) para el panel de control del lobby."""
    view = discord.ui.View(timeout=None)
    max_players = lobby.max_slots
    min_p = get_min_impo_players()
    
    # --- Fila 1: Acciones de Lobby ---
    view.add_item(LobbyButton(
        label="Ready", 
        style=discord.ButtonStyle.success,
        emoji="✅" if lobby.all_humans_ready_in_lobby else "☑️", 
        custom_id="imp:ready"
    ))
    view.add_item(LobbyButton(
        label="Cerrar Lobby" if lobby.is_open else "Abrir Lobby", 
        emoji="🔒" if lobby.is_open else "🟢", 
        custom_id="imp:toggle_open"
    ))

    # --- Fila 2: Bots e Invitación ---
    view.add_item(LobbyButton(
        label="Add Bot", 
        emoji="➕", 
        custom_id="imp:addbot",
        disabled=(lobby.all_players_count >= max_players),
        row=1
    ))
    view.add_item(LobbyButton(
        label="Quitar Bot", 
        emoji="➖", 
        custom_id="imp:removebot",
        disabled=(len(lobby.bot_players) == 0),
        row=1
    ))
    # --- Botón Invitar Info ---
    view.add_item(LobbyButton(
        label="Invitar Info",
        style=discord.ButtonStyle.secondary,
        emoji="💌",
        custom_id="imp:invite_info",
        disabled=(lobby.all_players_count >= max_players),
        row=1
    ))
    # --- Fin Botón ---

    # --- Fila 3: Acciones Críticas ---
    can_start = (
        lobby.all_players_count >= min_p
        and lobby.all_players_count <= max_players
        and lobby.all_humans_ready_in_lobby
    )
    can_force = (
        lobby.all_players_count >= min_p
        and lobby.all_players_count <= max_players
        and not lobby.all_humans_ready_in_lobby
    )
    view.add_item(LobbyButton(
        label="Comenzar", 
        style=discord.ButtonStyle.primary, 
        emoji="▶️", 
        custom_id="imp:start",
        disabled=(not can_start),
        row=2
    ))
    view.add_item(LobbyButton(
        label="Forzar inicio",
        style=discord.ButtonStyle.secondary,
        emoji="⚡",
        custom_id="imp:force_start",
        disabled=(not can_force),
        row=2
    ))
    view.add_item(LobbyButton(
        label="Llamar jugadores",
        style=discord.ButtonStyle.secondary,
        emoji="📢",
        custom_id="imp:notify_ping",
        row=2
    ))
    if not lobby.in_progress:
        mx_imp = rules.max_impostors_for_players(lobby.all_players_count)
        rules.clamp_impostor_count(lobby)
        view.add_item(LobbyButton(
            label="+ Imp",
            style=discord.ButtonStyle.secondary,
            emoji="🕵️",
            custom_id="imp:imp_plus",
            disabled=(lobby.impostor_count >= mx_imp),
            row=3,
        ))
        view.add_item(LobbyButton(
            label="− Imp",
            style=discord.ButtonStyle.secondary,
            custom_id="imp:imp_minus",
            disabled=(lobby.impostor_count <= 1),
            row=3,
        ))
    if not lobby.in_progress:
        view.add_item(LobbyButton(
            label="Cerrar sala",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            custom_id="imp:close_lobby_idle",
            row=4,
        ))
    view.add_item(LobbyButton(
        label="Leave", 
        style=discord.ButtonStyle.danger, 
        emoji="🚪", 
        custom_id="imp:leave",
        row=4
    ))
    
    return view


# --- Actualizador de HUD ---
_hud_update_queue: Set[int] = set()
_hud_update_lock = asyncio.Lock()

async def queue_hud_update(channel_id: int):
    """Agrega un lobby a la cola de actualización."""
    async with _hud_update_lock: # Proteger acceso a la cola
        _hud_update_queue.add(channel_id)


async def _process_hud_updates(bot: commands.Bot):
    """Procesa todos los HUDs en la cola."""
    global _hud_update_queue
    
    channel_ids_to_update = []
    async with _hud_update_lock: # Proteger acceso a la cola
        if not _hud_update_queue:
            return
        # Copiamos la cola y la limpiamos
        channel_ids_to_update = list(_hud_update_queue)
        _hud_update_queue.clear()
        
    # log.debug(f"Procesando {len(channel_ids_to_update)} actualizaciones de HUD...")

    for channel_id in channel_ids_to_update:
        lobby = core.get_lobby_by_channel(channel_id)
        if not lobby:
            # log.debug(f"HUD Update: Lobby C:{channel_id} no encontrado, omitiendo.")
            continue

        # Solo actualizar HUD si estamos en fase IDLE
        if lobby.phase != PHASE_IDLE:
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
                try:
                    msg = await channel.fetch_message(lobby.hud_message_id)
                    await msg.edit(embed=embed, view=view)
                except discord.NotFound:
                    log.warning(f"Mensaje HUD {lobby.hud_message_id} no encontrado en C:{channel_id}. Re-publicando.")
                    lobby.hud_message_id = None # Forzar re-publicación
                    # Re-encolar para el próximo ciclo (usando la función segura)
                    await queue_hud_update(channel_id) 
            else:
                # Si no hay ID, publicar uno nuevo y guardarlo
                log.warning(f"HUD Message ID faltante para C:{channel_id}. Re-publicando...")
                # Borrar mensajes viejos del bot para evitar spam
                try:
                    await channel.purge(limit=10, check=lambda m: m.author.id == bot.user.id)
                except discord.Forbidden:
                     log.warning(f"No tengo permisos para limpiar mensajes antiguos en C:{channel_id}")

                new_msg = await channel.send(embed=embed, view=view)
                lobby.hud_message_id = new_msg.id
        
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
            # Intentar responder a la interacción incluso si el lobby no existe
            try:
                 await interaction.response.send_message(
                     "❌ Este lobby ya no existe o está corrupto.", 
                     ephemeral=True
                 )
            except discord.InteractionResponded:
                 # Si ya se respondió (p.ej., por otro error), simplemente loguear
                 log.warning(f"Intento de responder a interacción ya respondida en canal {interaction.channel_id} sin lobby.")
            return

        # 2. Validar que el usuario está en el lobby (excepto para 'Leave' e 'Invite Info')
        player = lobby.get_player(interaction.user.id)
        # Invite Info lo puede usar el host aunque no sea jugador (improbable pero seguro)
        is_allowed_non_player = self.custom_id in ["imp:leave", "imp:invite_info"]
        
        if not player and not is_allowed_non_player:
            return await interaction.response.send_message(
                "❌ No eres parte de este lobby.", ephemeral=True
            )
            
        # 3. Manejar según el custom_id
        try:
            handler = _BUTTON_HANDLERS.get(self.custom_id)
            if handler:
                # Llamamos al handler específico (definidos abajo)
                # Pasar player=None si no es jugador (solo para invite_info/leave)
                await handler(interaction, bot, lobby, player if player else None)
            else:
                await interaction.response.send_message("Botón no implementado.", ephemeral=True)
        
        except discord.InteractionResponded:
             log.warning(f"Intento de responder a interacción ya respondida para botón {self.custom_id} por {interaction.user.name}")
        except Exception as e:
            log.exception(f"Error procesando botón {self.custom_id} por {interaction.user.name}: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Ocurrió un error inesperado.", ephemeral=True)
        
        # 4. Encolar actualización de HUD (si la partida no ha empezado y el lobby aún existe)
        # Verificar si el lobby todavía existe después del handler
        if core.get_lobby_by_channel(lobby.channel_id):
            touch_lobby_activity(lobby)
            if not lobby.in_progress:
                await queue_hud_update(lobby.channel_id)


# --- Lógica de los Botones ---

async def _handle_ready(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    if not player: # Añadido por seguridad, aunque no debería pasar por el check del callback
        return await interaction.response.send_message("Error: No se encontró tu estado de jugador.", ephemeral=True)
    if player.is_bot:
        return await interaction.response.send_message("Los bots siempre están listos.", ephemeral=True)
        
    player.ready_in_lobby = not player.ready_in_lobby
    status = "LISTO" if player.ready_in_lobby else "NO LISTO"
    await interaction.response.send_message(f"Te has marcado como **{status}**.", ephemeral=True)

async def _handle_toggle_open(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    if not player:
        return await interaction.response.send_message("Error: No se encontró tu estado de jugador.", ephemeral=True)
    if lobby.host_id != player.user_id:
        return await interaction.response.send_message("❌ Solo el host puede abrir o cerrar el lobby.", ephemeral=True)
        
    lobby.is_open = not lobby.is_open
    status = "ABIERTO" if lobby.is_open else "CERRADO"
    
    await interaction.response.send_message(f"El lobby ahora está **{status}**.", ephemeral=True)
    await feed.update_feed(bot) # Actualizar cartelera

async def _handle_add_bot(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    # 'player' puede ser None si es un admin usando el botón sin ser jugador
    if not await _can_use_admin_commands(interaction):
        return await interaction.response.send_message("❌ Solo el host o un admin pueden añadir bots.", ephemeral=True)

    if lobby.all_players_count >= lobby.max_slots:
        return await interaction.response.send_message("❌ El lobby está lleno.", ephemeral=True)

    # Lógica de bots.py
    cog = bot.get_cog("ImpostorBots")
    if not cog:
        return await interaction.response.send_message("Error: Módulo de Bots no cargado.", ephemeral=True)
        
    bot_name = await cog.add_bot_logic(lobby)
    if bot_name: # Asegurarse que se añadió
        _after_roster_change(lobby)
        await interaction.response.send_message(f"🤖 Bot `{bot_name}` añadido.", ephemeral=True)
        await feed.update_feed(bot)
    else: # Si no se añadió
        await interaction.response.send_message("❌ No se pudo añadir el bot (¿lobby lleno?).", ephemeral=True)


async def _handle_remove_bot(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    # 'player' puede ser None si es un admin
    if not await _can_use_admin_commands(interaction):
        return await interaction.response.send_message("❌ Solo el host o un admin pueden quitar bots.", ephemeral=True)

    if not lobby.bot_players:
        return await interaction.response.send_message("❌ No hay bots para quitar.", ephemeral=True)

    # Lógica de bots.py
    cog = bot.get_cog("ImpostorBots")
    if not cog:
        return await interaction.response.send_message("Error: Módulo de Bots no cargado.", ephemeral=True)
        
    bot_name = await cog.remove_bot_logic(lobby)
    if bot_name: # Asegurarse que se quitó
        _after_roster_change(lobby)
        await interaction.response.send_message(f"🤖 Bot `{bot_name}` eliminado.", ephemeral=True)
        await feed.update_feed(bot)
    else: # Si no se quitó
         await interaction.response.send_message("❌ No se pudo quitar el bot (¿no había?).", ephemeral=True)


def _lobby_howto_text() -> str:
    idle = get_lobby_idle_close_seconds()
    idle_note = ""
    if idle > 0:
        idle_note = f"\n• Si nadie escribe ni usa el panel por **{max(1, idle // 60)} min**, el bot cierra la sala."
    return (
        "📖 **Cómo se juega (Impostor)**\n"
        f"• Mínimo **{get_min_impo_players()}** jugadores. Host: **+ Imp** / **− Imp** (más impostores cada ~3 jugadores).\n"
        "• **Ready** → host **Comenzar** (o **Forzar inicio**). Roles: **Ver mi rol** → **Listo**.\n"
        "• Pistas: **1–5 palabras** en tu turno o `/palabra`. Votación: botones o `/votar` / `/vote`.\n"
        "• **Sociales** ganan eliminando a **todos** los impostores. **Impostores** ganan con **≤2 sociales** vivos.\n"
        "• Host: **Cerrar sala** o **Revancha** al terminar. Stats: `/impostor-stats` · `/impostor-ranking`."
        f"{idle_note}"
    )


async def _begin_match_after_countdown(
    bot: commands.Bot,
    lobby: GameState,
    channel: discord.TextChannel,
    seconds: int,
) -> None:
    sec = max(1, seconds)
    try:
        msg = await channel.send(f"▶️ **La partida arranca en {sec} segundos…**")
        for i in range(sec, 0, -1):
            if i <= 5 or i % 5 == 0:
                await msg.edit(content=f"▶️ **La partida arranca en {i} segundos…**")
            await asyncio.sleep(1)
        await msg.edit(content="🎲 **¡Repartiendo roles!**")
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass

    game_cog = bot.get_cog("ImpostorGameCore")
    if not game_cog:
        log.error("¡¡FATAL: No se pudo encontrar el Cog 'ImpostorGameCore'!!")
        lobby.in_progress = False
        lobby.phase = PHASE_IDLE
        await feed.update_feed(bot)
        await channel.send("❌ ERROR FATAL: Módulo 'game_core' no cargado.")
        return
    await game_cog.start_game(lobby)


async def _handle_start(
    interaction: discord.Interaction,
    bot: commands.Bot,
    lobby: GameState,
    player: GameState.Player,
    *,
    force: bool = False,
):
    if not player:
         return await interaction.response.send_message("❌ Solo los jugadores pueden iniciar.", ephemeral=True)
    if lobby.host_id != player.user_id:
        return await interaction.response.send_message("❌ Solo el host puede iniciar la partida.", ephemeral=True)

    min_p = get_min_impo_players()
    if lobby.all_players_count < min_p:
        return await interaction.response.send_message(
            f"❌ Se necesitan al menos **{min_p}** jugadores para empezar.", ephemeral=True
        )
    if lobby.all_players_count > lobby.max_slots:
        return await interaction.response.send_message("❌ Hay más jugadores que el cupo del lobby (error de estado).", ephemeral=True)

    if not force and not lobby.all_humans_ready_in_lobby:
        return await interaction.response.send_message("❌ No todos los humanos están listos.", ephemeral=True)
    if force and lobby.all_humans_ready_in_lobby:
        return await interaction.response.send_message("❌ Todos ya están listos; usá **Comenzar**.", ephemeral=True)
        
    if lobby.in_progress:
        return await interaction.response.send_message("❌ La partida ya ha comenzado.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return await interaction.followup.send("❌ Canal inválido.", ephemeral=True)

    lobby.in_progress = True
    lobby.phase = PHASE_ROLES
    await feed.update_feed(bot)

    from .roles import get_prestart_seconds

    asyncio.create_task(
        _begin_match_after_countdown(bot, lobby, channel, get_prestart_seconds())
    )
    note = " (inicio forzado)" if force else ""
    await interaction.followup.send(f"▶️ Cuenta regresiva antes de los roles…{note}", ephemeral=True)


async def _handle_force_start(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: GameState.Player):
    await _handle_start(interaction, bot, lobby, player, force=True)


async def _handle_impostor_count(
    interaction: discord.Interaction,
    bot: commands.Bot,
    lobby: GameState,
    player: Optional[GameState.Player],
    *,
    delta: int,
):
    if lobby.in_progress:
        return await interaction.response.send_message("❌ No se puede cambiar durante la partida.", ephemeral=True)
    if lobby.host_id != interaction.user.id:
        return await interaction.response.send_message("❌ Solo el host puede ajustar impostores.", ephemeral=True)
    mx = rules.max_impostors_for_players(lobby.all_players_count)
    new_val = lobby.impostor_count + delta
    if new_val < 1 or new_val > mx:
        return await interaction.response.send_message(
            f"❌ Cantidad inválida. Permitido: **1** a **{mx}** con {lobby.all_players_count} jugadores.",
            ephemeral=True,
        )
    lobby.impostor_count = new_val
    await interaction.response.send_message(
        f"🕵️ Impostores en esta partida: **{lobby.impostor_count}** / **{mx}**.",
        ephemeral=True,
    )


async def _handle_imp_plus(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: Optional[GameState.Player]):
    await _handle_impostor_count(interaction, bot, lobby, player, delta=1)


async def _handle_imp_minus(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: Optional[GameState.Player]):
    await _handle_impostor_count(interaction, bot, lobby, player, delta=-1)


async def _handle_close_lobby_idle(
    interaction: discord.Interaction,
    bot: commands.Bot,
    lobby: GameState,
    player: Optional[GameState.Player],
):
    if lobby.in_progress:
        return await interaction.response.send_message(
            "❌ La partida ya empezó. Al terminar, el host puede **Cerrar sala**.",
            ephemeral=True,
        )
    if lobby.host_id != interaction.user.id:
        return await interaction.response.send_message("❌ Solo el **host** puede cerrar la sala.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    lobby_name = lobby.lobby_name
    lobby_cid = lobby.channel_id
    ok = await close_lobby_channel(bot, lobby, reason=f"Host {interaction.user.id} cerró el lobby")
    if ok:
        try:
            from .activity import post_staff_log

            idle_embed = discord.Embed(
                title="Impostor — sala cerrada (host, lobby)",
                description=f"Host <@{interaction.user.id}> cerró el lobby antes de jugar.",
                color=discord.Color.dark_grey(),
            )
            idle_embed.add_field(name="Sala", value=lobby_name, inline=True)
            idle_embed.add_field(name="Canal", value=f"<#{lobby_cid}>", inline=True)
            await post_staff_log(bot, idle_embed)
        except Exception as e:
            log.warning("staff log cierre lobby idle: %s", e)
        await interaction.followup.send("Sala cerrada.", ephemeral=True)
    else:
        await interaction.followup.send(
            "No pude borrar el canal (permisos). Probá de nuevo o avisá al staff.",
            ephemeral=True,
        )


async def _handle_leave(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: Optional[GameState.Player]):
    # 'player' es None si el usuario ya no estaba registrado
    block = leave_block_reason(lobby, interaction.user.id)
    if block:
        return await interaction.response.send_message(block, ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    lobby_cog = bot.get_cog("ImpostorLobby")
    if lobby_cog:
        ok = await lobby_cog.handle_leave_logic(interaction.user, lobby)
        if not ok:
            return await interaction.followup.send("No pudiste salir del lobby.", ephemeral=True)
        await interaction.followup.send("Has abandonado el lobby.", ephemeral=True)
    else:
        log.error("No se pudo encontrar el Cog 'ImpostorLobby' para manejar la salida.")
        await interaction.followup.send("❌ Error interno al intentar salir.", ephemeral=True)

# --- Handler para el nuevo botón ---
async def _handle_invite_info(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: Optional[GameState.Player]):
    """Muestra información sobre cómo invitar."""
    # Permitir al host usarlo, incluso si 'player' es None (caso borde improbable)
    is_host = lobby.host_id == interaction.user.id
    
    if not is_host:
        # Si no es host, verificar si es admin (por si un admin pulsa el botón)
        is_admin = await _can_use_admin_commands(interaction)
        if not is_admin:
            return await interaction.response.send_message(
                 "❌ Solo el host puede ver la información de invitación.", 
                 ephemeral=True
             )
        # Si es admin pero no host, mostrarle igual la info

    if lobby.all_players_count >= lobby.max_slots:
         return await interaction.response.send_message(
            "❌ El lobby ya está lleno.", 
            ephemeral=True
        )

    await interaction.response.send_message(
        f"ℹ️ **Cómo Invitar (Host):**\n"
        f"Usa el comando `/invitar` mencionando al usuario:\n"
        f"```\n"
        f"/invitar usuario: @NombreDeUsuario\n"
        f"```\n"
        f"(Escríbelo aquí, en <#{lobby.channel_id}>)",
        ephemeral=True
    )
# --- Fin del nuevo handler ---


async def _handle_notify_ping(interaction: discord.Interaction, bot: commands.Bot, lobby: GameState, player: Optional[GameState.Player]):
    if not player:
        return await interaction.response.send_message("❌ Solo quien está en el lobby puede usar esto.", ephemeral=True)
    if lobby.host_id != interaction.user.id:
        return await interaction.response.send_message("❌ Solo el host puede avisar al rol de Impostor.", ephemeral=True)
    if lobby.in_progress:
        return await interaction.response.send_message("❌ No aplica con la partida en curso.", ephemeral=True)

    remaining = impostor_notify.lobby_ping_cooldown_remaining(lobby.channel_id)
    if remaining > 0:
        return await interaction.response.send_message(
            f"❌ Esperá **{remaining:.1f}s** antes de volver a mencionar al rol.",
            ephemeral=True,
        )

    guild = interaction.guild
    if not guild:
        return await interaction.response.send_message("❌ Solo en un servidor.", ephemeral=True)

    role = guild.get_role(impostor_notify.get_notify_role_id())
    if not role:
        return await interaction.response.send_message(
            "❌ No existe el rol de avisos en este servidor (revisá `IMPOSTOR_NOTIFY_ROLE_ID`).",
            ephemeral=True,
        )

    ping_ch_id = impostor_notify.get_notify_ping_broadcast_channel_id() or lobby.channel_id
    channel = bot.get_channel(ping_ch_id)
    if not isinstance(channel, discord.TextChannel):
        return await interaction.response.send_message(
            "❌ No encontré el canal para el aviso (lobby o `IMPOSTOR_NOTIFY_PING_CHANNEL_ID`).",
            ephemeral=True,
        )

    await interaction.response.defer(ephemeral=True)
    try:
        await channel.send(
            f"{role.mention} — **{interaction.user.display_name}** busca jugadores para **Impostor** "
            f"en **{lobby.lobby_name}**.\n"
            f"Entrá con `/entrar nombre:{lobby.lobby_name}` o mirá la cartelera."
        )
        impostor_notify.register_lobby_ping(lobby.channel_id)
        await interaction.followup.send("✅ Mención enviada.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ No tengo permiso para mencionar ese rol o enviar en el canal.", ephemeral=True
        )
    except discord.HTTPException as e:
        log.warning("Error al enviar ping de Impostor: %s", e)
        await interaction.followup.send("❌ No pude enviar el aviso.", ephemeral=True)


# Mapa de Handlers para los botones
_BUTTON_HANDLERS = {
    "imp:ready": _handle_ready,
    "imp:toggle_open": _handle_toggle_open,
    "imp:addbot": _handle_add_bot,
    "imp:removebot": _handle_remove_bot,
    "imp:start": _handle_start,
    "imp:force_start": _handle_force_start,
    "imp:imp_plus": _handle_imp_plus,
    "imp:imp_minus": _handle_imp_minus,
    "imp:close_lobby_idle": _handle_close_lobby_idle,
    "imp:notify_ping": _handle_notify_ping,
    "imp:leave": _handle_leave,
    "imp:invite_info": _handle_invite_info, # <-- Registrado
}


# --- Cog: Comandos y Tareas ---
class ImpostorLobbyCog(commands.Cog, name="ImpostorLobby"):
    """
    Gestiona la creación, unión y panel de control (HUD) de los lobbies.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hud_updater_task.start()
        self.idle_sweeper_task.start()

    def cog_unload(self):
        self.hud_updater_task.cancel()
        self.idle_sweeper_task.cancel()

    @tasks.loop(seconds=get_hud_update_interval())
    async def hud_updater_task(self):
        """Tarea periódica que actualiza los HUDs."""
        try:
            await _process_hud_updates(self.bot)
        except Exception as e:
            log.exception(f"Error en el loop hud_updater_task: {e}")

    @hud_updater_task.before_loop
    async def before_hud_updater(self):
        await self.bot.wait_until_ready()
        log.info(f"Iniciando loop de actualización de HUD (Intervalo: {get_hud_update_interval()}s)")

    @tasks.loop(seconds=45)
    async def idle_sweeper_task(self):
        try:
            n = await sweep_idle_lobbies(self.bot)
            if n:
                log.info("Idle sweeper: %s lobby(s) cerrados.", n)
        except Exception:
            log.exception("idle_sweeper_task")

    @idle_sweeper_task.before_loop
    async def before_idle_sweeper(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        lobby = core.get_lobby_by_channel(message.channel.id)
        if not lobby or lobby.in_progress:
            return
        if lobby.phase != PHASE_IDLE:
            return
        touch_lobby_activity(lobby)

    # --- Lógica de Salida ---
    async def handle_leave_logic(
        self,
        user: discord.Member,
        lobby: Optional[GameState] = None,
        *,
        force: bool = False,
    ) -> bool:
        """Lógica centralizada para que un usuario abandone un lobby. Devuelve True si salió."""
        if not lobby:
            lobby = core.get_lobby_by_user(user.id)

        if not lobby:
            log.debug(f"{user.name} intentó salir pero no estaba en ningún lobby.")
            return False

        block = leave_block_reason(lobby, user.id, force=force)
        if block:
            log.debug("%s bloqueado al salir: %s", user.name, block)
            return False

        lobby_channel_id = lobby.channel_id 
        lobby_name = lobby.lobby_name     

        # 1. Quitar al usuario del registro
        core.remove_user_from_lobby(user.id)
        log.info(f"{user.name} ha salido del lobby {lobby_name} (C:{lobby_channel_id})")

        # Intentar quitar permisos
        try:
            channel = await self.bot.fetch_channel(lobby_channel_id)
            if isinstance(channel, discord.TextChannel):
                 await channel.set_permissions(user, overwrite=None) 
        except (discord.NotFound, discord.Forbidden):
             pass 

        # 2. Comprobar estado del lobby post-salida
        lobby = core.get_lobby_by_channel(lobby_channel_id) 
        if not lobby:
             log.info(f"Lobby C:{lobby_channel_id} eliminado durante salida de {user.name}.")
             await feed.update_feed(self.bot)
             return True

        remaining_humans = lobby.human_players
        should_delete_channel = False
        new_host_id = None
        
        if lobby.host_id == user.id:
            log.info(f"Host {user.name} abandonó {lobby_name}. Transfiriendo...")
            if remaining_humans:
                new_host_id = remaining_humans[0].user_id
                lobby.host_id = new_host_id
                log.info(f"Nuevo host para C:{lobby_channel_id}: {new_host_id}")
            else:
                log.info(f"No quedan humanos C:{lobby_channel_id}. Marcado para borrado.")
                should_delete_channel = True
        
        if not remaining_humans and not should_delete_channel:
             log.info(f"No quedan humanos C:{lobby_channel_id}. Marcado para borrado.")
             should_delete_channel = True

        # 3. Borrar si necesario
        channel_deleted = False
        if should_delete_channel:
            log.info(f"Borrando canal C:{lobby_channel_id}...")
            channel_deleted = await close_lobby_channel(
                self.bot, lobby, reason="Lobby Impostor vacío"
            )
            if not channel_deleted:
                log.error(f"Sin permisos para borrar C:{lobby_channel_id}")
        
        # 4. Actualizar feed SIEMPRE
        await feed.update_feed(self.bot)
        
        # 5. Notificar o actualizar HUD
        if not channel_deleted:
            lobby = core.get_lobby_by_channel(lobby_channel_id)
            if lobby:
                _after_roster_change(lobby)
            if new_host_id:
                 try:
                     channel = await self.bot.fetch_channel(lobby_channel_id)
                     await channel.send(
                         f"👑 <@{user.id}> ha abandonado. Nuevo host: <@{new_host_id}>.\n"
                         f"El nuevo host puede **Cerrar sala** o seguir jugando."
                     )
                 except (discord.NotFound, discord.Forbidden):
                     pass 
            await queue_hud_update(lobby_channel_id)

        return True


    # --- Crear / unirse / salir (slash y prefijo `?`) ---

    async def service_create_lobby(
        self,
        guild: discord.Guild,
        member: discord.Member,
        nombre: str,
        *,
        is_open: bool,
        jugadores: Optional[int] = None,
    ) -> tuple[bool, str]:
        min_p = get_min_impo_players()
        ceiling = get_global_slot_ceiling()
        cupo = jugadores if jugadores is not None else get_default_lobby_slots()
        if cupo < min_p or cupo > ceiling:
            cap_hint = (
                f"**{ceiling}**"
                if ceiling < UNLIMITED_SLOTS
                else "**sin tope** (poné cupo si querés un límite menor)"
            )
            return False, f"❌ El cupo debe ser al menos **{min_p}** y como máximo {cap_hint}."

        if core.get_lobby_by_user(member.id):
            return False, "❌ Ya estás en un lobby. Usá `/leave` o `?salir`."

        category_id = get_category_id()
        if not category_id:
            log.error("IMPOSTOR_CATEGORY_ID no configurado.")
            return False, "❌ Error config: Falta ID categoría."

        category = guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            log.error("Categoría ID %s no encontrada o inválida.", category_id)
            return False, "❌ Error config: Categoría inválida."

        channel_name = _slugify(nombre)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_messages=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
            ),
        }

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Lobby Impostor: {nombre} | Host: {member.name}",
            )
        except discord.Forbidden:
            log.error("Sin permisos crear canal en %s", category.name)
            return False, "❌ Error: Sin permisos para crear canal."
        except Exception as e:
            log.exception("Error al crear canal: %s", e)
            return False, "❌ Error inesperado al crear canal."

        lobby = core.create_lobby(
            guild_id=guild.id,
            channel_id=channel.id,
            host_id=member.id,
            lobby_name=nombre,
            is_open=is_open,
            max_slots=cupo,
        )

        try:
            embed = _generate_lobby_embed(lobby, self.bot.user)
            view = _generate_lobby_view(lobby)
            msg = await channel.send(embed=embed, view=view)
            lobby.hud_message_id = msg.id
            await channel.send(_lobby_howto_text())
        except Exception as e:
            log.exception("Error al publicar HUD en C:%s: %s", channel.id, e)

        await feed.update_feed(self.bot)

        try:
            flag = (os.getenv("IMPOSTOR_ANNOUNCE_GENERAL", "1") or "").strip().lower()
            if flag not in {"0", "false", "no", "off"}:
                gen_id = int(os.getenv("GENERAL_CHANNEL_ID", "0") or 0)
                if gen_id:
                    gen_ch = guild.get_channel(gen_id)
                    if gen_ch and isinstance(gen_ch, discord.abc.Messageable):
                        tipo_txt = "**abierto**" if is_open else "**cerrado (solo invitación del host)**"
                        await gen_ch.send(
                            f"🎭 **Nueva sala Impostor** — **{discord.utils.escape_markdown(nombre)}** ({tipo_txt}).\n"
                            f"**Canal:** {channel.mention}\n"
                            f"**Host:** {member.mention}\n"
                            f"**Cómo entrar:** `/entrar` o `?entrar` con el nombre del lobby"
                            f"{' (si está abierto)' if is_open else ' (el host te tiene que dar acceso al canal)'}"
                            f". También podés ver lobbies en el feed de Impostor."
                        )
        except Exception as e:
            log.warning("No se pudo publicar el aviso de Impostor en #general: %s", e)

        return True, f"✅ Lobby **{nombre}** creado: {channel.mention}"

    async def service_join_lobby(
        self, guild: discord.Guild, member: discord.Member, nombre: str
    ) -> tuple[bool, str]:
        if core.get_lobby_by_user(member.id):
            return False, "❌ Ya estás en un lobby. Usá `/leave` o `?salir`."

        target_lobby: Optional[GameState] = None
        lobby_name_lower = nombre.lower()
        for lobby in core.get_all_lobbies():
            if lobby.lobby_name.lower() == lobby_name_lower:
                target_lobby = lobby
                break

        if not target_lobby:
            return False, f"❌ No encontré lobby abierto **{nombre}**."
        if not target_lobby.is_open:
            return False, f"❌ Lobby **{nombre}** está cerrado."
        if target_lobby.in_progress:
            return False, f"❌ Partida en **{nombre}** ya empezó."
        if target_lobby.all_players_count >= target_lobby.max_slots:
            return False, f"❌ Lobby **{nombre}** está lleno."

        channel = guild.get_channel(target_lobby.channel_id)
        if not channel:
            core.remove_lobby(target_lobby.channel_id)
            await feed.update_feed(self.bot)
            return False, "❌ Error: Canal del lobby no existe."

        try:
            await channel.set_permissions(member, read_messages=True, send_messages=True)
        except discord.Forbidden:
            return False, "❌ Error: Sin permisos para añadirte al canal."

        lobby_joined = core.add_user_to_lobby(member.id, target_lobby.channel_id)
        if not lobby_joined:
            try:
                await channel.set_permissions(member, overwrite=None)
            except Exception:
                pass
            return False, "❌ Error al unirte al estado del lobby."

        _after_roster_change(target_lobby)
        await feed.update_feed(self.bot)
        await queue_hud_update(target_lobby.channel_id)
        try:
            await channel.send(f"👋 ¡{member.mention} se unió!")
        except discord.HTTPException:
            pass
        return True, f"✅ Te uniste a **{nombre}**: <#{target_lobby.channel_id}>"

    async def service_leave_lobby(self, member: discord.Member) -> tuple[bool, str]:
        lobby = core.get_lobby_by_user(member.id)
        if not lobby:
            return False, "❌ No estás en ningún lobby."

        if lobby.in_progress and lobby.phase != PHASE_END:
            return False, "❌ No podés salir con la partida en curso."

        block = leave_block_reason(lobby, member.id)
        if block:
            return False, block

        lobby_name = lobby.lobby_name
        ok = await self.handle_leave_logic(member, lobby)
        if not ok:
            return False, "❌ No pudiste salir del lobby."
        return True, f"Abandonaste **{lobby_name}**."

    # --- Comandos Slash ---

    @app_commands.command(name="crearsimpostor", description="Crea un nuevo lobby para el juego Impostor.")
    @app_commands.describe(
        nombre="Nombre para tu lobby (ej: 'Pros Only')",
        jugadores="Opcional: cupo máximo (humanos+bots). Si lo omitís, se usa el cupo por defecto del servidor.",
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Abierto (Cualquiera puede unirse)", value="abierto"),
        app_commands.Choice(name="Cerrado (Solo con invitación)", value="cerrado") # Re-habilitado
    ])
    async def crearsimpostor(
        self,
        interaction: discord.Interaction,
        nombre: str,
        tipo: app_commands.Choice[str],
        jugadores: Optional[int] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("❌ Solo en servidor.", ephemeral=True)
        is_open = tipo.value == "abierto"
        ok, msg = await self.service_create_lobby(
            interaction.guild,
            interaction.user,
            nombre,
            is_open=is_open,
            jugadores=jugadores,
        )
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="entrar", description="Únete a un lobby de Impostor abierto.")
    @app_commands.describe(nombre="El nombre exacto del lobby al que quieres unirte.")
    async def entrar(self, interaction: discord.Interaction, nombre: str):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("❌ Solo en servidor.", ephemeral=True)
        ok, msg = await self.service_join_lobby(interaction.guild, interaction.user, nombre)
        await interaction.followup.send(msg, ephemeral=True)


    @app_commands.command(name="leave", description="Abandona el lobby de Impostor en el que te encuentras.")
    async def leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ok, msg = await self.service_leave_lobby(interaction.user)
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="salir", description="Abandona el lobby de Impostor en el que te encuentras.")
    async def salir(self, interaction: discord.Interaction):
        await self.leave.callback(self, interaction)

    @app_commands.command(name="invitar", description="[Host] Invita a un jugador a tu lobby actual.")
    @app_commands.describe(usuario="El jugador que quieres invitar.")
    async def invitar(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer(ephemeral=True)
        lobby = core.get_lobby_by_channel(interaction.channel_id)

        if not lobby: return await interaction.followup.send("❌ Solo en un canal de lobby.", ephemeral=True)
        if lobby.host_id != interaction.user.id: return await interaction.followup.send("❌ Solo el host invita.", ephemeral=True)
        if lobby.in_progress: return await interaction.followup.send("❌ Partida ya empezó.", ephemeral=True)
        if core.get_lobby_by_user(usuario.id): return await interaction.followup.send(f"❌ {usuario.display_name} ya está en otro lobby.", ephemeral=True)
        
        if lobby.all_players_count >= lobby.max_slots:
            return await interaction.followup.send("❌ Lobby lleno.", ephemeral=True)
        if usuario.id == self.bot.user.id or usuario.bot: return await interaction.followup.send("❌ No puedes invitar bots.", ephemeral=True)
        if lobby.get_player(usuario.id): return await interaction.followup.send(f"❌ {usuario.display_name} ya está aquí.", ephemeral=True)

        channel = interaction.channel
        try:
            await channel.set_permissions(usuario, read_messages=True, send_messages=True)
        except discord.Forbidden: return await interaction.followup.send("❌ Error: Sin permisos para añadir.", ephemeral=True)
        except Exception as e:
            log.exception(f"Error al invitar {usuario.id} en C:{channel.id}: {e}")
            return await interaction.followup.send("❌ Error inesperado al dar permisos.", ephemeral=True)
            
        core.add_user_to_lobby(usuario.id, lobby.channel_id)
        _after_roster_change(lobby)
        await feed.update_feed(self.bot)
        await queue_hud_update(lobby.channel_id)
        await interaction.followup.send(f"✅ Invitaste a {usuario.mention}.", ephemeral=True)
        await channel.send(f"👋 ¡Bienvenido/a {usuario.mention}! Invitado por el host.")

    @app_commands.command(name="ready", description="Marca tu estado como Listo/No Listo en el lobby.")
    async def ready_command(self, interaction: discord.Interaction):
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby: return await interaction.response.send_message("❌ Solo en un canal de lobby.", ephemeral=True)
        player = lobby.get_player(interaction.user.id)
        if not player or player.is_bot: return await interaction.response.send_message("❌ No eres un jugador humano aquí.", ephemeral=True)
        await _handle_ready(interaction, self.bot, lobby, player)
        await queue_hud_update(lobby.channel_id) 

    @app_commands.command(name="listo", description="(Alias) Marca tu estado como Listo/No Listo en el lobby.")
    async def listo(self, interaction: discord.Interaction):
        await self.ready_command.callback(self, interaction)

    @app_commands.command(name="abrirlobby", description="[Host] Abre tu lobby actual.")
    async def abrirlobby(self, interaction: discord.Interaction):
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby or lobby.host_id != interaction.user.id: return await interaction.response.send_message("❌ Solo el host en su lobby.", ephemeral=True)
        if lobby.in_progress: return await interaction.response.send_message("❌ No durante la partida.", ephemeral=True)
        if lobby.is_open: return await interaction.response.send_message("Ya estaba abierto.", ephemeral=True)
        lobby.is_open = True
        await interaction.response.send_message("Lobby **ABIERTO**.", ephemeral=True)
        await feed.update_feed(self.bot)
        await queue_hud_update(lobby.channel_id)
        
    @app_commands.command(name="cerrarlobby", description="[Host] Cierra tu lobby actual.")
    async def cerrarlobby(self, interaction: discord.Interaction):
        lobby = core.get_lobby_by_channel(interaction.channel_id)
        if not lobby or lobby.host_id != interaction.user.id: return await interaction.response.send_message("❌ Solo el host en su lobby.", ephemeral=True)
        if lobby.in_progress: return await interaction.response.send_message("❌ No durante la partida.", ephemeral=True)
        if not lobby.is_open: return await interaction.response.send_message("Ya estaba cerrado.", ephemeral=True)
        lobby.is_open = False
        await interaction.response.send_message("Lobby **CERRADO**.", ephemeral=True)
        await feed.update_feed(self.bot)
        await queue_hud_update(lobby.channel_id)

    # --- Prefijo `?` (cartelera, feed, #general — fuera del canal de lobby) ---

    @staticmethod
    def _parse_open_flag(token: str) -> Optional[bool]:
        t = (token or "").strip().lower()
        if t in ("abierto", "open", "publico", "público", "a"):
            return True
        if t in ("cerrado", "closed", "privado", "c"):
            return False
        return None

    @commands.command(
        name="crearsimpostor",
        aliases=["crearimpostor", "nuevolobby", "crearlobby"],
    )
    async def crearsimpostor_prefix(self, ctx: commands.Context, *, args: str = ""):
        """`?crearsimpostor Nombre [abierto|cerrado] [cupo]` — crear sala (desde feed/general)."""
        if not ctx.guild:
            return
        from .zone import is_impostor_lobby_channel

        if is_impostor_lobby_channel(ctx.channel.id):
            await ctx.send(
                "Creá la sala desde la **cartelera**, **#general** o el **canal del bot**, no desde un lobby en curso.",
                delete_after=10,
            )
            return

        parts = (args or "").strip().split()
        if not parts:
            await ctx.send(
                "Uso: **`?crearsimpostor <nombre>`** · opcional: `abierto`/`cerrado` · cupo numérico.\n"
                "Ej.: `?crearsimpostor Pros Only abierto 8`"
            )
            return

        is_open = True
        jugadores: Optional[int] = None
        name_parts: List[str] = []

        for p in parts:
            flag = self._parse_open_flag(p)
            if flag is not None:
                is_open = flag
                continue
            if p.isdigit():
                jugadores = int(p)
                continue
            name_parts.append(p)

        nombre = " ".join(name_parts).strip()
        if not nombre:
            await ctx.send("Falta el **nombre** del lobby.")
            return

        ok, msg = await self.service_create_lobby(
            ctx.guild, ctx.author, nombre, is_open=is_open, jugadores=jugadores
        )
        await ctx.send(msg)

    @commands.command(name="entrar", aliases=["unirme", "joinimpostor", "entrarimpostor"])
    async def entrar_prefix(self, ctx: commands.Context, *, nombre: str = ""):
        """`?entrar <nombre exacto del lobby>` — unirse a sala abierta."""
        if not ctx.guild:
            return
        from .zone import is_impostor_lobby_channel

        if is_impostor_lobby_channel(ctx.channel.id):
            await ctx.send("Usá `?entrar` desde **fuera** del canal de lobby (cartelera o #general).", delete_after=10)
            return
        nombre = (nombre or "").strip()
        if not nombre:
            await ctx.send("Uso: **`?entrar <nombre del lobby>`** (mismo nombre que en la cartelera).")
            return
        ok, msg = await self.service_join_lobby(ctx.guild, ctx.author, nombre)
        await ctx.send(msg)

    @commands.command(name="leave", aliases=["salir", "salirimpostor", "abandonar"])
    async def leave_prefix(self, ctx: commands.Context):
        """Abandonar el lobby en el que estés (`?salir` / `?leave`)."""
        ok, msg = await self.service_leave_lobby(ctx.author)
        await ctx.send(msg)


# --- Setup del Cog ---
async def setup(bot: commands.Bot):
    await bot.add_cog(ImpostorLobbyCog(bot))