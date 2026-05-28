# cogs/presentaciones.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Set

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()
log = logging.getLogger(__name__)


def _channel_id_presentacion() -> int:
    """Canal de texto de presentaciones (chat). Acepta nombre nuevo y legacy."""
    for key in ("PRESENTACION_CHANNEL_ID", "TRIGGER_CHANNEL_ID_PRESENTACION"):
        raw = (os.getenv(key) or "").strip()
        if raw.isdigit():
            return int(raw)
    return 0


def _env_int(key: str, default: int) -> int:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _sync_on_start_enabled() -> bool:
    return (os.getenv("PRESENTACION_CHUNIN_SYNC_ON_START", "1") or "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


CHANNEL_ID_PRESENTACION = _channel_id_presentacion()
CHUNIN_ROLE_ID = int(os.getenv("CHUNIN_ROLE_ID", "0") or 0)
HOKAGE_ROLE_ID = int(os.getenv("HOKAGE_ROLE_ID", "0") or 0)
EMOJI_ID_TOJITOOK = int(os.getenv("TOJITOOK_EMOJI_ID", "0") or 0)
EMOJI_NAME_TOJITOOK = os.getenv("TOJITOOK_EMOJI_NAME", "tojitook")
MAX_SCAN_PER_CHANNEL = _env_int("MAX_SCAN_PER_CHANNEL", 300)
CHUNIN_SYNC_LIMIT = _env_int("PRESENTACION_CHUNIN_SYNC_LIMIT", max(MAX_SCAN_PER_CHANNEL, 1000))


@dataclass
class ChuninSyncResult:
    ok: bool
    error: str = ""
    mensajes_escaneados: int = 0
    autores_unicos: int = 0
    roles_asignados: int = 0
    ya_tenian_rol: int = 0
    bypass_hokage: int = 0
    no_en_servidor: int = 0
    sin_permiso_bot: int = 0
    otros_fallos: int = 0


class PresentacionesCog(commands.Cog):
    """
    Una publicación por usuario en el canal de presentaciones.
    Al escribir (o al sincronizar) se asigna el rol Chūnin si falta.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._startup_sync_started = False

    @staticmethod
    def _tiene_bypass(member: discord.Member) -> bool:
        return bool(HOKAGE_ROLE_ID and any(r.id == HOKAGE_ROLE_ID for r in member.roles))

    @staticmethod
    def _es_staff(member: discord.Member) -> bool:
        perms = member.guild_permissions
        return bool(perms.administrator or perms.manage_guild)

    @staticmethod
    async def _buscar_msg_prev_en_canal(
        member: discord.Member,
        channel: discord.TextChannel,
        exclude_id: Optional[int] = None,
    ) -> Optional[discord.Message]:
        try:
            async for msg in channel.history(limit=MAX_SCAN_PER_CHANNEL, oldest_first=False):
                if msg.author.id == member.id and (exclude_id is None or msg.id != exclude_id):
                    return msg
        except (discord.Forbidden, Exception):
            return None
        return None

    async def _resolver_canal_presentacion(self) -> Optional[discord.TextChannel]:
        if not CHANNEL_ID_PRESENTACION:
            return None
        ch = self.bot.get_channel(CHANNEL_ID_PRESENTACION)
        if ch is None:
            try:
                ch = await self.bot.fetch_channel(CHANNEL_ID_PRESENTACION)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _dar_chunin(self, member: discord.Member, *, razon: str) -> str:
        """
        Intenta asignar Chūnin. Devuelve:
        bypass | already | no_config | hierarchy | ok | forbidden | error
        """
        if self._tiene_bypass(member):
            return "bypass"
        if not CHUNIN_ROLE_ID:
            return "no_config"
        role = member.guild.get_role(CHUNIN_ROLE_ID)
        if not role:
            return "no_config"
        if role in member.roles:
            return "already"
        me = member.guild.get_member(self.bot.user.id)
        if me and role >= me.top_role:
            return "hierarchy"
        try:
            await member.add_roles(role, reason=razon)
            return "ok"
        except discord.Forbidden:
            return "forbidden"
        except Exception as e:
            log.warning("Error asignando rol Chūnin a %s: %s", member.id, e)
            return "error"

    async def _recolectar_autores_presentacion(
        self, channel: discord.TextChannel, *, limit: int
    ) -> tuple[Set[int], int]:
        autores: Set[int] = set()
        count = 0
        try:
            async for msg in channel.history(limit=limit, oldest_first=False):
                count += 1
                if msg.author.bot:
                    continue
                autores.add(msg.author.id)
        except discord.Forbidden:
            raise
        return autores, count

    async def sincronizar_chunin_presentaciones(self, *, limit: Optional[int] = None) -> ChuninSyncResult:
        """Revisa el historial del canal y asigna Chūnin a quien publicó y no lo tiene."""
        lim = limit if limit is not None else CHUNIN_SYNC_LIMIT
        lim = max(1, min(lim, 5000))

        if not CHANNEL_ID_PRESENTACION:
            return ChuninSyncResult(ok=False, error="Falta `PRESENTACION_CHANNEL_ID` en .env")
        if not CHUNIN_ROLE_ID:
            return ChuninSyncResult(ok=False, error="Falta `CHUNIN_ROLE_ID` en .env")

        channel = await self._resolver_canal_presentacion()
        if not channel:
            return ChuninSyncResult(ok=False, error="No encontré el canal de presentaciones o sin permiso de lectura.")

        guild = channel.guild
        try:
            autores, scanned = await self._recolectar_autores_presentacion(channel, limit=lim)
        except discord.Forbidden:
            return ChuninSyncResult(
                ok=False,
                error="El bot no puede leer el historial de #presentaciones (`Read Message History`).",
            )

        result = ChuninSyncResult(
            ok=True,
            mensajes_escaneados=scanned,
            autores_unicos=len(autores),
        )

        for uid in autores:
            member = guild.get_member(uid)
            if member is None:
                try:
                    member = await guild.fetch_member(uid)
                except (discord.NotFound, discord.HTTPException):
                    result.no_en_servidor += 1
                    continue

            status = await self._dar_chunin(
                member, razon="Sincronización canal presentaciones (historial)"
            )
            if status == "ok":
                result.roles_asignados += 1
                await asyncio.sleep(0.2)
            elif status in ("already",):
                result.ya_tenian_rol += 1
            elif status == "bypass":
                result.bypass_hokage += 1
            elif status in ("hierarchy", "forbidden"):
                result.sin_permiso_bot += 1
            elif status == "no_config":
                return ChuninSyncResult(ok=False, error="Rol Chūnin no configurado o no existe en el servidor.")
            else:
                result.otros_fallos += 1

        log.info(
            "Sync Chūnin presentaciones: escaneados=%s autores=%s asignados=%s ya=%s",
            result.mensajes_escaneados,
            result.autores_unicos,
            result.roles_asignados,
            result.ya_tenian_rol,
        )
        return result

    @staticmethod
    def _embed_sync_result(result: ChuninSyncResult) -> discord.Embed:
        if not result.ok:
            return discord.Embed(
                title="Sync Chūnin — error",
                description=result.error,
                color=discord.Color.red(),
            )
        desc = (
            f"**Mensajes revisados:** {result.mensajes_escaneados}\n"
            f"**Autores distintos:** {result.autores_unicos}\n"
            f"**Rol asignado ahora:** {result.roles_asignados}\n"
            f"**Ya tenían Chūnin:** {result.ya_tenian_rol}"
        )
        extra = []
        if result.bypass_hokage:
            extra.append(f"Hokage (sin cambio): {result.bypass_hokage}")
        if result.no_en_servidor:
            extra.append(f"Ya no están en el servidor: {result.no_en_servidor}")
        if result.sin_permiso_bot:
            extra.append(f"Sin permiso/jerarquía del bot: {result.sin_permiso_bot}")
        if result.otros_fallos:
            extra.append(f"Otros fallos: {result.otros_fallos}")
        if extra:
            desc += "\n\n" + "\n".join(f"• {x}" for x in extra)
        return discord.Embed(
            title="Sync Chūnin — presentaciones",
            description=desc,
            color=discord.Color.green() if result.roles_asignados else discord.Color.blurple(),
        )

    async def _reaccionar(self, msg: discord.Message):
        try:
            await msg.add_reaction("🔥")
        except Exception:
            pass
        emoji_obj = None
        if EMOJI_ID_TOJITOOK:
            emoji_obj = self.bot.get_emoji(EMOJI_ID_TOJITOOK)
        if not emoji_obj and msg.guild:
            emoji_obj = discord.utils.find(
                lambda e: e.name.lower() == EMOJI_NAME_TOJITOOK.lower(), msg.guild.emojis
            )
        if emoji_obj:
            try:
                await msg.add_reaction(emoji_obj)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_ready(self):
        if self._startup_sync_started or not _sync_on_start_enabled():
            return
        self._startup_sync_started = True

        async def _run():
            await self.bot.wait_until_ready()
            await asyncio.sleep(3)
            if not CHANNEL_ID_PRESENTACION or not CHUNIN_ROLE_ID:
                return
            result = await self.sincronizar_chunin_presentaciones()
            if result.ok and result.roles_asignados:
                log.info("Arranque: %s rol(es) Chūnin asignados por sync presentaciones.", result.roles_asignados)
            elif not result.ok:
                log.warning("Arranque: sync Chūnin presentaciones falló: %s", result.error)

        asyncio.create_task(_run())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not CHANNEL_ID_PRESENTACION or message.channel.id != CHANNEL_ID_PRESENTACION:
            return

        member: discord.Member = message.author  # type: ignore

        if self._tiene_bypass(member):
            return

        previo = await self._buscar_msg_prev_en_canal(member, message.channel, exclude_id=message.id)
        if previo:
            user_msg_deleted = False
            try:
                await message.delete()
                user_msg_deleted = True
            except Exception:
                pass
            warn = None
            try:
                txt = (
                    f"{member.mention} solo se permite **una** publicación en este canal. "
                    "Podés **editar** la que ya tenés."
                    f" (Tu mensaje previo: {previo.jump_url})"
                )
                if not user_msg_deleted:
                    txt += " *(No pude borrar tu nuevo mensaje; revisen **Manage Messages** en este canal).*"
                warn = await message.channel.send(txt)
            except Exception:
                pass
            try:
                dm = await member.create_dm()
                await dm.send(
                    "👋 En el canal de presentaciones solo se permite **una** publicación por usuario.\n"
                    f"Editá tu mensaje previo: {previo.jump_url}"
                )
            except Exception:
                pass
            if warn:
                try:
                    await asyncio.sleep(6)
                    await warn.delete()
                except Exception:
                    pass
            await self._dar_chunin(member, razon="Presentación en canal (mensaje duplicado)")
            return

        await self._reaccionar(message)
        await self._dar_chunin(member, razon="Presentación en canal de chat")

    @app_commands.command(
        name="sync-chunin-presentaciones",
        description="[Staff] Revisa #presentaciones y asigna Chūnin a quien publicó y no lo tiene.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def sync_chunin_slash(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if not self._es_staff(interaction.user):
            await interaction.response.send_message("❌ Solo staff (admin o gestionar servidor).", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await self.sincronizar_chunin_presentaciones()
        await interaction.followup.send(embed=self._embed_sync_result(result), ephemeral=True)

    @commands.command(name="syncchunin", aliases=["chuninsync", "syncpresentaciones", "presentacionessync"])
    @commands.guild_only()
    async def sync_chunin_prefix(self, ctx: commands.Context):
        """[Staff] Sincroniza rol Chūnin con quienes escribieron en #presentaciones."""
        if not isinstance(ctx.author, discord.Member) or not self._es_staff(ctx.author):
            await ctx.send("❌ Solo staff (admin o gestionar servidor).", delete_after=8)
            return
        await ctx.send("⏳ Revisando historial de presentaciones…")
        result = await self.sincronizar_chunin_presentaciones()
        await ctx.send(embed=self._embed_sync_result(result))


async def setup(bot: commands.Bot):
    await bot.add_cog(PresentacionesCog(bot))
