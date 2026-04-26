# cogs/channel_enforcer.py
import os
import unicodedata
from typing import FrozenSet, Optional

import discord
from discord.ext import commands


def _env_truthy(key: str) -> bool:
    return os.getenv(key, "").strip().lower() in ("1", "true", "yes", "on")


def _normalize_token_fragment(s: str) -> str:
    """Minúsculas + sin acentos (misma idea que el primer token del mensaje)."""
    nk = unicodedata.normalize("NFKD", (s or "").strip())
    ascii_fold = "".join(ch for ch in nk if not unicodedata.combining(ch))
    return ascii_fold.lower()


def _normalized_message_content(message: discord.Message) -> str:
    """
    Algunos teclados mandan '？' (U+FF1F) en vez de '?'.
    Normalizamos solo el primer carácter para que el prefijo siga funcionando.
    """
    raw = (message.content or "").strip()
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff").strip()
    if raw.startswith("？"):
        return "?" + raw[1:]
    return raw


def _prefix_first_token(content: str) -> str:
    """Primer token tras '?' (sin acentos, minúsculas). Ej.: guía → guia."""
    raw = (content or "").strip()
    if not raw.startswith("?") or len(raw) <= 1:
        return ""
    rest = raw[1:].strip()
    if not rest:
        return ""
    first = rest.split()[0]
    return _normalize_token_fragment(first)


def _allowed_prefix_tokens(bot: commands.Bot) -> FrozenSet[str]:
    """
    Todos los nombres y aliases de comandos de prefijo registrados en el bot.
    Así no dependemos de una lista manual que se queda vieja al agregar comandos.
    """
    names: set[str] = set()
    for cmd in bot.walk_commands():
        # Solo comandos “reales” de ext (ignoramos el árbol híbrido de app_commands).
        if not isinstance(cmd, commands.Command):
            continue
        names.add(_normalize_token_fragment(cmd.name))
        for a in cmd.aliases:
            names.add(_normalize_token_fragment(a))
    return frozenset(names)


class ChannelEnforcerCog(commands.Cog, name="Limpieza de Chat"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._allowed_tokens_cache: Optional[FrozenSet[str]] = None
        try:
            self.general_id = int(os.getenv("GENERAL_CHANNEL_ID"))
            self.bot_channel_id = int(os.getenv("BOT_CHANNEL_ID"))
        except (TypeError, ValueError):
            print("❌ Error: Faltan GENERAL_CHANNEL_ID o BOT_CHANNEL_ID en el .env")
            self.general_id = 0
            self.bot_channel_id = 0

    def _tokens_for_bot(self) -> FrozenSet[str]:
        if self._allowed_tokens_cache is None:
            self._allowed_tokens_cache = _allowed_prefix_tokens(self.bot)
        return self._allowed_tokens_cache

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if _env_truthy("DISABLE_CHANNEL_PREFIX_ENFORCER"):
            return
        if self.general_id == 0 or self.bot_channel_id == 0:
            return

        if message.channel.id != self.general_id:
            return

        text = _normalized_message_content(message)
        if not (text.startswith("?") and len(text) > 1 and not text.startswith("? ")):
            return

        first = _prefix_first_token(text)
        if not first:
            return

        if first in self._tokens_for_bot():
            return

        try:
            await message.delete()
        except discord.Forbidden:
            return

        embed = discord.Embed(
            description=(
                f"🚫 **{message.author.mention}, en este canal ese `?comando` no está registrado** "
                f"(o tiene un typo). Probá **`?comandos`** o usá el canal del bot: <#{self.bot_channel_id}>.\n"
                f"_Tip: en algunos teclados el `?` sale como carácter ancho `？` — también lo aceptamos._"
            ),
            color=discord.Color.red(),
        )
        try:
            await message.channel.send(embed=embed, delete_after=8)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelEnforcerCog(bot))
