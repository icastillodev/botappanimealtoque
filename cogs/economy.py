# cogs/economy.py
import os
import time
from typing import List, Tuple, Optional

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite

# ======================
#        ENV
# ======================
DB_PATH = os.getenv("ECONOMY_DB_PATH", "./data/economy.db")
CURRENCY = os.getenv("ECONOMY_CURRENCY", "🌀")
ECONOMY_CHANNEL_ID = int(os.getenv("ECONOMY_CHANNEL_ID", "0"))

# Roles
HOKAGE_ROLE_ID = int(os.getenv("HOKAGE_ROLE_ID", "0"))     # admin
CHUNIN_ROLE_ID = int(os.getenv("CHUNIN_ROLE_ID", "0"))     # marca “presentado” en iniciación
EXCLUDED_ROLE_IDS = [int(x) for x in os.getenv("ECONOMY_EXCLUDED_ROLE_IDS", "").split(",") if x.strip().isdigit()]

# Reclamo cada 30'
CLAIM_COOLDOWN_SEC = 30 * 60
CLAIM_AMOUNT = 5

# Leaderboard
LEADERBOARD_SIZE = int(os.getenv("LEADERBOARD_SIZE", "10"))

# Slash sync rápido en tu guild
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

# Canal de sugerencias
SUGGESTIONS_CHANNEL_ID = int(os.getenv("SUGGESTIONS_CHANNEL_ID", "0"))

# Helpers
def _parse_id_list(s: str) -> List[int]:
    return [int(x) for x in s.split(",") if x.strip().isdigit()]

# ======================
#     DIARIAS
# ======================
DAILY_COMMENT_TARGET = int(os.getenv("DAILY_COMMENT_TARGET", "5"))
DAILY_COMMENT_POINTS = int(os.getenv("DAILY_COMMENT_POINTS", "50"))

DAILY_VIDEO_CHANNEL_ID = int(os.getenv("DAILY_VIDEO_CHANNEL_ID", "0"))
DAILY_VIDEO_REACT_POINTS = int(os.getenv("DAILY_VIDEO_REACT_POINTS", "30"))

# Wordle (diaria)
WORDLE_CHANNEL_ID = int(os.getenv("WORDLE_CHANNEL_ID", "0"))
WORDLE_POINTS = int(os.getenv("WORDLE_POINTS", "50"))

# ======================
#    SEMANALES
# ======================
WEEKLY_THREAD_CHANNEL_IDS = _parse_id_list(os.getenv("WEEKLY_THREAD_CHANNEL_IDS", ""))
WEEKLY_MEDIA_CHANNEL_IDS  = _parse_id_list(os.getenv("WEEKLY_MEDIA_CHANNEL_IDS", ""))
WEEKLY_THREAD_POINTS = int(os.getenv("WEEKLY_THREAD_POINTS", "80"))
WEEKLY_MEDIA_POINTS  = int(os.getenv("WEEKLY_MEDIA_POINTS", "80"))

# ======================
#    INICIACIÓN
# ======================
INIT_PRESENTED_POINTS = int(os.getenv("INIT_PRESENTED_POINTS", "50"))

INIT_SOCIALS_MESSAGE_ID = int(os.getenv("INIT_SOCIALS_MESSAGE_ID", "0"))
INIT_SOCIALS_POINTS     = int(os.getenv("INIT_SOCIALS_POINTS", "50"))
INIT_SOCIALS_CHANNEL_ID = int(os.getenv("INIT_SOCIALS_CHANNEL_ID", "0"))  # para mostrar “Cat > canal”

INIT_THREAD_CHANNEL_IDS = _parse_id_list(os.getenv("INIT_THREAD_CHANNEL_IDS", ""))
INIT_THREAD_POINTS      = int(os.getenv("INIT_THREAD_POINTS", "50"))

INIT_MEDIA_CHANNEL_IDS  = _parse_id_list(os.getenv("INIT_MEDIA_CHANNEL_IDS", ""))
INIT_MEDIA_POINTS       = int(os.getenv("INIT_MEDIA_POINTS", "50"))

