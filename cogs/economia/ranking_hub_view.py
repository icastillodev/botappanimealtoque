# Vista interactiva: `?ranking` — tablas de economía paginadas + accesos a otros tops.
from __future__ import annotations

from typing import TYPE_CHECKING, List

import discord
from discord.ext import commands

from .anime_top_cog import _embed_top_for
from .mi_resumen import RankingHubMode, render_mi_embed, render_ranking_hub_embed

if TYPE_CHECKING:
    from .db_manager import EconomiaDBManagerV2


def _trivia_top_embed(bot: commands.Bot, db: EconomiaDBManagerV2, guild: discord.Guild, limit: int = 10) -> discord.Embed:
    rows = db.trivia_stats_top(limit)
    if not rows:
        return discord.Embed(
            title="🏆 Top trivia anime",
            description="Todavía no hay victorias (hay que ser el **primero** en acertar cuando sale la pregunta).",
            color=discord.Color.orange(),
        )
    lines: List[str] = []
    for i, (uid, w) in enumerate(rows, start=1):
        m = guild.get_member(uid)
        name = m.display_name if m else f"ID {uid}"
        suf = "victoria" if w == 1 else "victorias"
        lines.append(f"`{i}.` **{discord.utils.escape_markdown(name)}** — {w} {suf}")
    emb = discord.Embed(
        title="🏆 Top trivia anime (primer acierto por ronda)",
        description="\n".join(lines),
        color=discord.Color.orange(),
    )
    emb.set_footer(text="Solo cuenta ser el primero en acertar a tiempo · `?triviami`")
    return emb


class _RankingModeButton(discord.ui.Button):
    def __init__(self, hub: "RankingHubView", mode: RankingHubMode, label: str):
        self.hub = hub
        self.mode = mode
        super().__init__(label=label, row=0, style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.hub.owner_id:
            await interaction.response.send_message("Este panel es de otra persona.", ephemeral=True)
            return
        self.hub.mode = self.mode
        self.hub.offset = 0
        self.hub._restyle_mode_buttons()
        self.hub._sync_nav()
        emb = await render_ranking_hub_embed(
            self.hub.bot, self.hub.db, self.hub.mode, self.hub.offset, self.hub.page_size, interaction.user
        )
        await interaction.response.edit_message(embed=emb, view=self.hub)


class _NavButton(discord.ui.Button):
    def __init__(self, hub: "RankingHubView", *, delta: int, label: str):
        self.hub = hub
        self.delta = delta
        super().__init__(label=label, row=1, style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.hub.owner_id:
            await interaction.response.send_message("Este panel es de otra persona.", ephemeral=True)
            return
        self.hub.offset = max(0, self.hub.offset + self.delta * self.hub.page_size)
        total = self.hub.db.count_ranked_users(self.hub.mode)
        max_off = max(0, ((total - 1) // self.hub.page_size) * self.hub.page_size) if total else 0
        self.hub.offset = min(self.hub.offset, max_off)
        self.hub._sync_nav()
        emb = await render_ranking_hub_embed(
            self.hub.bot, self.hub.db, self.hub.mode, self.hub.offset, self.hub.page_size, interaction.user
        )
        await interaction.response.edit_message(embed=emb, view=self.hub)


class RankingHubView(discord.ui.View):
    def __init__(self, bot: commands.Bot, db: EconomiaDBManagerV2, owner_id: int, *, page_size: int = 10):
        super().__init__(timeout=300.0)
        self.bot = bot
        self.db = db
        self.owner_id = owner_id
        self.page_size = page_size
        self.mode: RankingHubMode = "actual"
        self.offset = 0
        self._mode_btns = {
            "actual": _RankingModeButton(self, "actual", "Saldo actual"),
            "conseguidos": _RankingModeButton(self, "conseguidos", "Histórico ganado"),
            "gastados": _RankingModeButton(self, "gastados", "Total gastado"),
        }
        for b in self._mode_btns.values():
            self.add_item(b)
        self._prev = _NavButton(self, delta=-1, label="◀️ Anterior")
        self._next = _NavButton(self, delta=1, label="Siguiente ▶️")
        self.add_item(self._prev)
        self.add_item(self._next)
        self.add_item(_HubExtraButton(self, "mi", "Mi resumen", row=2))
        self.add_item(_HubExtraButton(self, "trivia_top", "Top trivia", row=2))
        self.add_item(_HubExtraButton(self, "trivia_me", "Mi trivia", row=2))
        self.add_item(_HubExtraButton(self, "anime_top", "Mi anime top", row=3))
        self._restyle_mode_buttons()
        self._sync_nav()

    def _restyle_mode_buttons(self) -> None:
        for m, b in self._mode_btns.items():
            b.style = discord.ButtonStyle.primary if m == self.mode else discord.ButtonStyle.secondary

    def _sync_nav(self) -> None:
        total = self.db.count_ranked_users(self.mode)
        max_off = max(0, ((total - 1) // self.page_size) * self.page_size) if total else 0
        self._prev.disabled = self.offset <= 0 or total == 0
        self._next.disabled = self.offset >= max_off or total == 0

    async def on_timeout(self) -> None:
        for c in self.children:
            c.disabled = True  # type: ignore[union-attr]


class _HubExtraButton(discord.ui.Button):
    def __init__(self, hub: RankingHubView, kind: str, label: str, *, row: int):
        self.hub = hub
        self.kind = kind
        super().__init__(label=label, row=row, style=discord.ButtonStyle.success if kind == "mi" else discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.hub.owner_id:
            await interaction.response.send_message("Este panel es de otra persona.", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("Solo en servidor.", ephemeral=True)
            return

        if self.kind == "mi":
            self.hub.db.ensure_user_exists(interaction.user.id)
            emb = await render_mi_embed(self.hub.bot, self.hub.db, interaction.user)
            await interaction.response.send_message(embed=emb, ephemeral=True)
            return

        if self.kind == "trivia_top":
            emb = _trivia_top_embed(self.hub.bot, self.hub.db, interaction.guild, 10)
            await interaction.response.send_message(embed=emb, ephemeral=True)
            return

        if self.kind == "trivia_me":
            rank, wins = self.hub.db.trivia_stats_rank_user(interaction.user.id)
            if wins <= 0:
                await interaction.response.send_message(
                    "No tenés victorias en trivia todavía: cuando el bot publique la pregunta en **#general**, "
                    "tenés que ser **el primero** en acertar con `?respuestapregunta` dentro del tiempo límite.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"🎯 Tenés **{wins}** victorias en trivia anime → puesto **#{rank}** en el servidor.",
                    ephemeral=True,
                )
            return

        if self.kind == "anime_top":
            rows = self.hub.db.anime_top_list(interaction.user.id)
            emb = _embed_top_for(self.hub.bot, interaction.user, rows, viewer_is_target=True)
            await interaction.response.send_message(embed=emb, ephemeral=True)
            return

        await interaction.response.send_message("Acción no disponible.", ephemeral=True)
