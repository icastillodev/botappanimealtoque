import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import logging.handlers
import sys

# --- MODIFICADO: Importamos la CLASE V4 ---
from cogs.votacion.db_manager import PollDBManagerV4, DB_FILE
from cogs.votacion.poll_view import PollView

# 2. Cargar .env PRIMERO
load_dotenv()

# 3. Configurar el Logging
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
# -----------------------------------------------------
log.info("Logging configurado. Cargando variables de entorno...")

# 4. Cargar Tokens y Roles
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    log.critical("¡ERROR CRÍTICO! Falta DISCORD_TOKEN en .env")
    raise SystemExit("Falta DISCORD_TOKEN en .env")

HOKAGE_ID_STR = os.getenv("HOKAGE_ROLE_ID")
if not HOKAGE_ID_STR or not HOKAGE_ID_STR.isdigit():
    log.warning("HOKAGE_ROLE_ID no está en .env o no es un número. Los comandos de admin no funcionarán.")
    HOKAGE_ID = None
else:
    HOKAGE_ID = int(HOKAGE_ID_STR)
    log.info("HOKAGE_ROLE_ID cargado exitosamente.")

log.info("Token de Discord encontrado.")

# 5. Lista de Cogs
INITIAL_EXTENSIONS = [
    "cogs.presentaciones",
    "cogs.economy",
    "cogs.impostor",
    "cogs.clearchat",
    "cogs.votacion",
]

# 6. La Clase del Bot
class MiBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix="!", intents=intents)
        
        self.log = logging.getLogger(self.__class__.__name__)

        # --- MODIFICADO: Instanciamos la CLASE V4 ---
        self.log.info("Inicializando el manejador de base de datos (DBManagerV4)...")
        self.db_manager = PollDBManagerV4(db_path=DB_FILE)
        
        self.hokage_role_id = HOKAGE_ID

    async def setup_hook(self):
        """Esto se ejecuta ANTES de que el bot inicie sesión."""
        
        self.log.info("Cargando vistas persistentes de votaciones...")
        active_polls = self.db_manager.get_active_polls()
        
        for poll in active_polls:
            full_poll = self.db_manager.get_poll_data(poll['message_id'])
            options = full_poll.get('options')

            if options:
                # Al reiniciar, también creamos la vista con los botones de admin
                self.add_view(PollView(poll_options=options, db_manager=self.db_manager))
            else:
                self.log.warning(f"No se pudieron cargar opciones para la votación {poll['message_id']}")
        
        self.log.info(f"Cargadas {len(active_polls)} vistas de votación persistentes.")

        # --- Cargar Extensiones (Cogs) ---
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

    async def on_ready(self):
        self.log.info(f"Conectado como {self.user} (ID {self.user.id})")
        self.log.info("Bot listo y operativo.")
        
        try:
            synced = await self.tree.sync()
            self.log.info(f"Sincronizados {len(synced)} comandos (/) globalmente.")
        except Exception as e:
            self.log.exception(f"Error al sincronizar comandos: {e}")

# 7. El punto de entrada principal
async def main():
    bot = MiBot()
    async with bot:
        log.info("Iniciando conexión del bot a Discord...")
        await bot.start(TOKEN)

# 8. Ejecutar el bot
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log.critical(f"El bot se ha detenido por un error fatal: {e}")
        log.exception(e)