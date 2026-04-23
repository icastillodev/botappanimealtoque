# Vista de paginación de progreso (`?inicial` / `?diaria` / …) con botones Reclamar.
from __future__ import annotations

from typing import List, Literal, Optional

import discord
from discord.ext import commands

from cogs.economia.guia_contenido import GuiaEmbedsPaginator
from cogs.economia.reclamar_help_ui import build_reclaim_result_embed
from cogs.economia.reclamar_service import (
    RECLAMO_TIPOS_AYUDA,
    is_reclamar_all_keyword,
    map_reclamo_token_to_tipo,
    reclaim_rewards,
)

_Layout = Literal["inicial", "diaria", "semanal", "progreso"]


class _ReclaimBtn(discord.ui.Button):
    def __init__(self, *, label: str, tipo: Optional[str], row: int = 1):
        super().__init__(label=label, style=discord.ButtonStyle.success, row=row)
        self.tipo_arg = tipo  # None = reclamar todo lo listo

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, ProgressEmbedsWithReclaimView):
            await view.run_reclaim(interaction, self.tipo_arg)


class ProgressEmbedsWithReclaimView(GuiaEmbedsPaginator):
    """Igual que la guía (Anterior/Siguiente) + botones para reclamar según el comando."""

    def __init__(
        self,
        bot: commands.Bot,
        author_id: int,
        pages: List[List[discord.Embed]],
        *,
        label: str,
        layout: _Layout,
    ):
        super().__init__(author_id, pages, label=label)
        self.bot = bot
        if layout == "inicial":
            self.add_item(_ReclaimBtn(label="Reclamar iniciación", tipo="inicial"))
        elif layout == "diaria":
            self.add_item(_ReclaimBtn(label="Reclamar diario", tipo="diaria"))
        elif layout == "semanal":
            self.add_item(_ReclaimBtn(label="Reclamar base", tipo="semanal", row=1))
            self.add_item(_ReclaimBtn(label="Reclamar especial", tipo="semanal_especial", row=1))
            self.add_item(_ReclaimBtn(label="Reclamar minijuegos", tipo="semanal_minijuegos", row=1))
        elif layout == "progreso":
            self.add_item(_ReclaimBtn(label="Reclamar todo lo listo", tipo=None))

    def header(self) -> Optional[str]:
        base = super().header()
        tip = "También: `?reclamar` · `?reclamar diaria` · `?reclamar weekly`…"
        if base:
            return f"{base} — {tip}"
        return f"{self.label} — {tip}"

    async def run_reclaim(self, interaction: discord.Interaction, tipo_token: Optional[str]) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Solo quien abrió el progreso puede usar estos botones.",
                ephemeral=True,
            )
            return
        db = self.bot.economia_db
        tc = getattr(self.bot, "task_config", None) or {}
        tipo: Optional[str] = None
        if tipo_token:
            if is_reclamar_all_keyword(tipo_token):
                tipo = None
            else:
                m = map_reclamo_token_to_tipo(tipo_token)
                if m is None:
                    await interaction.response.send_message(
                        f"No reconozco `{tipo_token}`. {RECLAMO_TIPOS_AYUDA}",
                        ephemeral=True,
                    )
                    return
                tipo = m
        _ok, ok_msgs, err_msgs = reclaim_rewards(db, tc, interaction.user.id, tipo)  # type: ignore[arg-type]
        emb = build_reclaim_result_embed(db, tc, interaction.user.id, ok_msgs, err_msgs)
        await interaction.response.send_message(embed=emb, ephemeral=False)
