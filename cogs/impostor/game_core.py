# cogs/impostor/game_core.py
import os
import time
import asyncio
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import discord

from .core import manager, MAX_PLAYERS

# === Configs de tiempos ===
PREPARE_SEC = int(os.getenv("IMPOSTOR_PREPARE_SEC", "10"))          # countdown antes de Ronda 1
TURN_SECONDS = int(os.getenv("IMPOSTOR_TURN_SECONDS", "45"))         # por jugador para pista
VOTE_SECONDS = int(os.getenv("IMPOSTOR_VOTE_SECONDS", "180"))        # ventana de votación
HUD_TICK = max(1, int(os.getenv("IMPOSTOR_HUD_TICK", "5")))          # refresco de HUD
MAX_ROUNDS = int(os.getenv("IMPOSTOR_MAX_ROUNDS", "6"))              # seguridad

IMPOSTOR_SOUND_URL = os.getenv("IMPOSTOR_SOUND_URL", "").strip()
SOCIAL_SOUND_URL = os.getenv("SOCIAL_SOUND_URL", "").strip()

# ---------------------------------------------------------------------

@dataclass
class GPlayer:
    user_id: int
    alive: bool = True
    role: Optional[str] = None         # "IMPOSTOR" | "SOCIAL"
    clue: Optional[str] = None
    afk_this_round: bool = False
    vote_target: Optional[int] = None

@dataclass
class GameState:
    lobby_name: str
    guild_id: int
    channel_id: int
    in_progress: bool = False
    round_no: int = 0
    impostor_id: Optional[int] = None
    word: Optional[str] = None
    link: Optional[str] = None
    players: Dict[int, GPlayer] = field(default_factory=dict)
    order: List[int] = field(default_factory=list)         # orden de turnos (IDs)
    hud_msg_id: Optional[int] = None
    votes_open: bool = False
    clues_phase: bool = False

# estado por (guild_id, lobby_name)
_games: Dict[Tuple[int, str], GameState] = {}

def get_game(guild_id: int, lobby_name: str) -> Optional[GameState]:
    return _games.get((guild_id, lobby_name))

def del_game(guild_id: int, lobby_name: str):
    _games.pop((guild_id, lobby_name), None)

# ---------------------------------------------------------------------

async def _channel(guild: discord.Guild, channel_id: int) -> Optional[discord.TextChannel]:
    ch = guild.get_channel(channel_id)
    return ch if isinstance(ch, discord.TextChannel) else None

def _alive(gs: GameState) -> List[int]:
    return [uid for uid, gp in gs.players.items() if gp.alive]

def _is_bot_sim(guild_id: int, lobby_name: str, uid: int) -> bool:
    lob = manager.get(guild_id, lobby_name)
    if not lob:
        return False
    p = lob.players.get(uid)
    return bool(p and p.is_bot_sim)

# ---------------------------------------------------------------------

async def start_game(guild: discord.Guild, lobby_name: str) -> Optional[GameState]:
    """Crea el estado de juego y dispara el kickoff (con try/except robusto)."""
    lob = manager.get(guild.id, lobby_name)
    if not lob or not lob.channel_id:
        return None

    # import local para evitar ciclos
    from . import chars
    await chars.ensure_cache()

    gs = GameState(lobby_name=lob.name, guild_id=guild.id, channel_id=lob.channel_id)

    alive_ids = list(lob.players.keys())
    if len(alive_ids) != MAX_PLAYERS:
        return None

    # Impostor + palabra
    gs.impostor_id = random.choice(alive_ids)
    name, slug = chars.pick_random()
    gs.word, gs.link = name, chars.to_link(slug)

    # jugadores y orden inicial random
    for uid in alive_ids:
        role = "IMPOSTOR" if uid == gs.impostor_id else "SOCIAL"
        gs.players[uid] = GPlayer(user_id=uid, role=role, alive=True)
    gs.order = random.sample(alive_ids, k=len(alive_ids))

    _games[(guild.id, lob.name)] = gs

    # marcar lobby en partida y refrescar panel sin bot
    lob.in_game = True
    try:
        from .ui import update_panel
        await update_panel(None, guild, lob)
    except Exception:
        pass

    try:
        await kickoff_game(guild, gs)
    except Exception as e:
        # si algo explota en el kickoff, volvemos lobby.in_game = False
        lob.in_game = False
        try:
            from .ui import update_panel
            await update_panel(None, guild, lob)
        except Exception:
            pass
        ch = await _channel(guild, gs.channel_id)
        if ch:
            await ch.send(f"⚠️ Ocurrió un error al iniciar la partida: `{type(e).__name__}`. Cancelado.")
        del_game(guild.id, lob.name)
        return None

    return gs

