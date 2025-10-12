# bot.py
import os
import unicodedata
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# Carga de variables .env
# =========================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # opcional: sincroniza slash (aunque no tengamos comandos)

# IDs específicos para tu flujo
CHANNEL_ID_PRESENTACION = int(os.getenv("TRIGGER_CHANNEL_ID_PRESENTACION", "0"))  # 🪪・presentacion
ROLE_ID_CHUNIN = int(os.getenv("TARGET_ROLE_ID_CHUNIN", "0"))                     # 🥷 Chūnin

# Emoji personalizado :tojitook: (usa UNO de los dos métodos)
EMOJI_ID_TOJITOOK = int(os.getenv("TOJITOOK_EMOJI_ID", "0"))       # recomendado (ID del emoji)
EMOJI_NAME_TOJITOOK = os.getenv("TOJITOOK_EMOJI_NAME", "tojitook") # alternativo por nombre

if not TOKEN:
    raise SystemExit("Falta DISCORD_TOKEN en .env")

# =========================
# Intents y Bot
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True  # leer texto ("caca" y validar formato)
intents.members = True          # necesario para add_roles

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# Utilidades
# =========================
def _normalize(txt: str) -> str:
    """Minusculas + sin tildes/acentos."""
    nfkd = unicodedata.normalize("NFKD", txt).encode("ASCII", "ignore").decode("ASCII")
    return nfkd.lower()

def cumple_formato(contenido: str) -> bool:
    """
    Debe CONTENER estas 4 palabras (como substring):
    list, personaje, top, categoria
    (insensible a mayúsculas y acentos).
    """
    t = _normalize(contenido)  # ya deja en minúsculas y sin tildes
    claves = ["list", "personaje", "top", "categoria"]
    return all(k in t for k in claves)

async def reaccionar_tojitook(msg: discord.Message):
    """Reacciona con 🔥 y con :tojitook: si existe/tenés permiso."""
    # 🔥
    try:
        await msg.add_reaction("🔥")
    except Exception:
        pass

    # :tojitook:
    emoji_obj = None
    if EMOJI_ID_TOJITOOK:
        emoji_obj = bot.get_emoji(EMOJI_ID_TOJITOOK)
    if not emoji_obj and msg.guild:
        emoji_obj = discord.utils.find(
            lambda e: e.name.lower() == EMOJI_NAME_TOJITOOK.lower(), msg.guild.emojis
        )
    if emoji_obj:
        try:
            await msg.add_reaction(emoji_obj)
        except Exception:
            pass

FORMATO_TXT = (
    "Formato presentación al toque (copiá/pegá y completá):\n\n"
    "🧾 **AnimeList:** (tu perfil o lista, o nada si no tenés)\n\n"
    "⚔️ **Personaje que pelearías espalda con espalda:** (ej: Itachi, Zoro, Goku, Gojo...)\n\n"
    "🥇 **Top 3 animes:**\n"
    "1.\n2.\n3.\n\n"
    "🌀 **Categoría anime que más te gusta:** (isekai, shonen, seinen, romance, slice of life, etc.)\n\n"
    "Recordá incluir las palabras **animelist**, **personaje**, **top** y **categoria**."
)

# =========================
# Eventos
# =========================
@bot.event
async def on_ready():
    print(f"Conectado como {bot.user} (ID {bot.user.id})")
    try:
        if GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=int(GUILD_ID)))
            print(f"Slash commands sincronizados en guild {GUILD_ID}")
        else:
            await bot.tree.sync()  # global (aunque no tengamos slash commands, no hace daño)
            print("Slash commands globales sincronizados")
    except Exception as e:
        print("Error al sincronizar comandos:", e)

@bot.event
async def on_message(message: discord.Message):
    # Ignorar DMs y bots
    if message.author.bot or message.guild is None:
        return

    # 0) Respuesta divertida: "caca" -> "loco"
    if "caca" in message.content.lower():
        await message.channel.send("loco")

    # 1) Validación de presentaciones SOLO en el canal configurado
    if CHANNEL_ID_PRESENTACION and message.channel.id == CHANNEL_ID_PRESENTACION:
        if not cumple_formato(message.content):
            # a) BORRAR PRIMERO el mensaje del usuario
            user_msg_deleted = False
            try:
                await message.delete()
                user_msg_deleted = True
            except discord.Forbidden:
                user_msg_deleted = False
            except discord.HTTPException:
                user_msg_deleted = False

            # b) Aviso temporal en el canal (se elimina solo)
            warn = None
            try:
                aviso_txt = (
                    f"{message.author.mention} tu presentación no cumple el formato. "
                    "Te mandé un DM con el modelo."
                )
                if not user_msg_deleted:
                    aviso_txt += " *(No pude borrar tu mensaje; verificá que el bot tenga **Manage Messages** en este canal).*"
                warn = await message.channel.send(aviso_txt)
            except Exception:
                pass

            # c) DM con el formato correcto
            try:
                dm = await message.author.create_dm()
                await dm.send(
                    "👋 Tu presentación no fue aceptada porque no sigue el formato.\n"
                    "Usá este modelo y volvé a enviarla en el canal de presentaciones:\n\n"
                    + FORMATO_TXT
                )
            except Exception:
                # DMs cerrados
                pass

            # d) Borrar el aviso después de unos segundos
            if warn:
                try:
                    await asyncio.sleep(6)
                    await warn.delete()
                except Exception:
                    pass

            # No seguir procesando este mensaje
            await bot.process_commands(message)
            return

        # Si el formato es correcto:
        await reaccionar_tojitook(message)

        # Asignar rol Chūnin (si no lo tiene)
        role = message.guild.get_role(ROLE_ID_CHUNIN) if ROLE_ID_CHUNIN else None
        if role and role not in message.author.roles:
            me = message.guild.get_member(bot.user.id)
            if me and role >= me.top_role:
                try:
                    await message.channel.send(
                        "No puedo asignar **Chūnin** por jerarquía. Subí el rol del bot por encima de ese rol."
                    )
                except Exception:
                    pass
            else:
                try:
                    await message.author.add_roles(role, reason="Presentación válida")
                except discord.Forbidden:
                    try:
                        await message.channel.send("Me falta **Manage Roles** o jerarquía correcta para asignar **Chūnin**.")
                    except Exception:
                        pass
                except Exception as e:
                    print("Error asignando rol Chūnin:", e)

    # Dejar que funcionen los comandos con prefijo/slash si en el futuro agregás
    await bot.process_commands(message)

# =========================
# Ejecución
# =========================
if TOKEN.count(".") != 2:
    print("⚠️ DISCORD_TOKEN no parece un token de bot (debería tener 3 partes con puntos).")

bot.run(TOKEN)
