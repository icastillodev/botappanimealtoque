# cogs/impostor/lobby.py
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .core import manager, Lobby, MAX_PLAYERS, CATEGORY_ID, PRE_GAME_TIMEOUT_SEC, is_admin_member
from .feed import feed
from .ui import update_panel  # <- UI panel


class LobbyCog(commands.Cog):
    """Gestión de lobbys: crear/entrar/invitar/abrir/cerrar/ready/kick/leave/finalizar."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- utilidades de canal --------
    async def _create_channel(self, guild: discord.Guild, lobby: Lobby) -> Optional[discord.TextChannel]:
        cat = guild.get_channel(CATEGORY_ID) if CATEGORY_ID else None
        if cat and not isinstance(cat, discord.CategoryChannel):
            cat = None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
        }
        host = guild.get_member(lobby.host_id)
        if host:
            overwrites[host] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            ch = await guild.create_text_channel(
                name=f"impostor-{lobby.name}",
                category=cat, overwrites=overwrites,
                topic=f"Lobby '{lobby.name}' • {lobby.slots()} • {'abierto' if lobby.is_open else 'cerrado'}"
            )
            lobby.channel_id = ch.id
            return ch
        except discord.Forbidden:
            return None

    async def _sync_membership(self, guild: discord.Guild, lobby: Lobby):
        if not lobby.channel_id:
            return
        ch = guild.get_channel(lobby.channel_id)
        if not isinstance(ch, discord.TextChannel):
            return
        overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False)}
        for p in lobby.players.values():
            m = guild.get_member(p.user_id)
            if not m:
                continue
            overwrites[m] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        try:
            await ch.edit(overwrites=overwrites, topic=f"Lobby '{lobby.name}' • {lobby.slots()} • {'abierto' if lobby.is_open else 'cerrado'}")
        except Exception:
            pass

    # -------- comandos --------
    @app_commands.command(name="crearimpostor", description="Crear un lobby de Impostor")
    @app_commands.describe(nombre="Nombre del lobby", tipo="abierto o cerrado")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="abierto", value="abierto"),
        app_commands.Choice(name="cerrado", value="cerrado"),
    ])
    async def crearimpostor(self, interaction: discord.Interaction, nombre: str, tipo: app_commands.Choice[str]):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Usá este comando en el servidor.", ephemeral=True)
        if manager.by_user(interaction.user.id):
            return await interaction.response.send_message("Ya estás en un lobby. Usá `/leave` antes de crear otro.", ephemeral=True)
        if manager.get(interaction.guild.id, nombre):
            return await interaction.response.send_message("Ese nombre de lobby ya existe.", ephemeral=True)

        lob = Lobby(name=nombre, host_id=interaction.user.id, is_open=(tipo.value == "abierto"), guild_id=interaction.guild.id)
        manager.register(lob)
        manager.add_user(lob, interaction.user)

        ch = await self._create_channel(interaction.guild, lob)
        if not ch:
            return await interaction.response.send_message("No pude crear el canal (revisá permisos/categoría).", ephemeral=True)

        await self._sync_membership(interaction.guild, lob)
        await ch.send(
            f"🎭 **Lobby '{lob.name}'** creado por <@{lob.host_id}> — {'abierto' if lob.is_open else 'cerrado'}\n"
            f"Jugadores: {lob.slots()}\n"
            f"Comandos: `/abrirlobby`, `/cerrarlobby`, `/invitar`, `/kick`, `/ready`, `/leave`"
        )
        await interaction.response.send_message(f"Lobby **{lob.name}** creado en {ch.mention}", ephemeral=True)
        await update_panel(self.bot, interaction.guild, lob)
        await feed.update(interaction.guild)

    @app_commands.command(name="entrar", description="Entrar a un lobby abierto")
    @app_commands.describe(nombre="Nombre del lobby")
    async def entrar(self, interaction: discord.Interaction, nombre: str):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Usá este comando en el servidor.", ephemeral=True)
        lob = manager.get(interaction.guild.id, nombre)
        if not lob or lob.in_game:
            return await interaction.response.send_message("Lobby no existe o ya está en partida.", ephemeral=True)
        if not lob.is_open:
            return await interaction.response.send_message("Ese lobby es cerrado. Pedí invitación al host.", ephemeral=True)
        if manager.by_user(interaction.user.id):
            return await interaction.response.send_message("Ya estás en un lobby. Usá `/leave` primero.", ephemeral=True)
        if len(lob.players) >= MAX_PLAYERS:
            return await interaction.response.send_message("El lobby está lleno (5/5).", ephemeral=True)

        manager.add_user(lob, interaction.user)
        await self._sync_membership(interaction.guild, lob)
        ch = interaction.guild.get_channel(lob.channel_id)
        if isinstance(ch, discord.TextChannel):
            await ch.send(f"👤 <@{interaction.user.id}> se unió. {lob.slots()}")
        await interaction.response.send_message(f"Te uniste a **{lob.name}**.", ephemeral=True)
        await update_panel(self.bot, interaction.guild, lob)
        await feed.update(interaction.guild)

    @app_commands.command(name="invitar", description="(Host) Invitar a alguien a tu lobby")
    async def invitar(self, interaction: discord.Interaction, usuario: discord.Member):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Usá este comando en el servidor.", ephemeral=True)
        lob = manager.by_user(interaction.user.id)
        if not lob or lob.host_id != interaction.user.id:
            return await interaction.response.send_message("No sos host de ningún lobby.", ephemeral=True)
        if lob.in_game:
            return await interaction.response.send_message("La partida ya comenzó.", ephemeral=True)
        if len(lob.players) >= MAX_PLAYERS:
            return await interaction.response.send_message("Lobby lleno (5/5).", ephemeral=True)
        if usuario.id in lob.players:
            return await interaction.response.send_message("Esa persona ya está en tu lobby.", ephemeral=True)

        manager.add_user(lob, usuario)
        await self._sync_membership(interaction.guild, lob)
        ch = interaction.guild.get_channel(lob.channel_id)
        if isinstance(ch, discord.TextChannel):
            await ch.send(f"✉️ <@{usuario.id}> fue invitado por <@{interaction.user.id}>. {lob.slots()}")
        await interaction.response.send_message(f"Invitado **{usuario.display_name}**.", ephemeral=True)
        await update_panel(self.bot, interaction.guild, lob)
        await feed.update(interaction.guild)

    @app_commands.command(name="abrirlobby", description="(Host) Abrir el lobby (entrada pública)")
    async def abrirlobby(self, interaction: discord.Interaction):
        lob = manager.by_user(interaction.user.id)
        if not lob or lob.host_id != interaction.user.id:
            return await interaction.response.send_message("No sos host de ningún lobby.", ephemeral=True)
        lob.is_open = True
        await interaction.response.send_message("Lobby abierto.", ephemeral=True)
        if interaction.guild:
            await update_panel(self.bot, interaction.guild, lob)
            await feed.update(interaction.guild)

    @app_commands.command(name="cerrarlobby", description="(Host) Cerrar el lobby (solo por invitación)")
    async def cerrarlobby(self, interaction: discord.Interaction):
        lob = manager.by_user(interaction.user.id)
        if not lob or lob.host_id != interaction.user.id:
            return await interaction.response.send_message("No sos host de ningún lobby.", ephemeral=True)
        lob.is_open = False
        await interaction.response.send_message("Lobby cerrado.", ephemeral=True)
        if interaction.guild:
            await update_panel(self.bot, interaction.guild, lob)
            await feed.update(interaction.guild)

    @app_commands.command(name="kick", description="(Host) Expulsar a un jugador del lobby")
    async def kick(self, interaction: discord.Interaction, usuario: discord.Member):
        lob = manager.by_user(interaction.user.id)
        if not lob or lob.host_id != interaction.user.id:
            return await interaction.response.send_message("No sos host de ningún lobby.", ephemeral=True)
        if usuario.id not in lob.players:
            return await interaction.response.send_message("Ese usuario no está en tu lobby.", ephemeral=True)

        manager.remove_user(interaction.guild_id, usuario.id)  # type: ignore
        await interaction.response.send_message("Expulsado.", ephemeral=True)
        if interaction.guild:
            await self._sync_membership(interaction.guild, lob)
            ch = interaction.guild.get_channel(lob.channel_id)
            if isinstance(ch, discord.TextChannel):
                await ch.send(f"🪓 <@{usuario.id}> fue expulsado por el host. {lob.slots()}")
            await update_panel(self.bot, interaction.guild, lob)
            await feed.update(interaction.guild)

    @app_commands.command(name="ready", description="Marcarte listo en tu lobby")
    async def ready(self, interaction: discord.Interaction):
        lob = manager.by_user(interaction.user.id)
        if not lob or lob.in_game:
            return await interaction.response.send_message("No estás en un lobby (o ya inició).", ephemeral=True)

        p = lob.players.get(interaction.user.id)
        if not p:
            return await interaction.response.send_message("No estás en este lobby.", ephemeral=True)
        if p.is_bot_sim:
            return await interaction.response.send_message("Los bots no necesitan estar listos.", ephemeral=True)
        if p.ready:
            return await interaction.response.send_message("Ya estabas listo.", ephemeral=True)

        p.ready = True

        humans_total = sum(1 for x in lob.players.values() if not x.is_bot_sim)
        humans_ready = sum(1 for x in lob.players.values() if not x.is_bot_sim and x.ready)

        await interaction.response.send_message("✅ Listo!", ephemeral=True)

        if interaction.guild and lob.channel_id:
            ch = interaction.guild.get_channel(lob.channel_id)
            if isinstance(ch, discord.TextChannel):
                await ch.send(f"✔️ <@{interaction.user.id}> está listo (**{humans_ready}/{humans_total}** humanos).")

        if interaction.guild:
            await update_panel(self.bot, interaction.guild, lob)
        # *** SIN AUTO-INICIO *** -> el host debe tocar "▶️ Comenzar"

    @app_commands.command(name="leave", description="Salir del lobby (tras 30s dentro)")
    async def leave(self, interaction: discord.Interaction):
        lob = manager.by_user(interaction.user.id)
        if not lob:
            return await interaction.response.send_message("No estás en un lobby.", ephemeral=True)
        if not manager.leave_allowed(interaction.user.id):
            return await interaction.response.send_message("Debés permanecer al menos 30 segundos antes de salir.", ephemeral=True)

        lob2 = manager.remove_user(interaction.guild_id, interaction.user.id)  # type: ignore
        await interaction.response.send_message("Saliste del lobby.", ephemeral=True)
        if interaction.guild and lob2:
            await self._sync_membership(interaction.guild, lob2)
            ch = interaction.guild.get_channel(lob2.channel_id)
            if isinstance(ch, discord.TextChannel):
                await ch.send(f"🚪 <@{interaction.user.id}> salió del lobby. {lob2.slots()}")
            # borrar si vacío (de humanos)
            if len([p for p in lob2.players.values() if not p.is_bot_sim]) == 0:
                try:
                    if isinstance(ch, discord.TextChannel):
                        await ch.delete(reason="Lobby vacío")
                except Exception:
                    pass
                manager.delete_if_empty(interaction.guild.id, lob2.name)
            await feed.update(interaction.guild)
            if manager.get(interaction.guild.id, lob2.name):
                await update_panel(self.bot, interaction.guild, lob2)

    @app_commands.command(name="finalizar_lobby", description="(Host/Admin) Finalizar lobby si no empezó en 5 minutos")
    async def finalizar_lobby(self, interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Usá esto en el servidor.", ephemeral=True)
        lob = manager.by_user(interaction.user.id)
        if not lob:
            return await interaction.response.send_message("No estás en un lobby.", ephemeral=True)

        es_host = (lob.host_id == interaction.user.id)
        es_admin = is_admin_member(interaction.user)

        if not (es_host or es_admin):
            return await interaction.response.send_message("Solo el host o un admin puede finalizar.", ephemeral=True)
        if lob.in_game:
            return await interaction.response.send_message("El lobby ya está en partida.", ephemeral=True)
        if (int(time.time()) - lob.created_ts) < PRE_GAME_TIMEOUT_SEC and not es_admin:
            faltan = PRE_GAME_TIMEOUT_SEC - (int(time.time()) - lob.created_ts)
            return await interaction.response.send_message(f"Esperá {faltan//60}m {faltan%60}s para poder finalizar.", ephemeral=True)

        ch = interaction.guild.get_channel(lob.channel_id) if lob.channel_id else None
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send("⛔ Lobby finalizado por host/admin. Cerrando canal…")
                await ch.delete(reason="Lobby finalizado sin iniciar")
            except Exception:
                pass
        for uid in list(lob.players.keys()):
            manager.remove_user(interaction.guild.id, uid)
        manager.delete_if_empty(interaction.guild.id, lob.name)
        await interaction.response.send_message("Lobby finalizado.", ephemeral=True)
        await feed.update(interaction.guild)

    # -------- eventos --------
    @commands.Cog.listener()
    async def on_ready(self):
        for g in self.bot.guilds:
            await feed.update(g)


async def setup_lobby(bot: commands.Bot):
    await bot.add_cog(LobbyCog(bot))