# ---------------------------------------------------------------------

async def kickoff_game(guild: discord.Guild, gs: GameState):
    """Muestra rol (solo a cada jugador), muestra orden y hace countdown de PREPARE_SEC."""
    ch = await _channel(guild, gs.channel_id)
    if not ch:
        return

    # Mensaje de "Roles entregados / botón Ver mi rol"
    # Vamos a usar un Button que muestre embed efímero (sólo al usuario)
    class VerRolView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=PREPARE_SEC + 30)

        @discord.ui.button(label="Ver mi rol", style=discord.ButtonStyle.primary)
        async def ver(self, interaction: discord.Interaction, btn: discord.ui.Button):
            uid = interaction.user.id
            gp = gs.players.get(uid)
            if not gp:
                return await interaction.response.send_message("No estás en la partida.", ephemeral=True)
            emb = discord.Embed(
                title="Tu rol en IMPOSITOR",
                color=discord.Color.red() if gp.role == "IMPOSTOR" else discord.Color.green()
            )
            emb.add_field(name="Rol", value=gp.role or "—", inline=False)
            if gp.role == "SOCIAL":
                emb.add_field(name="Personaje / Palabra", value=gs.word or "—", inline=False)
                if gs.link:
                    emb.add_field(name="Info", value=gs.link, inline=False)
                if SOCIAL_SOUND_URL:
                    emb.set_footer(text="Consejo: Da pista sin decir la palabra.")
                view = None
                if SOCIAL_SOUND_URL:
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(label="🔊 Sonidito SOCIAL", style=discord.ButtonStyle.link, url=SOCIAL_SOUND_URL))
                await interaction.response.send_message(embed=emb, view=view, ephemeral=True)
            else:
                emb.set_footer(text="Sos el impostor. Disimulá y no cantes bingo!")
                view = None
                if IMPOSTOR_SOUND_URL:
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(label="🔊 Sonidito IMPOSTOR", style=discord.ButtonStyle.link, url=IMPOSTOR_SOUND_URL))
                await interaction.response.send_message(embed=emb, view=view, ephemeral=True)

    await ch.send("📨 **Roles entregados de forma privada.** Tocá **Ver mi rol** si necesitás revisarlo.", view=VerRolView())

    # Orden visible
    mention_order = []
    for i, uid in enumerate(gs.order, start=1):
        botflag = " 🤖" if _is_bot_sim(gs.guild_id, gs.lobby_name, uid) else ""
        mention_order.append(f"{i}. <@{uid}>{botflag}")
    await ch.send("🟢 **¡Comienza la Ronda 1!**\n**Orden de turnos:**\n" + "\n".join(mention_order))

    # Countdown
    prep = PREPARE_SEC
    msg = await ch.send(f"⏳ La partida comienza en **{prep}s**…")
    while prep > 0:
        await asyncio.sleep(min(5, prep))
        prep -= min(5, prep)
        try:
            await msg.edit(content=f"⏳ La partida comienza en **{prep}s**…")
        except Exception:
            pass

    gs.in_progress = True
    gs.round_no = 1
    await open_clues_phase(guild, gs)

# ---------------------------------------------------------------------

