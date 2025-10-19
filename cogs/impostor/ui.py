# cogs/impostor/ui.py
from __future__ import annotations

import discord
from typing import Optional

from discord.ext import commands

from .core import manager, is_admin_member, MAX_PLAYERS
from .feed import feed


# ---------- helpers ----------
def _is_host(inter: discord.Interaction, lobby) -> bool:
    return lobby and lobby.host_id == inter.user.id


def _panel_title(lobby) -> str:
    estado = "jugando" if lobby.in_game else ("abierto" if lobby.is_open else "cerrado")
    return f"🎭 Lobby: {lobby.name} — {lobby.slots()} — {estado}"


async def _ensure_channel(inter: discord.Interaction, lobby) -> Optional[discord.TextChannel]:
    if not inter.guild or not lobby.channel_id:
        return None
    ch = inter.guild.get_channel(lobby.channel_id)
    return ch if isinstance(ch, discord.TextChannel) else None


# ---------- Vista del mensaje final (botón salir SÍEMPRE) ----------
class FinalLeaveView(discord.ui.View):
    """Botón 'Salir del lobby' que se usa al mensaje final de la partida.
       No aplica la espera de 30s; sale siempre."""
    def __init__(self, lobby_name: str):
        super().__init__(timeout=0)  # persistente
        self.lobby_name = lobby_name

    @discord.ui.button(label="🚪 Salir del lobby", style=discord.ButtonStyle.secondary, custom_id="imp:leave_final")
    async def leave_final(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message("Usá esto en el servidor.", ephemeral=True)

        lob = manager.get(inter.guild.id, self.lobby_name)
        if not lob:
            return await inter.response.send_message("Lobby no existe.", ephemeral=True)

        # ⛔ Sin chequeo de 30s: sale siempre
        lob2 = manager.remove_user(inter.guild_id, inter.user.id)  # type: ignore
        await inter.response.send_message("Saliste del lobby.", ephemeral=True)

        if inter.guild and lob2:
            ch = inter.guild.get_channel(lob2.channel_id) if lob2.channel_id else None
            if isinstance(ch, discord.TextChannel):
                await ch.send(f"🚪 <@{inter.user.id}> salió del lobby. {lob2.slots()}")
            # Si ya no quedan humanos, borrar canal + lobby
            if len([p for p in lob2.players.values() if not p.is_bot_sim]) == 0:
                try:
                    if isinstance(ch, discord.TextChannel):
                        await ch.delete(reason="Lobby vacío")
                except Exception:
                    pass
                manager.delete_if_empty(inter.guild.id, lob2.name)
            await feed.update(inter.guild)
            if manager.get(inter.guild.id, lob2.name):
                await update_panel(None, inter.guild, lob2)


# ---------- Vista del panel ----------
class LobbyPanel(discord.ui.View):
    """Panel interactivo dentro del canal del lobby."""
    def __init__(self, bot: Optional[commands.Bot], lobby_name: str, *, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.bot = bot  # puede ser None; no lo usamos para instanciar nada
        self.lobby_name = lobby_name

    # ---------- BOTONES GENÉRICOS ----------
    @discord.ui.button(label="✅ Ready", style=discord.ButtonStyle.success, custom_id="imp:ready")
    async def btn_ready(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message("Usá esto en el servidor.", ephemeral=True)

        lob = manager.by_user(inter.user.id)
        if not lob or lob.name != self.lobby_name or lob.in_game:
            return await inter.response.send_message("No estás en este lobby (o ya comenzó).", ephemeral=True)
        p = lob.players.get(inter.user.id)
        if not p:
            return await inter.response.send_message("No estás en este lobby.", ephemeral=True)
        if p.ready:
            return await inter.response.send_message("Ya estabas listo.", ephemeral=True)
        p.ready = True

        ch = await _ensure_channel(inter, lob)
        if ch:
            await ch.send(f"✔️ <@{inter.user.id}> está listo "
                          f"({sum(1 for x in lob.players.values() if x.ready)}/{len(lob.players)})")
        await inter.response.send_message("Listo ✅", ephemeral=True)
        await update_panel(self.bot, inter.guild, lob)

    @discord.ui.button(label="🚪 Leave", style=discord.ButtonStyle.secondary, custom_id="imp:leave")
    async def btn_leave(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message("Usá esto en el servidor.", ephemeral=True)
        lob = manager.by_user(inter.user.id)
        if not lob or lob.name != self.lobby_name:
            return await inter.response.send_message("No estás en este lobby.", ephemeral=True)

        # ⛔ Sin espera de 30s para el botón: sale siempre
        lob2 = manager.remove_user(inter.guild_id, inter.user.id)  # type: ignore
        await inter.response.send_message("Saliste del lobby.", ephemeral=True)
        if inter.guild and lob2:
            ch = inter.guild.get_channel(lob2.channel_id) if lob2.channel_id else None
            if isinstance(ch, discord.TextChannel):
                await ch.send(f"🚪 <@{inter.user.id}> salió del lobby. {lob2.slots()}")
            if len([p for p in lob2.players.values() if not p.is_bot_sim]) == 0:
                try:
                    if isinstance(ch, discord.TextChannel):
                        await ch.delete(reason="Lobby vacío")
                except Exception:
                    pass
                manager.delete_if_empty(inter.guild.id, lob2.name)
            await feed.update(inter.guild)
            if manager.get(inter.guild.id, lob2.name):
                await update_panel(self.bot, inter.guild, lob2)

    # ---------- HOST / ADMIN ----------
    @discord.ui.button(label="🔓 Abrir/Cerrar", style=discord.ButtonStyle.primary, custom_id="imp:toggle_open")
    async def btn_toggle_open(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message("Usá esto en el servidor.", ephemeral=True)
        lob = manager.get(inter.guild.id, self.lobby_name)
        if not lob:
            return await inter.response.send_message("Lobby no existe.", ephemeral=True)
        if not (_is_host(inter, lob) or is_admin_member(inter.user)):
            return await inter.response.send_message("Solo host o admin.", ephemeral=True)
        lob.is_open = not lob.is_open
        await inter.response.send_message(f"Lobby ahora está **{'abierto' if lob.is_open else 'cerrado'}**.",
                                          ephemeral=True)
        await feed.update(inter.guild)
        await update_panel(self.bot, inter.guild, lob)

    @discord.ui.button(label="✉️ Invitar", style=discord.ButtonStyle.primary, custom_id="imp:invite")
    async def btn_invite(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message("Usá esto en el servidor.", ephemeral=True)
        lob = manager.get(inter.guild.id, self.lobby_name)
        if not lob:
            return await inter.response.send_message("Lobby no existe.", ephemeral=True)
        if not (_is_host(inter, lob) or is_admin_member(inter.user)):
            return await inter.response.send_message("Solo host o admin.", ephemeral=True)
        if len(lob.players) >= MAX_PLAYERS:
            return await inter.response.send_message("Lobby lleno (5/5).", ephemeral=True)

        class InviteModal(discord.ui.Modal, title="Invitar a jugador"):
            user_field = discord.ui.TextInput(label="@Usuario (mención o ID)",
                                              placeholder="@nombre#1234 o ID", required=True)

            async def on_submit(self, interaction: discord.Interaction):
                txt = str(self.user_field.value).strip()
                member: Optional[discord.Member] = None
                if interaction.guild:
                    if txt.startswith("<@") and txt.endswith(">"):
                        try:
                            uid = int(txt.strip("<@!>"))
                            member = interaction.guild.get_member(uid)
                        except Exception:
                            member = None
                    if member is None and txt.isdigit():
                        member = interaction.guild.get_member(int(txt))
                    if member is None:
                        for m in interaction.guild.members:
                            if m.name.lower() in txt.lower() or \
                               (m.display_name and m.display_name.lower() in txt.lower()):
                                member = m
                                break
                if not member:
                    return await interaction.response.send_message("No pude encontrar ese usuario.", ephemeral=True)

                if member.id in lob.players:
                    return await interaction.response.send_message("Esa persona ya está en el lobby.", ephemeral=True)
                if len(lob.players) >= MAX_PLAYERS:
                    return await interaction.response.send_message("Lobby lleno (5/5).", ephemeral=True)

                manager.add_user(lob, member)
                ch = await _ensure_channel(interaction, lob)
                if ch:
                    await ch.send(f"✉️ <@{member.id}> fue invitado por <@{interaction.user.id}>. {lob.slots()}")
                await interaction.response.send_message("Invitación completada ✅", ephemeral=True)
                await update_panel(self.bot, interaction.guild, lob)

        await inter.response.send_modal(InviteModal())

    @discord.ui.button(label="▶️ Comenzar", style=discord.ButtonStyle.success, custom_id="imp:start")
    async def btn_start(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message("Usá esto en el servidor.", ephemeral=True)
        lob = manager.get(inter.guild.id, self.lobby_name)
        if not lob:
            return await inter.response.send_message("Lobby no existe.", ephemeral=True)
        if not (_is_host(inter, lob) or is_admin_member(inter.user)):
            return await inter.response.send_message("Solo host o admin.", ephemeral=True)
        if lob.in_game:
            return await inter.response.send_message("La partida ya está en curso.", ephemeral=True)
        if len(lob.players) != MAX_PLAYERS:
            return await inter.response.send_message("Se necesitan exactamente 5 jugadores.", ephemeral=True)
        if not all(p.ready for p in lob.players.values()):
            return await inter.response.send_message("Todos deben estar **ready**.", ephemeral=True)

        # IMPORT LOCAL para evitar import circular
        from .game_core import start_game
        gs = await start_game(inter.guild, lob.name)  # type: ignore[arg-type]
        if not gs:
            return await inter.response.send_message("No se pudo iniciar la partida.", ephemeral=True)
        lob.in_game = True
        await inter.response.send_message("✅ Partida iniciada.", ephemeral=True)
        await update_panel(self.bot, inter.guild, lob)

    @discord.ui.button(label="🚀 Forzar inicio", style=discord.ButtonStyle.danger, custom_id="imp:force")
    async def btn_force(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message("Usá esto en el servidor.", ephemeral=True)
        lob = manager.get(inter.guild.id, self.lobby_name)
        if not lob:
            return await inter.response.send_message("Lobby no existe.", ephemeral=True)
        if not (_is_host(inter, lob) or is_admin_member(inter.user)):
            return await inter.response.send_message("Solo host o admin.", ephemeral=True)
        if lob.in_game:
            return await inter.response.send_message("La partida ya está en curso.", ephemeral=True)
        if len(lob.players) != MAX_PLAYERS:
            return await inter.response.send_message("Se necesitan exactamente 5 jugadores.", ephemeral=True)

        from .game_core import start_game
        gs = await start_game(inter.guild, lob.name)  # type: ignore[arg-type]
        if not gs:
            return await inter.response.send_message("No se pudo iniciar la partida.", ephemeral=True)
        lob.in_game = True
        await inter.response.send_message("🚀 Partida iniciada (forzado).", ephemeral=True)
        await update_panel(self.bot, inter.guild, lob)

    @discord.ui.button(label="🤖 AddBot", style=discord.ButtonStyle.secondary, custom_id="imp:addbot")
    async def btn_addbot(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message("Usá esto en el servidor.", ephemeral=True)
        lob = manager.get(inter.guild.id, self.lobby_name)
        if not lob:
            return await inter.response.send_message("Lobby no existe.", ephemeral=True)
        if not (_is_host(inter, lob) or is_admin_member(inter.user)):
            return await inter.response.send_message("Solo host o admin.", ephemeral=True)
        if len(lob.players) >= MAX_PLAYERS:
            return await inter.response.send_message("Lobby lleno (5/5).", ephemeral=True)

        uid = manager.add_sim_bot(lob)
        if uid == 0:
            return await inter.response.send_message("No se pudo agregar el bot.", ephemeral=True)
        ch = await _ensure_channel(inter, lob)
        if ch:
            await ch.send(f"🤖 **AAT-Bot** se unió (listo). {lob.slots()}")
        await inter.response.send_message("Bot agregado ✅", ephemeral=True)
        await update_panel(self.bot, inter.guild, lob)

    @discord.ui.button(label="🔁 Revancha", style=discord.ButtonStyle.primary, custom_id="imp:rematch")
    async def btn_rematch(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message("Usá esto en el servidor.", ephemeral=True)
        lob = manager.get(inter.guild.id, self.lobby_name)
        if not lob:
            return await inter.response.send_message("Lobby no existe.", ephemeral=True)
        if not (_is_host(inter, lob) or is_admin_member(inter.user)):
            return await inter.response.send_message("Solo host o admin.", ephemeral=True)
        if lob.in_game:
            return await inter.response.send_message("La partida está en curso.", ephemeral=True)

        for p in lob.players.values():
            p.ready = False
        ch = await _ensure_channel(inter, lob)
        if ch:
            try:
                overwrites = ch.overwrites
                for target, perms in overwrites.items():
                    if isinstance(target, (discord.Member, discord.Role)):
                        perms.send_messages = True
                await ch.edit(overwrites=overwrites)
                await ch.send("🔁 **Revancha solicitada** — Todos marquen `/ready` o usen el botón **Ready**.\n"
                              "(Host puede **Forzar inicio** si ya están 5/5.)")
            except Exception:
                pass
        await inter.response.send_message("Revancha armada ✅", ephemeral=True)
        await update_panel(self.bot, inter.guild, lob)


# ---------- API: crear/actualizar panel ----------
async def update_panel(bot: commands.Bot | None, guild: discord.Guild, lobby) -> None:
    """Crea o edita el mensaje de Panel en el canal del lobby."""
    if not lobby.channel_id:
        return
    ch = guild.get_channel(lobby.channel_id)
    if not isinstance(ch, discord.TextChannel):
        return

    view = LobbyPanel(bot, lobby.name)
    embed = discord.Embed(title=_panel_title(lobby), color=discord.Color.teal())

    players = []
    for uid, p in lobby.players.items():
        flag = " 🤖" if p.is_bot_sim else ""
        rdy = "✅" if p.ready else "…"
        players.append(f"<@{uid}>{flag} {rdy}")
    embed.add_field(name="Jugadores", value="\n".join(players) if players else "—", inline=False)

    if lobby.in_game:
        embed.set_footer(text="Partida en curso. Usá /palabra y /votar según la fase.")
    else:
        embed.set_footer(text="Esperando jugadores y ready. Se necesitan 5/5.")

    try:
        if lobby.dashboard_msg_id:
            msg = await ch.fetch_message(lobby.dashboard_msg_id)
            await msg.edit(embed=embed, view=view)
        else:
            msg = await ch.send(embed=embed, view=view)
            lobby.dashboard_msg_id = msg.id
    except Exception:
        try:
            msg = await ch.send(embed=embed, view=view)
            lobby.dashboard_msg_id = msg.id
        except Exception:
            pass
