# Embeds compartidos: `?mi`, `?top` / `?tophist`, slash `/aat-mi` y `/aat-top-hist`.
from __future__ import annotations

from typing import Any, Dict, List

import discord
from discord.ext import commands

from .db_manager import EconomiaDBManagerV2
from .toque_labels import toque_emote


async def _display_name(bot: commands.Bot, user_id: int) -> str:
    try:
        u = bot.get_user(user_id) or await bot.fetch_user(user_id)
        return u.display_name
    except discord.NotFound:
        return "Desconocido"


async def _leaderboard_body(bot: commands.Bot, rows: List[Dict[str, Any]], points_key: str) -> str:
    if not rows:
        return "*Nadie todavía.*"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines: List[str] = []
    for i, r in enumerate(rows):
        medal = medals[i] if i < len(medals) else f"**{i + 1}.**"
        name = await _display_name(bot, int(r["user_id"]))
        lines.append(f"{medal} {name} • **{int(r.get(points_key) or 0)}**")
    return "\n".join(lines)


async def render_mi_embed(bot: commands.Bot, db: EconomiaDBManagerV2, user: discord.abc.User) -> discord.Embed:
    uid = user.id
    db.ensure_user_exists(uid)
    eco = db.get_user_economy(uid)
    ra = db.get_user_rank_info(uid, "actual")
    rh = db.get_user_rank_info(uid, "conseguidos")
    copies, kinds = db.inventory_cards_totals(uid)
    tq = toque_emote()
    embed = discord.Embed(
        title=f"{tq} Tu resumen — {user.display_name}",
        color=discord.Color.gold(),
    )
    embed.description = (
        f"**Saldo actual:** `{eco['puntos_actuales']}` {tq} — **#{ra['rank']}** en el servidor "
        f"(`?top` / saldo momentáneo).\n"
        f"**Total ganado (histórico):** `{eco['puntos_conseguidos']}` — **#{rh['rank']}** "
        f"(`?tophist` / todo lo que sumaste aunque lo hayas gastado).\n"
        f"**Total gastado (lifetime):** `{eco['puntos_gastados']}`\n\n"
        f"**Cartas en inventario:** **{copies}** copias · **{kinds}** tipos distintos."
    )
    embed.set_footer(text="Slash: /aat-mi · /aat-top-hist · /aat-ranking-top")
    return embed


async def render_top_embed(
    bot: commands.Bot,
    db: EconomiaDBManagerV2,
    *,
    ranking_type: str,
    points_key: str,
    title: str,
    limit: int = 5,
) -> discord.Embed:
    rows = db.get_top_users(ranking_type, limit=limit)
    body = await _leaderboard_body(bot, rows, points_key)
    return discord.Embed(title=title, description=body, color=discord.Color.gold())