async def _hud(guild: discord.Guild, gs: GameState, *, voting: bool = False, seconds_left: Optional[int] = None):
    ch = await _channel(guild, gs.channel_id)
    if not ch:
        return
    lines = [f"**Ronda {gs.round_no}** — Vivos: {len(_alive(gs))}"]
    if voting:
        lines.append("**Votación abierta** — Usá los botones o `/votar @jugador`.")
    else:
        lines.append("**Fase de PISTAS** — usa `/palabra <tu pista>` (1–5 palabras).")

    if seconds_left is not None:
        lines.append(f"⏳ Tiempo restante: **{seconds_left}s** (actualiza cada {HUD_TICK}s)")

    content = "\n".join(lines)
    try:
        if gs.hud_msg_id:
            msg = await ch.fetch_message(gs.hud_msg_id)
            await msg.edit(content=content)
        else:
            msg = await ch.send(content)
            gs.hud_msg_id = msg.id
    except Exception:
        try:
            msg = await ch.send(content)
            gs.hud_msg_id = msg.id
        except Exception:
            pass

# ---------------------------------------------------------------------

async def open_clues_phase(guild: discord.Guild, gs: GameState):
    """Turnos secuenciales; el chat sigue abierto pero sólo se acepta /palabra del jugador activo.
       Bots dicen "kunai". Cuando todos dieron pista o se agotó su turno, pasamos a votación."""
    if not gs.in_progress:
        return
    ch = await _channel(guild, gs.channel_id)
    if not ch:
        return

    # reset por ronda
    for uid in _alive(gs):
        gp = gs.players[uid]
        gp.clue = None
        gp.afk_this_round = False
        gp.vote_target = None

    gs.clues_phase = True
    await _hud(guild, gs, voting=False, seconds_left=TURN_SECONDS * len(_alive(gs)))

    # Turnos
    for turn_uid in list(gs.order):
        if not gs.in_progress:
            return
        if not gs.players[turn_uid].alive:
            continue

        # anunciar turno
        await ch.send(f"▶️ **Turno de <@{turn_uid}>** — **{TURN_SECONDS}s**. Escribí `/palabra <tu pista>` (1–5 palabras).")

        # Si es bot sim → habla solo
        if _is_bot_sim(gs.guild_id, gs.lobby_name, turn_uid):
            await asyncio.sleep(2)
            gs.players[turn_uid].clue = "kunai"
            await ch.send(f"🤖 AAT-Bot dijo: **kunai**")
            # consumimos resto del tiempo “rápido”
            await asyncio.sleep(1)
            continue

        # Humano: esperar a que ponga /palabra
        left = TURN_SECONDS
        while left > 0 and gs.in_progress and gs.clues_phase and gs.players[turn_uid].clue is None:
            await asyncio.sleep(1)
            left -= 1

        if gs.players[turn_uid].clue is None:
            # AFK: se autovota
            gs.players[turn_uid].afk_this_round = True
            gs.players[turn_uid].clue = "(AFK)"
            gs.players[turn_uid].vote_target = turn_uid
            await ch.send(f"⏰ <@{turn_uid}> no dio su pista. Marcado **AFK** y auto-voto a sí mismo.")

    gs.clues_phase = False
    await ch.send("🛑 Pistas cerradas → **VOTACIÓN**.")
    await open_votes(guild, gs)

# ---------------------------------------------------------------------

