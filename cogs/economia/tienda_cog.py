# cogs/economia/tienda_cog.py
from __future__ import annotations

import logging
import time
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .db_manager import EconomiaDBManagerV2

log = logging.getLogger(__name__)

PollDuracion = Literal["10 Minutos", "20 Minutos", "30 Minutos", "60 Minutos"]
_DURATION_MAP = {"10 Minutos": 10, "20 Minutos": 20, "30 Minutos": 30, "60 Minutos": 60}


class TiendaCog(commands.Cog, name="Economia Tienda"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economia_db: EconomiaDBManagerV2 = bot.economia_db
        self.config = bot.shop_config
        self.task_config = getattr(bot, "task_config", None) or {}
        super().__init__()

    def cog_unload(self):
        self._expire_temp_roles.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._expire_temp_roles.is_running():
            self._expire_temp_roles.start()

    def _cfg(self, key: str, default: int = 0) -> int:
        if not self.config:
            return default
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _general_channel_id(self) -> Optional[int]:
        ch = (self.task_config or {}).get("channels", {}).get("general")
        return int(ch) if ch else None

    def _build_tienda_embed(self, eco: dict) -> discord.Embed:
        embed = discord.Embed(
            title="🏪 Tienda Anime al Toque",
            description=(
                "Gastá **puntos** 🪙 en recompensas. Los precios dependen del servidor.\n"
                f"**Tu saldo:** `{eco['puntos_actuales']}` pts · **Créditos pin:** `{eco.get('creditos_pin', 0)}`"
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        if not self.config:
            embed.description = "La tienda no está configurada."
            return embed

        def line(name: str, item_id: str, price: int, extra: str = "") -> str:
            if price <= 0:
                return f"~~{name}~~ — *no disponible*\n"
            return f"**{name}** · `{item_id}` — **{price}** pts{extra}\n"

        pa = self.config.get("price_akatsuki", 0)
        pj = self.config.get("price_jonin", 0)
        pp = self.config.get("price_pin", 0)
        pbt = self._cfg("price_blister_trampa", 0)
        poll = self._cfg("price_poll_tienda", 0)
        ppg = self._cfg("price_pin_general", 0)
        ptr = self._cfg("price_temp_role", 0)
        vch = self._cfg("votacion_channel_id", 0)

        embed.add_field(
            name="Roles permanentes",
            value=(
                line("Rol Akatsuki", "akatsuki", int(pa or 0))
                + line("Rol Jonin", "jonin", int(pj or 0))
                + "_Canje:_ `/aat_tienda_canjear` → elegí el ítem."
            ),
            inline=False,
        )
        embed.add_field(
            name="Pin de mensajes",
            value=(
                line("Crédito para fijar (cualquier canal donde tengas permiso)", "pin", int(pp or 0))
                + "· Usá `/aat_tienda_fijar` con la **ID del mensaje** en ese canal.\n"
                + (line("Fijar en #general (un solo pago, sin crédito)", "—", int(ppg)) if ppg > 0 else "")
                + (f"· Comando: `/aat_tienda_pin_general`\n" if ppg > 0 else "")
            ),
            inline=False,
        )
        embed.add_field(
            name="Cartas",
            value=(
                line("Sobre **Trampa** (1 blister)", "blister_trampa", int(pbt))
                + "· Abrilo con `/aat_abrirblister` tipo trampa.\n"
            ),
            inline=False,
        )
        extra = ""
        if poll > 0 and vch > 0:
            extra = f"**Encuesta en canal votación** — **{poll}** pts → `/aat_tienda_encuesta`\n"
        elif poll > 0 and vch <= 0:
            extra = "_Encuesta tienda:_ esta opción no está disponible en este servidor.\n"
        if ptr > 0:
            extra += f"**Rol personal 30 días** — **{ptr}** pts → `/aat_tienda_rol_temporal`\n"
        if extra:
            embed.add_field(name="Extras (puntos)", value=extra, inline=False)
        embed.set_footer(text="/aat_ayuda · página Tienda para paso a paso")
        return embed

    @app_commands.command(name="aat_tienda_ver", description="Catálogo de la tienda y tu saldo.")
    async def ver_tienda(self, interaction: discord.Interaction):
        if not self.config:
            await interaction.response.send_message("La tienda no está configurada.", ephemeral=True)
            return
        self.economia_db.ensure_user_exists(interaction.user.id)
        eco = self.economia_db.get_user_economy(interaction.user.id)
        await interaction.response.send_message(embed=self._build_tienda_embed(eco), ephemeral=True)

    @app_commands.command(name="aat_tienda_canjear", description="Comprá un ítem de la tienda con puntos.")
    @app_commands.describe(
        item_id="akatsuki | jonin | pin | blister_trampa",
    )
    async def canjear_item(
        self,
        interaction: discord.Interaction,
        item_id: Literal["akatsuki", "jonin", "pin", "blister_trampa"],
    ):
        await interaction.response.defer(ephemeral=True)
        if not self.config:
            await interaction.followup.send("La tienda no está configurada.", ephemeral=True)
            return

        user_data = self.economia_db.get_user_economy(interaction.user.id)
        item_id = item_id.lower()
        precio = 0
        try:
            if item_id == "akatsuki":
                precio = int(self.config["price_akatsuki"])
            elif item_id == "jonin":
                precio = int(self.config["price_jonin"])
            elif item_id == "pin":
                precio = int(self.config["price_pin"])
            elif item_id == "blister_trampa":
                precio = self._cfg("price_blister_trampa", 0)
        except KeyError:
            await interaction.followup.send("Error de configuración para este ítem.", ephemeral=True)
            return

        if precio <= 0:
            await interaction.followup.send("Este ítem no está habilitado (precio 0 en configuración).", ephemeral=True)
            return

        if user_data["puntos_actuales"] < precio:
            await interaction.followup.send(
                f"No te alcanza: necesitás **{precio}** pts y tenés **{user_data['puntos_actuales']}**.",
                ephemeral=True,
            )
            return

        self.economia_db.modify_points(interaction.user.id, precio, gastar=True)

        if item_id in ("akatsuki", "jonin"):
            role_id_key = "akatsuki_role_id" if item_id == "akatsuki" else "jonin_role_id"
            role_id = self.config.get(role_id_key)
            if not role_id or not interaction.guild:
                self.economia_db.modify_points(interaction.user.id, precio, gastar=False)
                await interaction.followup.send(
                    "Se devolvieron los puntos: falta ID del rol o no estás en un servidor.",
                    ephemeral=True,
                )
                return
            role = interaction.guild.get_role(int(role_id))
            if not role:
                self.economia_db.modify_points(interaction.user.id, precio, gastar=False)
                await interaction.followup.send("Se devolvieron los puntos: no encontré ese rol en el servidor.", ephemeral=True)
                return
            try:
                await interaction.user.add_roles(role, reason="Tienda Anime al Toque")
                await interaction.followup.send(f"✅ Listo: te asigné **{role.name}**.", ephemeral=True)
            except discord.Forbidden:
                self.economia_db.modify_points(interaction.user.id, precio, gastar=False)
                await interaction.followup.send(
                    "Se devolvieron los puntos: el bot no puede asignar ese rol (jerarquía / permisos).",
                    ephemeral=True,
                )
        elif item_id == "pin":
            self.economia_db.set_credits(interaction.user.id, user_data["creditos_pin"] + 1)
            await interaction.followup.send(
                "✅ **+1 crédito de pin.** Usalo con `/aat_tienda_fijar` (ID del mensaje en el canal correspondiente).",
                ephemeral=True,
            )
        elif item_id == "blister_trampa":
            _, bcol = self.economia_db.modify_blisters(interaction.user.id, "trampa", 1)
            extra = ("\n\n" + "\n".join(bcol)) if bcol else ""
            await interaction.followup.send(
                "✅ **+1 sobre Trampa.** Abrilo con `/aat_abrirblister` eligiendo tipo **trampa**." + extra,
                ephemeral=True,
            )

    @app_commands.command(
        name="aat_tienda_fijar",
        description="Gastás 1 crédito de pin para fijar un mensaje en el canal donde ejecutás el comando.",
    )
    @app_commands.describe(id_mensaje="ID numérica del mensaje (clic derecho → Copiar ID).")
    async def fijar_mensaje(self, interaction: discord.Interaction, id_mensaje: str):
        await interaction.response.defer(ephemeral=True)
        if not id_mensaje.isdigit():
            await interaction.followup.send("La ID tiene que ser solo números.", ephemeral=True)
            return
        if not self.economia_db.use_credit(interaction.user.id):
            await interaction.followup.send(
                "No tenés créditos. Comprá con `/aat_tienda_canjear` → **pin**.",
                ephemeral=True,
            )
            return
        try:
            mensaje = await interaction.channel.fetch_message(int(id_mensaje))
            await mensaje.pin(reason=f"Pin tienda — {interaction.user} ({interaction.user.id})")
            await interaction.followup.send(
                "✅ Mensaje fijado. Si Discord avisa por DM, es el aviso normal de pin.",
                ephemeral=True,
            )
        except discord.NotFound:
            self.economia_db.set_credits(
                interaction.user.id, self.economia_db.get_user_economy(interaction.user.id)["creditos_pin"] + 1
            )
            await interaction.followup.send(
                "No encontré ese mensaje **en este canal**. Se te devolvió el crédito.",
                ephemeral=True,
            )
        except discord.Forbidden:
            self.economia_db.set_credits(
                interaction.user.id, self.economia_db.get_user_economy(interaction.user.id)["creditos_pin"] + 1
            )
            await interaction.followup.send(
                "No pude fijar (permisos). Se te devolvió el crédito.",
                ephemeral=True,
            )
        except Exception as e:
            self.economia_db.set_credits(
                interaction.user.id, self.economia_db.get_user_economy(interaction.user.id)["creditos_pin"] + 1
            )
            await interaction.followup.send(f"Error: {e}. Crédito devuelto.", ephemeral=True)

    @app_commands.command(
        name="aat_tienda_pin_general",
        description="Pagás con puntos y fijás un mensaje en #general (sin usar crédito de pin).",
    )
    @app_commands.describe(id_mensaje="ID del mensaje en #general.")
    async def pin_general(self, interaction: discord.Interaction, id_mensaje: str):
        await interaction.response.defer(ephemeral=True)
        precio = self._cfg("price_pin_general", 0)
        if precio <= 0:
            await interaction.followup.send("Esta opción no está disponible en este servidor.", ephemeral=True)
            return
        gid = self._general_channel_id()
        if not gid or not interaction.guild:
            await interaction.followup.send("No está configurado el canal #general (`GENERAL_CHANNEL_ID`).", ephemeral=True)
            return
        if not id_mensaje.isdigit():
            await interaction.followup.send("La ID tiene que ser numérica.", ephemeral=True)
            return

        eco = self.economia_db.get_user_economy(interaction.user.id)
        if eco["puntos_actuales"] < precio:
            await interaction.followup.send(
                f"Necesitás **{precio}** pts (tenés {eco['puntos_actuales']}).",
                ephemeral=True,
            )
            return

        ch = interaction.guild.get_channel(gid)
        if not isinstance(ch, discord.TextChannel):
            await interaction.followup.send("El canal general configurado no es de texto.", ephemeral=True)
            return

        self.economia_db.modify_points(interaction.user.id, precio, gastar=True)
        try:
            msg = await ch.fetch_message(int(id_mensaje))
            await msg.pin(reason=f"Pin general tienda — {interaction.user} ({interaction.user.id})")
            await interaction.followup.send(
                f"✅ Pagaste **{precio}** pts y fijaste el mensaje en {ch.mention}.",
                ephemeral=True,
            )
        except discord.NotFound:
            self.economia_db.modify_points(interaction.user.id, precio, gastar=False)
            await interaction.followup.send(
                "No encontré ese mensaje en #general. **Puntos devueltos.**",
                ephemeral=True,
            )
        except discord.Forbidden:
            self.economia_db.modify_points(interaction.user.id, precio, gastar=False)
            await interaction.followup.send(
                "Sin permiso para fijar ahí. **Puntos devueltos.**",
                ephemeral=True,
            )
        except Exception as e:
            self.economia_db.modify_points(interaction.user.id, precio, gastar=False)
            await interaction.followup.send(f"Error: {e}. **Puntos devueltos.**", ephemeral=True)

    @app_commands.command(
        name="aat_tienda_encuesta",
        description="Pagás puntos y publicás una votación en el canal de votaciones del servidor.",
    )
    @app_commands.describe(
        titulo="Título de la encuesta",
        opcion1="Primera opción",
        opcion2="Segunda opción",
        duracion="Cuánto dura",
        descripcion="Texto opcional bajo el título",
        opcion3="Opcional",
        opcion4="Opcional",
        url_imagen="URL de imagen opcional (ej. Imgur)",
    )
    async def tienda_encuesta(
        self,
        interaction: discord.Interaction,
        titulo: str,
        opcion1: str,
        opcion2: str,
        duracion: PollDuracion,
        descripcion: Optional[str] = None,
        opcion3: Optional[str] = None,
        opcion4: Optional[str] = None,
        url_imagen: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        precio = self._cfg("price_poll_tienda", 0)
        cid = self._cfg("votacion_channel_id", 0)
        if precio <= 0 or cid <= 0:
            await interaction.followup.send("Esta opción no está disponible en este servidor.", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.followup.send("Solo en servidor.", ephemeral=True)
            return

        eco = self.economia_db.get_user_economy(interaction.user.id)
        if eco["puntos_actuales"] < precio:
            await interaction.followup.send(
                f"Necesitás **{precio}** pts (tenés {eco['puntos_actuales']}).",
                ephemeral=True,
            )
            return

        ch = interaction.guild.get_channel(cid)
        if not isinstance(ch, discord.TextChannel):
            await interaction.followup.send("Canal de votación inválido en configuración.", ephemeral=True)
            return

        vot = self.bot.get_cog("VotacionCog")
        if not vot:
            for cog in self.bot.cogs.values():
                if cog.__class__.__name__ == "VotacionCog":
                    vot = cog
                    break
        if not vot or not hasattr(vot, "create_shop_poll"):
            await interaction.followup.send("Módulo de votaciones no disponible.", ephemeral=True)
            return

        self.economia_db.modify_points(interaction.user.id, precio, gastar=True)
        minutes = _DURATION_MAP[duracion]
        ok, err, _msg = await vot.create_shop_poll(
            ch,
            interaction.guild,
            interaction.user,
            titulo[:200],
            opcion1[:80],
            opcion2[:80],
            minutes,
            descripcion=descripcion[:500] if descripcion else None,
            opcion3=opcion3[:80] if opcion3 else None,
            opcion4=opcion4[:80] if opcion4 else None,
            url_imagen=url_imagen,
        )
        if not ok:
            self.economia_db.modify_points(interaction.user.id, precio, gastar=False)
            await interaction.followup.send(f"No se pudo publicar. **Puntos devueltos.**\n{err}", ephemeral=True)
            return
        await interaction.followup.send(
            f"✅ **-{precio}** pts. Tu encuesta está en {ch.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="aat_tienda_rol_temporal",
        description="Creás un rol con nombre personal y se lo das a alguien (o a vos) por 30 días.",
    )
    @app_commands.describe(
        nombre_rol="Nombre visible del rol (máx. 80 caracteres).",
        usuario="A quién se lo damos (podés elegirte).",
    )
    async def tienda_rol_temporal(
        self,
        interaction: discord.Interaction,
        nombre_rol: str,
        usuario: discord.Member,
    ):
        await interaction.response.defer(ephemeral=True)
        precio = self._cfg("price_temp_role", 0)
        raw_days = int(self.config.get("temp_role_days", 30) if self.config else 30)
        days = max(1, min(30, raw_days))
        if precio <= 0:
            await interaction.followup.send("Esta opción no está disponible en este servidor.", ephemeral=True)
            return
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Solo en servidor.", ephemeral=True)
            return

        eco = self.economia_db.get_user_economy(interaction.user.id)
        if eco["puntos_actuales"] < precio:
            await interaction.followup.send(
                f"Necesitás **{precio}** pts (tenés {eco['puntos_actuales']}).",
                ephemeral=True,
            )
            return

        me = interaction.guild.me
        if not me or not me.guild_permissions.manage_roles:
            await interaction.followup.send("El bot no tiene **Gestionar roles**.", ephemeral=True)
            return

        prefix = str(self.config.get("temp_role_prefix") or "★ ")[:16]
        clean = nombre_rol.strip().replace("@", "")[:80] or "Rol tienda"
        role_name = f"{prefix}{clean}"[:100]

        self.economia_db.modify_points(interaction.user.id, precio, gastar=True)
        role = None
        try:
            role = await interaction.guild.create_role(
                name=role_name,
                mentionable=False,
                reason=f"Tienda temporal — compra {interaction.user.id} → {usuario.id}",
            )
            try:
                if me.top_role.position > 1:
                    await role.edit(position=max(1, me.top_role.position - 1))
            except (discord.Forbidden, discord.HTTPException):
                pass
            await usuario.add_roles(role, reason="Rol temporal tienda")
            now = time.time()
            exp = now + days * 86400
            self.economia_db.register_temp_shop_role(
                interaction.guild.id,
                role.id,
                usuario.id,
                interaction.user.id,
                clean,
                now,
                exp,
                kind="shop",
            )
            await interaction.followup.send(
                f"✅ **-{precio}** pts. Rol {role.mention} → {usuario.mention} por **{days}** días.",
                ephemeral=True,
            )
        except discord.Forbidden:
            self.economia_db.modify_points(interaction.user.id, precio, gastar=False)
            if role:
                try:
                    await role.delete()
                except Exception:
                    pass
            await interaction.followup.send(
                "Sin permisos para crear/asignar roles. **Puntos devueltos.**",
                ephemeral=True,
            )
        except Exception as e:
            self.economia_db.modify_points(interaction.user.id, precio, gastar=False)
            if role:
                try:
                    await role.delete()
                except Exception:
                    pass
            log.exception("rol_temporal: %s", e)
            await interaction.followup.send(f"Error: {e}. **Puntos devueltos.**", ephemeral=True)

    @tasks.loop(hours=1)
    async def _expire_temp_roles(self):
        try:
            now = time.time()
            rows = self.economia_db.get_expired_temp_shop_roles(now)
            for row in rows:
                rid = int(row["id"])
                guild_id = int(row["guild_id"])
                role_id = int(row["role_id"])
                user_id = int(row["user_id"])
                kind = str(row.get("kind") or "shop")
                g = self.bot.get_guild(guild_id)
                if g:
                    role = g.get_role(role_id)
                    mem = g.get_member(user_id)
                    if mem and role and role in mem.roles:
                        try:
                            await mem.remove_roles(
                                role,
                                reason="Rol temporal — vencido (tienda o carta)",
                            )
                        except Exception:
                            pass
                    if kind == "shop" and role:
                        try:
                            await role.delete(reason="Rol temporal tienda — vencido")
                        except Exception:
                            pass
                self.economia_db.delete_temp_shop_role_row(rid)
        except Exception:
            log.exception("_expire_temp_roles")

    @_expire_temp_roles.before_loop
    async def _before_expire(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(TiendaCog(bot))
