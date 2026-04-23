# Embeds compartidos: `?mi`, `?top` / `?tophist`, slash `/aat-mi` y `/aat-top-hist`.
from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple

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


async def _leaderboard_body_global(
    bot: commands.Bot, rows: List[Dict[str, Any]], points_key: str, start_rank: int
) -> str:
    """Lista con posición global (1 = mejor). Medallas solo para puestos 1–3 del servidor."""
    if not rows:
        return "*Nadie en esta página.*"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines: List[str] = []
    for i, r in enumerate(rows):
        pos = start_rank + i
        prefix = medals.get(pos, f"`{pos}.`")
        name = await _display_name(bot, int(r["user_id"]))
        lines.append(f"{prefix} {name} • **{int(r.get(points_key) or 0)}**")
    return "\n".join(lines)


def _ranking_meta(ranking_type: str) -> Tuple[str, str]:
    tq = toque_emote()
    if ranking_type == "conseguidos":
        return "puntos_conseguidos", f"{tq} Ranking — histórico ganado (total conseguido)"
    if ranking_type == "gastados":
        return "puntos_gastados", f"{tq} Ranking — total gastado (lifetime)"
    return "puntos_actuales", f"{tq} Ranking — saldo actual (Toque points)"


RankingHubMode = Literal["actual", "conseguidos", "gastados"]


async def render_ranking_hub_embed(
    bot: commands.Bot,
    db: EconomiaDBManagerV2,
    ranking_type: RankingHubMode,
    offset: int,
    page_size: int,
    viewer: discord.abc.User,
) -> discord.Embed:
    points_key, title = _ranking_meta(ranking_type)
    total = db.count_ranked_users(ranking_type)
    off = max(0, offset)
    if total == 0:
        body = "*Todavía nadie figura en esta tabla (todos en 0).*"
        rows = []
    else:
        rows = db.get_top_users(ranking_type, limit=page_size, offset=off)
        start_rank = off + 1
        body = await _leaderboard_body_global(bot, rows, points_key, start_rank)
    info = db.get_user_rank_info(viewer.id, ranking_type)
    val = int(info["value"] or 0)
    rk = int(info["rank"] or 0)
    wp = int(info["with_positive"] or 0)
    if wp <= 0:
        you_line = f"**Tu fila:** sin puntaje en esta tabla (`0`)."
    else:
        you_line = f"**Tu posición:** **#{rk}** de **{wp}** con puntaje > 0 · valor: **{val}**"

    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    cur_page = (off // page_size) + 1 if total else 1
    if total and rows:
        start_rank = off + 1
        span = f"**Página {cur_page}/{pages}** · puestos **{start_rank}**–**{off + len(rows)}**"
    else:
        span = f"**Página {cur_page}/{pages}**"

    embed = discord.Embed(title=title, description=f"{you_line}\n{span}\n\n{body}", color=discord.Color.gold())
    embed.set_footer(
        text="◀ ▶ paginar · menú: tipo de ranking · botones: tu resumen, trivia, top anime · ?top = top 5 rápido"
    )
    return embed


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
        f"(`?top` rápido · `?ranking` paginado).\n"
        f"**Total ganado (histórico):** `{eco['puntos_conseguidos']}` — **#{rh['rank']}** "
        f"(`?tophist` / todo lo que sumaste aunque lo hayas gastado).\n"
        f"**Total gastado (lifetime):** `{eco['puntos_gastados']}`\n\n"
        f"**Cartas en inventario:** **{copies}** copias · **{kinds}** tipos distintos."
    )
    embed.set_footer(text="`?ranking` tablas paginadas · Slash: /aat-mi · /aat-top-hist · /aat-ranking-top")
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
