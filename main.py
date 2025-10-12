import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise SystemExit("Falta DISCORD_TOKEN en .env")

# Intents
intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Carga de extensiones (cogs) — cada una una sola vez
INITIAL_EXTENSIONS = [
    "cogs.presentaciones",
    "cogs.economy",
    "cogs.invites", 
]

@bot.event
async def on_ready():
    print(f"Conectado como {bot.user} (ID {bot.user.id})")

async def load_extensions():
    for ext in INITIAL_EXTENSIONS:
        if ext in bot.extensions:  # evita carga doble
            print(f"⚠️ Ya estaba cargado: {ext}")
            continue
        try:
            await bot.load_extension(ext)
            print(f"✅ Cargado: {ext}")
        except Exception as e:
            print(f"❌ Error cargando {ext}: {e}")

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
