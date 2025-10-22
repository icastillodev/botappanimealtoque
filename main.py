import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import logging.handlers
import sys

# 1. Cargar .env PRIMERO
load_dotenv()

# 2. Configurar el Logging ANTES de hacer nada
# (Esto mostrará todo en tu consola)
log_level = logging.DEBUG # Nivel máximo de detalle

# Configurar el logger raíz (para nuestros cogs y este main.py)
root_logger = logging.getLogger()
root_logger.setLevel(log_level)

# Configurar el logger de discord.py
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.INFO) # INFO es bueno para discord

# Evitar el spam de http
http_logger = logging.getLogger('discord.http')
http_logger.setLevel(logging.WARNING)

# Crear el "handler" (a dónde va el log: la consola)
# sys.stdout es la consola (PowerShell)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(log_level)

# Crear el formato del log
formatter = logging.Formatter(
    '%(asctime)s - [%(levelname)s] - %(name)s: %(message)s', 
    '%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(formatter)

# Añadir el handler a los loggers
root_logger.addHandler(console_handler)

# Logger para este archivo main.py
log = logging.getLogger(__name__)

# -----------------------------------------------------
# AHORA COMIENZA EL CÓDIGO DE TU BOT
# -----------------------------------------------------

log.info("Logging configurado. Cargando variables de entorno...")

# 3. Cargar el Token
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    log.critical("¡ERROR CRÍTICO! Falta DISCORD_TOKEN en .env")
    raise SystemExit("Falta DISCORD_TOKEN en .env")

log.info("Token de Discord encontrado.")

# Intents
intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True # Requerido por cogs.presentaciones
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Carga de extensiones (cogs)    "cogs.invites",
INITIAL_EXTENSIONS = [
    "cogs.presentaciones",
    "cogs.economy",
    "cogs.impostor",
    "cogs.clearchat",
]

@bot.event
async def on_ready():
    log.info(f"Conectado como {bot.user} (ID {bot.user.id})")
    log.info("Bot listo y operativo.")

async def load_extensions():
    log.info("Iniciando carga de extensiones (cogs)...")
    for ext in INITIAL_EXTENSIONS:
        if ext in bot.extensions:
            log.warning(f"Extensión ya estaba cargada: {ext}")
            continue
        try:
            await bot.load_extension(ext)
            log.info(f"✅ Extensión cargada exitosamente: {ext}")
        except Exception as e:
            # log.exception() es como log.error() pero incluye el traceback completo
            log.exception(f"❌ Error cargando {ext}: {e}")

async def main():
    async with bot:
        await load_extensions()
        log.info("Iniciando conexión del bot a Discord...")
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log.critical(f"El bot se ha detenido por un error fatal: {e}")
        log.exception(e)