# main.py — botappanimealtoque (discord.py)
# Ejecutar: desde esta carpeta, con venv activado → python main.py
import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import logging.handlers
import sys

# --- Importamos Votacion (V5) ---
from cogs.votacion.db_manager import PollDBManagerV5, DB_FILE as POLL_DB_FILE
from cogs.votacion.poll_view import PollView

# --- Importamos Economia (V2) y Cartas ---
from cogs.economia.db_manager import EconomiaDBManagerV2, DB_FILE as ECON_DB_FILE
from cogs.economia.card_db_manager import CardDBManager, DB_FILE as CARD_DB_FILE

load_dotenv()

from env_loader import load_task_and_shop_config

log_level = logging.DEBUG
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.INFO)
http_logger = logging.getLogger('discord.http')
http_logger.setLevel(logging.WARNING)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(log_level)
formatter = logging.Formatter(
    '%(asctime)s - [%(levelname)s] - %(name)s: %(message)s', 
    '%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)
log = logging.getLogger(__name__)

log.info("Logging configurado. Cargando variables de entorno...")

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
        super().__init__(command_prefix="?", intents=intents)
        
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
        except Exception as e:
            self.log.exception(f"Error al sincronizar comandos: {e}")

    async def on_ready(self):
        self.log.info(f"Conectado como {self.user} (ID {self.user.id})")
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