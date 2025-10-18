# cogs/impostor/logger.py
import os
from typing import List, Optional
import discord

LOG_CH_IDS: List[int] = []
raw = os.getenv("IMPOSTOR_STAFF_LOG_CHANNEL_ID", "").strip()
if raw:
    for piece in raw.split(","):
        piece = piece.strip()
        if piece.isdigit():
            LOG_CH_IDS.append(int(piece))

async def log_staff(guild: discord.Guild, *, title: str, desc: str):
    """Manda un embed de log a los canales configurados (si hay)."""
    if not LOG_CH_IDS:
        return
    emb = discord.Embed(title=f"[IMPOSTOR] {title}", description=desc, color=discord.Color.blurple())
    for ch_id in LOG_CH_IDS:
        ch = guild.get_channel(ch_id)
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(embed=emb)
            except Exception:
                pass