INIT_RULES_MESSAGE_ID   = int(os.getenv("INIT_RULES_MESSAGE_ID", "0"))
INIT_RULES_POINTS       = int(os.getenv("INIT_RULES_POINTS", "50"))
INIT_RULES_CHANNEL_ID   = int(os.getenv("INIT_RULES_CHANNEL_ID", "0"))    # para mostrar “Cat > canal”

# ======================
#     INCLUDES
# ======================
from economy import diarias as eco_daily
from economy import semanales as eco_weekly
from economy import recompensas as shop

# Claves de iniciación
INIT_TASK_PRESENTED = "init_presented"
INIT_TASK_SOCIALS   = "init_socials_react"
INIT_TASK_THREAD    = "init_first_thread_comment"
INIT_TASK_MEDIA     = "init_first_media_post"
INIT_TASK_RULES     = "init_rules_react"


class EconomyCog(commands.Cog):
    """Economía: reclamo 30', scoreboard, diarias/semanales, Wordle, iniciación y tienda de recompensas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[aiosqlite.Connection] = None

    # ---------- helpers permisos/canales ----------
    @staticmethod
    def _is_admin(member: discord.Member) -> bool:
        return HOKAGE_ROLE_ID and any(r.id == HOKAGE_ROLE_ID for r in member.roles)

    @staticmethod
    def _is_excluded(member: discord.Member) -> bool:
        if member.bot:
            return True
        if EXCLUDED_ROLE_IDS and any(r.id in EXCLUDED_ROLE_IDS for r in member.roles):
            return True
        return False

    @staticmethod
    def _channel_ok(inter: discord.Interaction) -> bool:
        return (not ECONOMY_CHANNEL_ID) or (inter.channel_id == ECONOMY_CHANNEL_ID)

    def _channel_path(self, guild: discord.Guild, channel_id: int) -> str:
        ch = guild.get_channel(channel_id)
        if not ch:
            return f"<#{channel_id}>"
        cat = getattr(ch, "category", None)
        if cat:
            return f"{cat.name} > {ch.name}"
        return f"#{ch.name}"

    # ---------- DB ----------
    async def _init_db(self):
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        self.db = await aiosqlite.connect(DB_PATH)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                points      INTEGER NOT NULL DEFAULT 0,
                last_claim  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS progress (
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                scope       TEXT    NOT NULL,            -- 'daily' | 'weekly' | 'init'
                task        TEXT    NOT NULL,
                period_key  TEXT    NOT NULL,            -- YYYY-MM-DD | YYYY-WW | 'once'
                value       INTEGER NOT NULL DEFAULT 0,
                completed   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, scope, task, period_key)
            )
        """)
        await self.db.commit()

    async def _ensure_db(self):
        if self.db is None:
            await self._init_db()

    async def _ensure_user(self, guild_id: int, user_id: int):
        assert self.db is not None
        await self.db.execute(
            "INSERT INTO users (guild_id, user_id) VALUES (?, ?) ON CONFLICT(guild_id, user_id) DO NOTHING",
            (guild_id, user_id)
        )
        await self.db.commit()

    async def _get_user(self, guild_id: int, user_id: int) -> Tuple[int, int]:
        assert self.db is not None
        await self._ensure_user(guild_id, user_id)
        async with self.db.execute(
            "SELECT points, last_claim FROM users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            return (int(row[0]), int(row[1])) if row else (0, 0)

    async def _set_points(self, guild_id: int, user_id: int, pts: int):
        assert self.db is not None
        await self.db.execute(
            "UPDATE users SET points = ? WHERE guild_id = ? AND user_id = ?",
            (max(0, int(pts)), guild_id, user_id)
        )
        await self.db.commit()

    async def _add_points(self, guild_id: int, user_id: int, delta: int) -> int:
        pts, _ = await self._get_user(guild_id, user_id)
        new_pts = max(0, pts + int(delta))
        await self._set_points(guild_id, user_id, new_pts)
        return new_pts

    async def _set_last_claim(self, guild_id: int, user_id: int, ts: int):
        assert self.db is not None
        await self.db.execute(
            "UPDATE users SET last_claim = ? WHERE guild_id = ? AND user_id = ?",
            (int(ts), guild_id, user_id)
        )
        await self.db.commit()

    # --- progress helpers ---
    async def _get_progress(self, guild_id: int, user_id: int, scope: str, task: str, period_key: str) -> Tuple[int, bool]:
        assert self.db is not None
        await self.db.execute(
            "INSERT INTO progress (guild_id,user_id,scope,task,period_key) VALUES (?,?,?,?,?) "
            "ON CONFLICT(guild_id,user_id,scope,task,period_key) DO NOTHING",
            (guild_id, user_id, scope, task, period_key)
        )
        await self.db.commit()
        async with self.db.execute(
            "SELECT value, completed FROM progress WHERE guild_id=? AND user_id=? AND scope=? AND task=? AND period_key=?",
            (guild_id, user_id, scope, task, period_key)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return int(row[0]), bool(row[1])
            return 0, False

    async def _set_progress(self, guild_id: int, user_id: int, scope: str, task: str, period_key: str, value: int, completed: bool):
        assert self.db is not None
        await self.db.execute(
            """
            INSERT INTO progress (guild_id,user_id,scope,task,period_key,value,completed)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(guild_id,user_id,scope,task,period_key)
            DO UPDATE SET value=excluded.value, completed=excluded.completed
            """,
            (guild_id, user_id, scope, task, period_key, int(value), 1 if completed else 0)
        )
        await self.db.commit()

    async def _complete_init_once(self, guild_id: int, user_id: int, task_key: str, reward: int) -> bool:
        """Marca una tarea de iniciación ('once') y otorga puntos si no estaba hecha."""
        _, done = await self._get_progress(guild_id, user_id, "init", task_key, "once")
        if done:
            return False
        await self._set_progress(guild_id, user_id, "init", task_key, "once", 1, True)
        await self._add_points(guild_id, user_id, reward)
        return True

    # ---------- lifecycle ----------
    @commands.Cog.listener()
    async def on_ready(self):
        await self._ensure_db()
        # Sync slash
        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                self.bot.tree.copy_global_to(guild=guild)
                await self.bot.tree.sync(guild=guild)
            else:
                await self.bot.tree.sync()
        except Exception as e:
            print("Slash sync error:", e)

    # ---------- EVENTOS ----------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorar DMs/bots
        if message.author.bot or message.guild is None:
            return

        await self._ensure_db()

        # DIARIA: comentar X veces
        try:
            await eco_daily.incrementar_comentario(
                self.db.execute, self.db.commit,  # type: ignore
                self._get_progress, self._set_progress, self._add_points,
                message.guild.id, message.author.id,
                DAILY_COMMENT_TARGET, DAILY_COMMENT_POINTS
            )
        except Exception:
            pass

        # DIARIA: WORDLE (cualquier mensaje en el canal de Wordle cuenta 1 vez por día)
        if WORDLE_CHANNEL_ID and isinstance(message.channel, discord.TextChannel):
            if message.channel.id == WORDLE_CHANNEL_ID:
                try:
                    await eco_daily.completar_wordle(
                        self._get_progress, self._set_progress, self._add_points,
                        message.guild.id, message.author.id, WORDLE_POINTS
                    )
                except Exception:
                    pass

        # SEMANAL MEDIA + INICIACIÓN MEDIA (primer post con adjunto en memes/cosplay/fanart)
        if isinstance(message.channel, discord.TextChannel) and (message.attachments or message.stickers):
            ch_id = message.channel.id
            # semanal
            if WEEKLY_MEDIA_CHANNEL_IDS and ch_id in WEEKLY_MEDIA_CHANNEL_IDS:
                try:
                    await eco_weekly.completar_media(
                        self._get_progress, self._set_progress, self._add_points,
                        message.guild.id, message.author.id, WEEKLY_MEDIA_POINTS
                    )
                except Exception:
                    pass
            # iniciación (si se configuró)
            if INIT_MEDIA_CHANNEL_IDS and ch_id in INIT_MEDIA_CHANNEL_IDS:
                try:
                    await self._complete_init_once(message.guild.id, message.author.id, INIT_TASK_MEDIA, INIT_MEDIA_POINTS)
                except Exception:
                    pass

        # INICIACIÓN: primer comentario en thread de anime/manga (mensaje dentro de un thread)
        if isinstance(message.channel, discord.Thread):
            parent = message.channel.parent
            parent_id = getattr(parent, "id", None)
            if parent_id and (parent_id in INIT_THREAD_CHANNEL_IDS):
                try:
                    await self._complete_init_once(message.guild.id, message.author.id, INIT_TASK_THREAD, INIT_THREAD_POINTS)
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Diaria: reaccionar en canal de videos (cualquier emoji)
        if DAILY_VIDEO_CHANNEL_ID and payload.channel_id == DAILY_VIDEO_CHANNEL_ID:
            if payload.guild_id and payload.user_id:
                guild = self.bot.get_guild(payload.guild_id)
                if guild:
                    member = guild.get_member(payload.user_id)
                    if member and not member.bot:
                        try:
                            await self._ensure_db()
                            await eco_daily.completar_video(
                                self.db.execute, self.db.commit,  # type: ignore
                                self._get_progress, self._set_progress, self._add_points,
                                guild.id, member.id, DAILY_VIDEO_REACT_POINTS
                            )
                        except Exception:
                            pass

        # Iniciación: reacción a 'redes' (cualquier emoji)
        if INIT_SOCIALS_MESSAGE_ID and payload.message_id == INIT_SOCIALS_MESSAGE_ID:
            if payload.guild_id and payload.user_id:
                guild = self.bot.get_guild(payload.guild_id)
                member = guild.get_member(payload.user_id) if guild else None
                if member and not member.bot:
                    try:
                        await self._complete_init_once(guild.id, member.id, INIT_TASK_SOCIALS, INIT_SOCIALS_POINTS)
                    except Exception:
                        pass

        # Iniciación: reacción a 'reglas' (cualquier emoji)
        if INIT_RULES_MESSAGE_ID and payload.message_id == INIT_RULES_MESSAGE_ID:
            if payload.guild_id and payload.user_id:
                guild = self.bot.get_guild(payload.guild_id)
                member = guild.get_member(payload.user_id) if guild else None
                if member and not member.bot:
                    try:
                        await self._complete_init_once(guild.id, member.id, INIT_TASK_RULES, INIT_RULES_POINTS)
                    except Exception:
                        pass

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        # SEMANAL: abrir thread (ya implementado)
        if WEEKLY_THREAD_CHANNEL_IDS:
            parent = thread.parent
            parent_id = getattr(parent, "id", None)
            if parent_id in WEEKLY_THREAD_CHANNEL_IDS:
                creator_id = getattr(thread, "owner_id", None)
                if not creator_id and getattr(thread, "owner", None) is not None:
                    creator_id = thread.owner.id  # type: ignore
                if creator_id:
                    member = thread.guild.get_member(creator_id)
                    if member and not member.bot:
                        try:
                            await self._ensure_db()
                            await eco_weekly.completar_thread(
                                self._get_progress, self._set_progress, self._add_points,
                                thread.guild.id, member.id, WEEKLY_THREAD_POINTS
                            )
                        except Exception:
                            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # INICIACIÓN: presentado → cuando gana el rol CHŪNIN
        if CHUNIN_ROLE_ID == 0:
            return
        before_ids = {r.id for r in before.roles}
        after_ids  = {r.id for r in after.roles}
        if (CHUNIN_ROLE_ID not in before_ids) and (CHUNIN_ROLE_ID in after_ids):
            try:
                await self._ensure_db()
                await self._complete_init_once(after.guild.id, after.id, INIT_TASK_PRESENTED, INIT_PRESENTED_POINTS)
            except Exception:
                pass

    # =========================
    #       SLASH COMMANDS
    # =========================
    @app_commands.command(name="scoreboard", description="Ver el ranking de puntos del servidor")
    async def scoreboard(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)

        await self._ensure_db()
        assert self.db is not None
        async with self.db.execute(
            "SELECT user_id, points FROM users WHERE guild_id = ? ORDER BY points DESC LIMIT ?",
            (interaction.guild_id, LEADERBOARD_SIZE)  # type: ignore
        ) as cur:
            rows = await cur.fetchall()

        if not rows:
            return await interaction.response.send_message("🏆 **Scoreboard**\nAún no hay registros.", ephemeral=True)

        lines = []
        for i, (uid, pts) in enumerate(rows, start=1):
            member = interaction.guild.get_member(uid) if interaction.guild else None
            name = member.display_name if member else f"User {uid}"
            lines.append(f"**{i}.** {name} — {CURRENCY} {pts}")

        await interaction.response.send_message("🏆 **Scoreboard**\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="reclamar", description=f"Reclamá {CLAIM_AMOUNT} cada 30 minutos")
    async def reclamar(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Solo en servidores.", ephemeral=True)
        if self._is_excluded(interaction.user):
            return await interaction.response.send_message("Tu rol actual no puede reclamar puntos.", ephemeral=True)

        await self._ensure_db()
        guild_id = interaction.guild_id
        user_id = interaction.user.id
        pts, last_claim = await self._get_user(guild_id, user_id)  # type: ignore

        now = int(time.time())
        elapsed = now - last_claim
        if elapsed < CLAIM_COOLDOWN_SEC:
            mins, secs = divmod(CLAIM_COOLDOWN_SEC - elapsed, 60)
            return await interaction.response.send_message(
                f"⏳ Te faltan **{mins}m {secs}s** para volver a reclamar.", ephemeral=True
            )

        new_pts = await self._add_points(guild_id, user_id, CLAIM_AMOUNT)  # type: ignore
        await self._set_last_claim(guild_id, user_id, now)
        await interaction.response.send_message(
            f"✅ Reclamo realizado: **+{CURRENCY} {CLAIM_AMOUNT}**\n"
            f"Nuevo saldo: **{CURRENCY} {new_pts}**",
            ephemeral=True
        )

    @app_commands.command(name="puntos", description="Ver tu saldo actual de puntos")
    async def puntos(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)
        await self._ensure_db()
        pts, _ = await self._get_user(interaction.guild_id, interaction.user.id)  # type: ignore
        await interaction.response.send_message(f"Tu saldo: **{CURRENCY} {pts}**", ephemeral=True)

    @app_commands.command(name="diarias", description="Ver tu progreso de diarias")
    async def diarias(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)
        await self._ensure_db()
        txt = await eco_daily.render_diarias(
            self._get_progress, interaction.guild_id, interaction.user.id,  # type: ignore
            DAILY_COMMENT_TARGET, DAILY_COMMENT_POINTS,
            DAILY_VIDEO_CHANNEL_ID, DAILY_VIDEO_REACT_POINTS,
            WORDLE_CHANNEL_ID, WORDLE_POINTS
        )
        await interaction.response.send_message(txt, ephemeral=True)

    @app_commands.command(name="semanales", description="Ver tu progreso de semanales")
    async def semanales(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)
        await self._ensure_db()
        txt = await eco_weekly.render_semanales(
            self._get_progress, interaction.guild_id, interaction.user.id,  # type: ignore
            WEEKLY_THREAD_CHANNEL_IDS, WEEKLY_MEDIA_CHANNEL_IDS,
            WEEKLY_THREAD_POINTS, WEEKLY_MEDIA_POINTS
        )
        await interaction.response.send_message(txt, ephemeral=True)

    @app_commands.command(name="iniciacion", description="Ver tu progreso de iniciación (tareas one-shot)")
    async def iniciacion(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)

        await self._ensure_db()
        guild = interaction.guild
        guild_id = interaction.guild_id
        user_id = interaction.user.id  # type: ignore

        async def done(task_key: str) -> bool:
            _, completed = await self._get_progress(guild_id, user_id, "init", task_key, "once")  # type: ignore
            return completed

        # Presentación
        d_present = await done(INIT_TASK_PRESENTED)
        line_present = f"- **Presentación** (obtener rol Chūnin) — {'✅' if d_present else '❌'} (+{INIT_PRESENTED_POINTS})"

        # Redes
        if INIT_SOCIALS_MESSAGE_ID:
            lugar_txt = (
                self._channel_path(guild, INIT_SOCIALS_CHANNEL_ID)
                if guild and INIT_SOCIALS_CHANNEL_ID else f"mensaje {INIT_SOCIALS_MESSAGE_ID}"
            )
            d_socials = await done(INIT_TASK_SOCIALS)
            line_socials = f"- **Reaccionar a redes** en **{lugar_txt}** — {'✅' if d_socials else '❌'} (+{INIT_SOCIALS_POINTS})"
        else:
            line_socials = "- **Reaccionar a redes** — *(mensaje no configurado)*"

        # Thread anime/manga
        if INIT_THREAD_CHANNEL_IDS:
            d_thread = await done(INIT_TASK_THREAD)
            if guild:
                chs = " / ".join(self._channel_path(guild, cid) for cid in INIT_THREAD_CHANNEL_IDS)
            else:
                chs = " / ".join(f"<#{cid}>" for cid in INIT_THREAD_CHANNEL_IDS)
            line_thread = f"- **Comentar por primera vez en un thread** ({chs}) — {'✅' if d_thread else '❌'} (+{INIT_THREAD_POINTS})"
        else:
            line_thread = "- **Comentar por primera vez en un thread** — *(canales no configurados)*"

        # Media (meme/cosplay/fanart)
        if INIT_MEDIA_CHANNEL_IDS:
            d_media = await done(INIT_TASK_MEDIA)
            if guild:
                chs2 = " / ".join(self._channel_path(guild, cid) for cid in INIT_MEDIA_CHANNEL_IDS)
            else:
                chs2 = " / ".join(f"<#{cid}>" for cid in INIT_MEDIA_CHANNEL_IDS)
            line_media = f"- **Publicar por primera vez un meme/cosplay/fanart** ({chs2}) — {'✅' if d_media else '❌'} (+{INIT_MEDIA_POINTS})"
        else:
            line_media = "- **Publicar por primera vez un meme/cosplay/fanart** — *(canales no configurados)*"

        # Reglas
        if INIT_RULES_MESSAGE_ID:
            lugar_txt = (
                self._channel_path(guild, INIT_RULES_CHANNEL_ID)
                if guild and INIT_RULES_CHANNEL_ID else f"mensaje {INIT_RULES_MESSAGE_ID}"
            )
            d_rules = await done(INIT_TASK_RULES)
            line_rules = f"- **Reaccionar a las reglas** en **{lugar_txt}** — {'✅' if d_rules else '❌'} (+{INIT_RULES_POINTS})"
        else:
            line_rules = "- **Reaccionar a las reglas** — *(mensaje no configurado)*"

        txt = "🆕 **Iniciación** (tareas únicas)\n" + "\n".join([
            line_present,
            line_socials,
            line_thread,
            line_media,
            line_rules,
        ])
        await interaction.response.send_message(txt, ephemeral=True)

    # ====== TIENDA ======
    @app_commands.command(name="tienda", description="Ver la tienda de recompensas")
    async def tienda(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)
        items = shop.get_shop_items()
        await interaction.response.send_message(shop.format_shop(items), ephemeral=True)

    @app_commands.command(name="canjear", description="Canjear una recompensa")
    @app_commands.describe(
        recompensa="Qué querés canjear",
        message_link="(Solo 'Mensaje fijo') link completo del mensaje tuyo en el canal general",
        encuesta="(Solo 'Proponer encuesta') texto de la propuesta"
    )
    @app_commands.choices(
        recompensa=[
            app_commands.Choice(name="🩸 Rol Akatsuki", value="role_akatsuki"),
            app_commands.Choice(name="🍃 Rol Jōnin",    value="role_jonin"),
            app_commands.Choice(name="💬 Mensaje fijo", value="pin_message"),
            app_commands.Choice(name="🍥 Proponer encuesta", value="poll_propose"),
        ]
    )
    async def canjear(
        self,
        interaction: discord.Interaction,
        recompensa: app_commands.Choice[str],
        message_link: Optional[str] = None,
        encuesta: Optional[str] = None
    ):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)

        await self._ensure_db()
        try:
            text = await shop.redeem(
                self, interaction, recompensa.value,
                message_link=message_link, poll_text=encuesta
            )
        except ValueError as e:
            return await interaction.response.send_message(f"❌ {e}", ephemeral=True)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Me faltan permisos para completar el canje.", ephemeral=True)
        except Exception:
            return await interaction.response.send_message("❌ Ocurrió un error al procesar el canje.", ephemeral=True)

        await interaction.response.send_message(f"✅ {text}", ephemeral=True)

    # ====== EXTRAS ======
    @app_commands.command(name="especiales", description="Ver tareas especiales")
    async def especiales(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)
        await interaction.response.send_message("✨ **Especiales**\nPor ahora no hay tareas especiales.", ephemeral=True)

    @app_commands.command(name="eventos", description="Ver eventos activos")
    async def eventos(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)
        await interaction.response.send_message("🎉 **Eventos**\nNo hay eventos activos.", ephemeral=True)

    @app_commands.command(name="info", description="Cómo funciona el sistema de economía")
    async def info(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)
        await interaction.response.send_message(
            "ℹ️ **Economía**\n"
            f"- Reclamo cada 30': **{CURRENCY} {CLAIM_AMOUNT}** (`/reclamar`).\n"
            f"- **Diarias**: comentar {DAILY_COMMENT_TARGET} (+{DAILY_COMMENT_POINTS}), reaccionar video (+{DAILY_VIDEO_REACT_POINTS}), Wordle (+{WORDLE_POINTS}).\n"
            f"- **Semanales**: abrir thread (+{WEEKLY_THREAD_POINTS}), subir media (+{WEEKLY_MEDIA_POINTS}).\n"
            "- **Iniciación**: presentado, reaccionar redes, primer comentario en thread, primer media, reaccionar reglas (cada una +50, una sola vez).\n"
            "- **Tienda**: `/tienda` para ver y `/canjear` para usar tus puntos.\n"
            "- Todo se resetea por día/semana automáticamente. Respuestas *ephemeral*.",
            ephemeral=True
        )

    @app_commands.command(name="comandos", description="Lista de comandos disponibles")
    async def comandos(self, interaction: discord.Interaction):
        if not self._channel_ok(interaction):
            return await interaction.response.send_message("Usá este comando en el canal de economía.", ephemeral=True)
        await interaction.response.send_message(
            "**Comandos**\n"
            "- `/reclamar` — reclamar puntos cada 30 min\n"
            "- `/puntos` — ver tu saldo\n"
            "- `/scoreboard` — ranking\n"
            "- `/diarias` — ver diarias\n"
            "- `/semanales` — ver semanales\n"
            "- `/iniciacion` — progreso de iniciación\n"
            "- `/tienda` — ver recompensas\n"
            "- `/canjear` — canjear una recompensa\n"
            "- `/especiales`, `/eventos`, `/info`\n"
            "- `/proximamente`, `/sugerencia`",
            ephemeral=True
        )

    # ====== NUEVOS ======
    @app_commands.command(name="proximamente", description="Mirá lo que se viene al servidor y al bot")
    async def proximamente(self, interaction: discord.Interaction):
        # libre de canal
        texto = (
            "🛠️ **Próximamente**\n"
            "\n"
            "🎮 **Juegos**\n"
            "• Piedra, papel o tijera\n"
            "• Moneda (coin flip)\n"
            "• Wordle (en web o en Discord)\n"
            "• /random (número más alto, etc.)\n"
            "• Juego del impostor\n"
            "• Piedra, papel o tijera **ranked**\n"
            "\n"
            "🖼️ **Coleccionables**\n"
            "• Imágenes/ítems coleccionables\n"
            "\n"
            "🎟️ **Recompensas especiales**\n"
            "• Canje mensual de **Crunchyroll**\n"
        )
        await interaction.response.send_message(texto, ephemeral=True)

    @app_commands.command(name="sugerencia", description="Dejá una sugerencia para el bot/servidor")
    @app_commands.describe(texto="Tu idea (será enviada al canal de sugerencias)")
    async def sugerencia(self, interaction: discord.Interaction, texto: str):
        if not texto or len(texto.strip()) < 5:
            return await interaction.response.send_message(
                "Escribí una sugerencia un poco más detallada (min. 5 caracteres).",
                ephemeral=True
            )

        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("Usá este comando dentro del servidor.", ephemeral=True)

        if SUGGESTIONS_CHANNEL_ID == 0:
            return await interaction.response.send_message(
                "El canal de sugerencias no está configurado. Pedile a un admin que setee `SUGGESTIONS_CHANNEL_ID` en .env.",
                ephemeral=True
            )

        ch = guild.get_channel(SUGGESTIONS_CHANNEL_ID)
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message(
                "No encuentro el canal de sugerencias configurado.",
                ephemeral=True
            )

        autor = interaction.user.mention
        msg = await ch.send(f"💡 **Sugerencia de {autor}:**\n> {texto.strip()}")
        try:
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
        except Exception:
            pass

        await interaction.response.send_message(
            f"¡Gracias! Tu sugerencia fue enviada a {ch.mention} 👍",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