async def open_votes(guild: discord.Guild, gs: GameState):
    if not gs.in_progress:
        return
    ch = await _channel(guild, gs.channel_id)
    if not ch:
        return

    gs.votes_open = True

    # construir botones por vivos
    class VotarView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=VOTE_SECONDS + 10)
            vivos = _alive(gs)
            for uid in vivos:
                self.add_item(VotarButton(uid))
            self.add_item(QuitarVotoButton())

    class VotarButton(discord.ui.Button):
        def __init__(self, target_uid: int):
            self.target_uid = target_uid
            label = "AAT-Bot" if self.target_uid < 0 else "Votar a "  # luego resolvemos nombre real
            super().__init__(label=label, style=discord.ButtonStyle.primary)

        async def callback(self, interaction: discord.Interaction):
            uid = interaction.user.id
            if uid not in gs.players or not gs.players[uid].alive:
                return await interaction.response.send_message("No estás vivo en esta partida.", ephemeral=True)
            tgt = self.target_uid
            if tgt not in gs.players or not gs.players[tgt].alive:
                return await interaction.response.send_message("Ese jugador no está vivo.", ephemeral=True)
            gs.players[uid].vote_target = tgt
            await interaction.response.send_message("🗳️ Voto registrado.", ephemeral=True)

    class QuitarVotoButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Quitar mi voto", style=discord.ButtonStyle.secondary)

        async def callback(self, interaction: discord.Interaction):
            uid = interaction.user.id
            if uid not in gs.players:
                return await interaction.response.send_message("No estás en esta partida.", ephemeral=True)
            gs.players[uid].vote_target = None
            await interaction.response.send_message("Voto quitado.", ephemeral=True)

    # Ajustar labels con nombres legibles
    vivos = _alive(gs)
    view = VotarView()
    for item in view.children:
        if isinstance(item, VotarButton):
            if item.target_uid < 0:
                item.label = f"Votar a AAT-Bot#{abs(item.target_uid)%1000}"
            else:
                member = guild.get_member(item.target_uid)
                item.label = f"Votar a {member.display_name if member else item.target_uid}"

    await _hud(guild, gs, voting=True, seconds_left=VOTE_SECONDS)
    await ch.send("🗳️ **Votación abierta** — Usá los **botones** o `/votar @jugador`.", view=view)

    # Bots: votan inmediatamente (a sí mismos)
    for uid in vivos:
        if _is_bot_sim(gs.guild_id, gs.lobby_name, uid):
            gs.players[uid].vote_target = uid

    # Esperar a que voten todos o timeout
    left = VOTE_SECONDS
    while left > 0 and gs.in_progress and gs.votes_open:
        if all(gs.players[uid].vote_target is not None for uid in _alive(gs)):
            break
        await asyncio.sleep(1)
        left -= 1
        if left % HUD_TICK == 0:
            await _hud(guild, gs, voting=True, seconds_left=left)

    gs.votes_open = False
    await resolve_votes(guild, gs)

# ---------------------------------------------------------------------

async def resolve_votes(guild: discord.Guild, gs: GameState):
    ch = await _channel(guild, gs.channel_id)
    if not ch:
        return

    votes: Dict[int, int] = {}
    for uid in _alive(gs):
        tgt = gs.players[uid].vote_target
        if tgt is not None and tgt in gs.players and gs.players[tgt].alive:
            votes[tgt] = votes.get(tgt, 0) + 1

    if not votes:
        await ch.send("🗳️ Nadie votó. **Sin eliminación.**")
        await next_round_or_end(guild, gs, tie=True)
        return

    max_votes = max(votes.values())
    tops = [uid for uid, c in votes.items() if c == max_votes]

    # Mostrar recuento por persona (sin quién votó a quién)
    lines = ["📊 **Recuento de votos (anónimo):**"]
    for uid, c in votes.items():
        nombre = f"AAT-Bot#{abs(uid)%1000}" if uid < 0 else (guild.get_member(uid).display_name if guild.get_member(uid) else str(uid))
        lines.append(f"• {nombre}: **{c}**")
    await ch.send("\n".join(lines))

    if len(tops) > 1:
        await ch.send(f"🟰 Empate en votos (**{max_votes}**). **Sin eliminación**.")
        await next_round_or_end(guild, gs, tie=True)
        return

    eliminated = tops[0]
    gs.players[eliminated].alive = False
    role = gs.players[eliminated].role or "?"
    nombre = f"AAT-Bot#{abs(eliminated)%1000}" if eliminated < 0 else (guild.get_member(eliminated).display_name if guild.get_member(eliminated) else str(eliminated))
    await ch.send(f"💀 Eliminado: **{nombre}** — Rol: **{role}**")

    if eliminated == gs.impostor_id:
        await end_game(guild, gs, winner="SOCIALES")
        return

    await next_round_or_end(guild, gs, tie=False)

