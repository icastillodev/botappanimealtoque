# main.py — botappanimealtoque (discord.py)
# Ejecutar: desde esta carpeta, con venv activado → python main.py
import os
import asyncio
import sys
import logging
import logging.handlers
import discord
from discord import app_commands
from discord.ext import commands
from typing import Any

from dotenv import load_dotenv

# --- Importamos Votacion (V5) ---
from cogs.votacion.db_manager import PollDBManagerV5, DB_FILE as POLL_DB_FILE
from cogs.votacion.poll_view import PollView

# --- Importamos Economia (V2) y Cartas ---
from cogs.economia.db_manager import EconomiaDBManagerV2, DB_FILE as ECON_DB_FILE
from cogs.economia.card_db_manager import CardDBManager, DB_FILE as CARD_DB_FILE

load_dotenv()

from env_loader import load_task_and_shop_config


def _parse_log_level(raw: str) -> int:
    name = (raw or "DEBUG").strip().upper()
    return getattr(logging, name, logging.DEBUG)


def _env_truthy(key: str) -> bool:
    return os.getenv(key, "").strip().lower() in ("1", "true", "yes", "on")

log_level = _parse_log_level(os.getenv("BOT_LOG_LEVEL", "DEBUG"))
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.INFO)
http_logger = logging.getLogger("discord.http")
http_logger.setLevel(logging.WARNING)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(log_level)
formatter = logging.Formatter(
    "%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
    "%Y-%m-%d %H:%M:%S",
)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)
log = logging.getLogger(__name__)

log.info(
    "Logging consola nivel=%s (cambia con BOT_LOG_LEVEL=INFO|DEBUG|WARNING). "
    "Comandos ? exitosos: DEBUG por defecto; BOT_LOG_PREFIX_COMMANDS=1 los muestra en INFO.",
    logging.getLevelName(log_level),
)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    log.critical("¡ERROR CRÍTICO! Falta DISCORD_TOKEN en .env")
    raise SystemExit("Falta DISCORD_TOKEN en .env")

HOKAGE_ID_STR = os.getenv("HOKAGE_ROLE_ID")
if not HOKAGE_ID_STR or not HOKAGE_ID_STR.isdigit():
    log.warning("HOKAGE_ROLE_ID no está en .env o no es un número.")
    HOKAGE_ID = None
else:
    HOKAGE_ID = int(HOKAGE_ID_STR)
    log.info("HOKAGE_ROLE_ID cargado exitosamente.")

log.info("Token de Discord encontrado.")

INITIAL_EXTENSIONS = [
    "cogs.presentaciones",
    "cogs.impostor",
    "cogs.clearchat",
    "cogs.votacion",
    "cogs.economia",
    "cogs.creador",
    "cogs.reaction_limiter",
    "cogs.check_tareas",
    "cogs.comandos_prefijo",
    "cogs.oraculo_cog",
    "cogs.channel_enforcer",
    "cogs.semanal_versus",
]

class MiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.message_content = True
        intents.members = True
        intents.messages = True     
        intents.reactions = True    
        
        # Prefijo de comandos de texto (por convivencia con otros bots del servidor)
        # case_insensitive: ?GUIA / ?guia — evita CommandNotFound silencioso en móviles con caps.
        super().__init__(command_prefix="?", intents=intents, case_insensitive=True)
        
        self.log = logging.getLogger(self.__class__.__name__)

        # --- DB Votacion (ESTO ARREGLA EL ERROR DE LA IMAGEN) ---
        self.log.info("Inicializando el manejador de base de datos (DBManagerV5)...")
        self.db_manager = PollDBManagerV5(db_path=POLL_DB_FILE)
        
        # --- DB Economia ---
        self.log.info("Inicializando el manejador de base de datos (EconomiaDBManagerV2)...")
        self.economia_db = EconomiaDBManagerV2(db_path=ECON_DB_FILE)
        
        self.log.info("Inicializando el manejador de base de datos (CardDBManager)...")
        self.card_db = CardDBManager(db_path=CARD_DB_FILE)
        
        self.hokage_role_id = HOKAGE_ID
        self.task_config, self.shop_config = load_task_and_shop_config(log)

    async def on_command_completion(self, ctx: commands.Context) -> None:
        cmd = ctx.command.name if ctx.command else "?"
        gid = ctx.guild.id if ctx.guild else None
        cid = ctx.channel.id if ctx.channel else None
        uid = ctx.author.id if ctx.author else None
        line = f"[?] OK comando={cmd} guild={gid} channel={cid} user={uid}"
        if _env_truthy("BOT_LOG_PREFIX_COMMANDS"):
            self.log.info(line)
        else:
            self.log.debug(line)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        cmd = ctx.command.name if ctx.command else "(desconocido)"
        gid = ctx.guild.id if ctx.guild else None
        cid = ctx.channel.id if ctx.channel else None
        uid = ctx.author.id if ctx.author else None
        base = f"[?] ERR comando={cmd} guild={gid} channel={cid} user={uid}"
        preview = ""
        if ctx.message and ctx.message.content:
            c = ctx.message.content
            preview = c if len(c) <= 220 else c[:220] + "..."

        if isinstance(error, commands.CommandNotFound):
            self.log.info("%s | CommandNotFound contenido=%r", base, preview)
            return
        if isinstance(error, commands.CommandOnCooldown):
            self.log.info("%s | cooldown retry_after=%.1fs", base, error.retry_after)
            return
        if isinstance(error, commands.MaxConcurrencyReached):
            self.log.warning("%s | MaxConcurrencyReached: %s", base, error)
            return
        if isinstance(error, commands.MissingRequiredArgument):
            self.log.warning("%s | falta argumento: %s", base, error.param.name)
            return
        if isinstance(error, commands.BadArgument):
            self.log.warning("%s | BadArgument: %s", base, error)
            return
        if isinstance(error, commands.CheckFailure):
            self.log.warning("%s | CheckFailure: %s", base, error)
            return
        if isinstance(error, commands.DisabledCommand):
            self.log.warning("%s | comando deshabilitado", base)
            return
        if isinstance(error, commands.UserInputError):
            self.log.warning("%s | UserInputError: %s", base, error)
            return
        if isinstance(error, commands.NoPrivateMessage):
            self.log.warning("%s | NoPrivateMessage", base)
            return
        if isinstance(error, commands.PrivateMessageOnly):
            self.log.warning("%s | PrivateMessageOnly", base)
            return
        if isinstance(error, commands.CommandInvokeError):
            orig = error.original
            self.log.error("%s | CommandInvokeError: %s: %s", base, type(orig).__name__, orig, exc_info=orig)
            return
        self.log.error("%s | %s: %s", base, type(error).__name__, error, exc_info=error)

    async def _log_slash_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        cmd = interaction.command.name if interaction.command else "(slash)"
        gid = interaction.guild_id
        cid = interaction.channel_id
        uid = interaction.user.id if interaction.user else None
        base = f"[/] ERR comando={cmd} guild={gid} channel={cid} user={uid}"
        if isinstance(error, app_commands.CommandInvokeError):
            orig = error.original
            self.log.error("%s | CommandInvokeError: %s: %s", base, type(orig).__name__, orig, exc_info=orig)
            return
        if isinstance(error, app_commands.MissingPermissions):
            self.log.warning("%s | MissingPermissions: %s", base, list(error.missing_permissions))
            return
        if isinstance(error, app_commands.BotMissingPermissions):
            self.log.warning("%s | BotMissingPermissions: %s", base, list(error.missing_permissions))
            return
        if isinstance(error, app_commands.CheckFailure):
            self.log.warning("%s | CheckFailure: %s", base, error)
            return
        if isinstance(error, app_commands.TransformerError):
            self.log.warning("%s | TransformerError: %s", base, error)
            return
        if isinstance(error, app_commands.CommandOnCooldown):
            self.log.info("%s | cooldown retry_after=%.1fs", base, error.retry_after)
            return
        self.log.error("%s | %s: %s", base, type(error).__name__, error, exc_info=error)

    async def on_error(self, event_method: str, /, *args: Any, **kwargs: Any) -> None:
        # Un solo traceback en consola (evita duplicar con super().on_error del cliente).
        self.log.exception(
            "[discord evento] Falló %r | args=%d kwargs=%s",
            event_method,
            len(args),
            list(kwargs.keys()),
        )

    async def setup_hook(self):
        self.log.info("Cargando vistas persistentes de votaciones...")
        active_polls = self.db_manager.get_active_polls()
        
        for poll in active_polls:
            full_poll = self.db_manager.get_poll_data(poll['message_id'])
            options = full_poll.get('options')
            if options:
                self.add_view(PollView(poll_options=options, db_manager=self.db_manager))
            else:
                self.log.warning(f"No se pudieron cargar opciones para la votación {poll['message_id']}")
        self.log.info(f"Cargadas {len(active_polls)} vistas de votación persistentes.")

        self.log.info("Iniciando carga de extensiones (cogs)...")
        for ext in INITIAL_EXTENSIONS:
            if ext in self.extensions:
                self.log.warning(f"Extensión ya estaba cargada: {ext}")
                continue
            try:
                await self.load_extension(ext)
                self.log.info(f"✅ Extensión cargada exitosamente: {ext}")
            except Exception as e:
                self.log.exception(f"❌ Error cargando {ext}: {e}")

        # Slash: una sola vez al arrancar (evita re-sync en cada on_ready → duplicados / ruido en el cliente)
        try:
            synced = await self.tree.sync()
            self.log.info(f"Sincronizados {len(synced)} comandos (/) globalmente (setup_hook).")
            try:
                slash_names = sorted({c.qualified_name for c in self.tree.walk_commands()})
                preview = ", ".join(slash_names[:80])
                if len(slash_names) > 80:
                    preview += f" … (+{len(slash_names) - 80} más)"
                self.log.info("Slash registrados (qualified_name): %s", preview)
            except Exception as ex:
                self.log.debug("No se pudo enumerar slash con walk_commands: %s", ex)
            self.log.info(
                "Nota: los comandos globales pueden tardar hasta ~1 h en actualizarse en todos los clientes; "
                "reiniciar Discord suele ayudar. Para probar al instante, definí DISCORD_DEV_GUILD_ID (servidor de prueba)."
            )
            dev_gid = (os.getenv("DISCORD_DEV_GUILD_ID") or "").strip()
            if dev_gid.isdigit() and hasattr(self.tree, "copy_global_to"):
                g = discord.Object(id=int(dev_gid))
                self.tree.copy_global_to(guild=g)
                gsync = await self.tree.sync(guild=g)
                self.log.info(
                    "Sync en servidor de desarrollo (guild %s): %s comandos (visibles al momento en ese servidor).",
                    dev_gid,
                    len(gsync),
                )
            elif dev_gid.isdigit():
                self.log.warning(
                    "DISCORD_DEV_GUILD_ID ignorado: falta CommandTree.copy_global_to (actualizá discord.py / py-cord)."
                )
        except Exception as e:
            self.log.exception(f"Error al sincronizar comandos: {e}")

        async def _slash_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
            await self._log_slash_tree_error(interaction, error)

        self.tree.error(_slash_tree_error)
        self.log.info("Registrado handler de errores del CommandTree (slash /).")

    async def on_ready(self):
        self.log.info(f"Conectado como {self.user} (ID {self.user.id})")
        self.log.info(
            "Intents: message_content=%s — si en el servidor el texto de los mensajes llega vacío, "
            "activá **Message Content Intent** en https://discord.com/developers/applications → tu app → Bot → "
            "Privileged Gateway Intents, guardá y reiniciá el bot.",
            getattr(self.intents, "message_content", False),
        )
        self.log.info("Bot listo y operativo.")

async def main():
    bot = MiBot()
    if bot.task_config is None or bot.shop_config is None:
        log.critical("El bot no puede arrancar. Revisa los errores de configuración del .env")
        return

    async with bot:
        log.info("Iniciando conexión del bot a Discord...")
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log.critical(f"El bot se ha detenido por un error fatal: {e}")
        log.exception(e)