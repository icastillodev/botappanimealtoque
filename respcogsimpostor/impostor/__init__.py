# cogs/impostor/__init__.py

import asyncio
from discord.ext import commands
import logging

# Lista de los módulos (archivos .py) dentro de cogs/impostor/ que
# definen su propia función setup() y son Cogs de discord.py.
# (Omitimos los archivos de utilidad como engine.py, core.py, chars.py)
SUB_COGS = [
    "feed",
    "lobby",
    "bots",
    "game_core",
    "roles",
    "turns",
    "votes",
    "endgame",
    "clean",
    "help", 
]
# Configura un logger específico para este paquete, si lo deseas
log = logging.getLogger(__name__)


async def setup(bot: commands.Bot):
    """
    Función setup principal llamada por discord.py cuando 
    se carga la extensión 'cogs.impostor'.
    
    Esta función cargará todos los sub-cogs.
    """
    print("---------------------------------")
    print("Cargando paquete: cogs.impostor")
    
    loaded_count = 0
    failed_count = 0

    for cog_name in SUB_COGS:
        extension_name = f"cogs.impostor.{cog_name}"
        try:
            # Usamos asyncio.gather para cargar en paralelo en el futuro si fuera necesario
            # pero por ahora, una carga secuencial es más fácil de depurar.
            await bot.load_extension(extension_name)
            print(f"  ✅ [Impostor] Sub-cog cargado: {cog_name}")
            loaded_count += 1
        except commands.ExtensionAlreadyLoaded:
            print(f"  ⚠️ [Impostor] Sub-cog ya estaba cargado: {cog_name}")
        except Exception as e:
            print(f"  ❌ [Impostor] Error cargando sub-cog {cog_name}: {e}")
            log.exception(f"Error al cargar {extension_name}", exc_info=e)
            failed_count += 1

    print(f"Carga de 'cogs.impostor' completa.")
    print(f"  -> {loaded_count} sub-cogs cargados exitosamente.")
    if failed_count > 0:
        print(f"  -> {failed_count} sub-cogs fallaron al cargar.")
    print("---------------------------------")


async def teardown(bot: commands.Bot):
    """
    Función teardown llamada por discord.py cuando se descarga la extensión.
    
    Descargará todos los sub-cogs en orden reverso.
    """
    print("---------------------------------")
    print("Descargando paquete: cogs.impostor")
    
    for cog_name in reversed(SUB_COGS):
        extension_name = f"cogs.impostor.{cog_name}"
        try:
            await bot.unload_extension(extension_name)
            print(f"  🗑️ [Impostor] Sub-cog descargado: {cog_name}")
        except Exception as e:
            print(f"  ❌ [Impostor] Error descargando sub-cog {cog_name}: {e}")
    
    print("Descarga de 'cogs.impostor' completa.")
    print("---------------------------------")