# ---------------------------------------------------------------------

async def next_round_or_end(guild: discord.Guild, gs: GameState, tie: bool):
    alive = _alive(gs)
    impostor_alive = gs.impostor_id in alive
    ch = await _channel(guild, gs.channel_id)
    if not ch:
        return

    # condición de victoria del impostor
    if len(alive) <= 2 and impostor_alive:
        await end_game(guild, gs, winner="IMPOSTOR")
        return

    if gs.round_no >= MAX_ROUNDS:
        await end_game(guild, gs, winner="SOCIALES")  # seguridad
        return

    # Nueva ronda — refrescar orden sólo con vivos
    vivos = [uid for uid in gs.order if gs.players[uid].alive]
    gs.order = random.sample(vivos, k=len(vivos))
    gs.round_no += 1

    # Mostrar orden y comenzar pistas
    mention_order = []
    for i, uid in enumerate(gs.order, start=1):
        botflag = " 🤖" if _is_bot_sim(gs.guild_id, gs.lobby_name, uid) else ""
        mention_order.append(f"{i}. <@{uid}>{botflag}")
    await ch.send(f"🟢 **¡Comienza la Ronda {gs.round_no}!**\n**Orden de turnos:**\n" + "\n".join(mention_order))

    await open_clues_phase(guild, gs)

# ---------------------------------------------------------------------

async def end_game(guild: discord.Guild, gs: GameState, winner: str):
    ch = await _channel(guild, gs.channel_id)
    if not ch:
        del_game(guild.id, gs.lobby_name)
        return

    # stats opcional
    try:
        from .stats import stats_store
        if winner == "IMPOSTOR" and gs.impostor_id:
            await stats_store.add_win(guild.id, gs.impostor_id, "IMPOSTOR")
        elif winner == "SOCIALES":
            for uid, gp in gs.players.items():
                if gp.role == "SOCIAL":
                    await stats_store.add_win(guild.id, uid, "SOCIAL")
    except Exception:
        pass

    lines = [f"🎉 **Fin de la partida** — Ganador: **{winner}**"]
    if gs.impostor_id:
        nombre_imp = f"AAT-Bot#{abs(gs.impostor_id)%1000}" if gs.impostor_id < 0 else (guild.get_member(gs.impostor_id).display_name if guild.get_member(gs.impostor_id) else str(gs.impostor_id))
        lines.append(f"🕵️ Impostor: **{nombre_imp}**")
    if gs.word:
        lines.append(f"🎯 Palabra: **{gs.word}**")
        if gs.link:
            lines.append(gs.link)
    lines.append("**Jugadores**")
    for uid, gp in gs.players.items():
        status = "vivo" if gp.alive else "eliminado"
        botflag = " 🤖" if _is_bot_sim(gs.guild_id, gs.lobby_name, uid) else ""
        nombre = f"AAT-Bot#{abs(uid)%1000}" if uid < 0 else (guild.get_member(uid).display_name if guild.get_member(uid) else str(uid))
        lines.append(f"- {nombre}{botflag} — {gp.role} — {status}")

    emb = discord.Embed(title="IMPOSITOR — Resultado", color=discord.Color.gold(), description="\n".join(lines))
    await ch.send(embed=emb)

    # desbloquear o bloquear según quieras; dejamos lectura on
    try:
        overwrites = ch.overwrites
        for target, perms in overwrites.items():
            if isinstance(target, (discord.Member, discord.Role)):
                perms.send_messages = False
        await ch.edit(overwrites=overwrites)
    except Exception:
        pass

    # marcar lobby fuera de juego y actualizar panel
    lob = manager.get(guild.id, gs.lobby_name)
    if lob:
        lob.in_game = False
        try:
            from .ui import update_panel
            await update_panel(None, guild, lob)
        except Exception:
            pass

    del_game(guild.id, gs.lobby_name)
