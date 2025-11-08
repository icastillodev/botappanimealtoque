# cogs/economia/__init__.py
import asyncio
from discord.ext import commands
import logging

# --- ¡¡¡ESTA ES LA LISTA FINAL DE TODOS TUS COGS DE ECONOMÍA!!! ---
SUB_COGS = [
    "listeners_cog",
    "tareas_cog",
    "admin_cog",
    "cartas_cog",
    "tienda_cog",
    "ranking_cog",
    "ayuda_cog",
]

log = logging.getLogger(__name__)

async def setup(bot: commands.Bot):
    print("---------------------------------")
    print("Cargando paquete: cogs.economia")
    
    if not bot.task_config or not bot.shop_config:
        log.critical("¡ERROR FATAL! Faltan task_config o shop_config en el bot. El paquete 'cogs.economia' no se cargará.")
        return

    loaded_count = 0
    failed_count = 0

    for cog_name in SUB_COGS:
        extension_name = f"cogs.economia.{cog_name}"
        try:
            await bot.load_extension(extension_name)
            print(f"  ✅ [Economia] Sub-cog cargado: {cog_name}")
            loaded_count += 1
        except commands.ExtensionAlreadyLoaded:
            print(f"  ⚠️ [Economia] Sub-cog ya estaba cargado: {cog_name}")
        except Exception as e:
            print(f"  ❌ [Economia] Error cargando sub-cog {cog_name}: {e}")
            log.exception(f"Error al cargar {extension_name}", exc_info=e)
            failed_count += 1

    print(f"Carga de 'cogs.economia' completa.")
    print(f"  -> {loaded_count} sub-cogs cargados exitosamente.")
    if failed_count > 0:
        print(f"  -> {failed_count} sub-cogs fallaron al cargar.")
    print("---------------------------------")


async def teardown(bot: commands.Bot):
    print("---------------------------------")
    print("Descargando paquete: cogs.economia")
    
    for cog_name in reversed(SUB_COGS):
        extension_name = f"cogs.economia.{cog_name}"
        try:
            await bot.unload_extension(extension_name)
            print(f"  🗑️ [Economia] Sub-cog descargado: {cog_name}")
        except Exception as e:
            print(f"  ❌ [Economia] Error descargando sub-cog {cog_name}: {e}")
    
    print("Descarga de 'cogs.economia' completa.")
    print("---------------------------------")