# Vista de paginación de progreso (`?inicial` / `?diaria` / …) con botones Reclamar.
from __future__ import annotations

from typing import List, Literal, Optional

import discord
from discord.ext import commands

from cogs.economia.guia_contenido import GuiaEmbedsPaginator
from cogs.economia.progreso_vistas import (
    build_pages_diaria,
    build_pages_inicial,
    build_pages_semanal,
    build_progreso_resumen_pages,
)
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
    """Igual que la guía (◀ Atrás / ▶ Siguiente) + botones para reclamar según el comando."""

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
        self.reclaim_layout: _Layout = layout
        if layout == "inicial":
            self.add_item(_ReclaimBtn(label="Ini 1 · Discord", tipo="inicial_comunidad", row=0))
            self.add_item(_ReclaimBtn(label="Ini 2 · Perfil min.", tipo="inicial_perfil_min", row=0))
            self.add_item(_ReclaimBtn(label="Ini 3 · Perfil top", tipo="inicial_perfil_max", row=0))
            self.add_item(_ReclaimBtn(label="Todo iniciación", tipo="inicial", row=1))
        elif layout == "diaria":
            self.add_item(_ReclaimBtn(label="Diaria 1 · Actividad", tipo="diaria_actividad", row=0))
            self.add_item(_ReclaimBtn(label="Diaria 2 · Trampa", tipo="diaria_trampa", row=0))
            self.add_item(_ReclaimBtn(label="Diaria 3 · Rolls", tipo="diaria_rolls", row=0))
            self.add_item(_ReclaimBtn(label="Diaria 4 · PPT", tipo="diaria_rps", row=1))
            self.add_item(_ReclaimBtn(label="Diaria 5 · Ahorcado", tipo="diaria_ahorcado", row=1))
            self.add_item(_ReclaimBtn(label="Todo el diario", tipo="diaria", row=2))
        elif layout == "semanal":
            self.add_item(_ReclaimBtn(label="Semanal base", tipo="semanal", row=0))
            self.add_item(_ReclaimBtn(label="Especial", tipo="semanal_especial", row=0))
            self.add_item(_ReclaimBtn(label="Minijuegos", tipo="semanal_minijuegos", row=0))
            self.add_item(_ReclaimBtn(label="Todo semanal", tipo="semanal_all", row=1))
        elif layout == "progreso":
            self.add_item(_ReclaimBtn(label="Reclamar todo lo listo", tipo=None))

    def header(self) -> Optional[str]:
        base = super().header()
        if self.reclaim_layout == "progreso":
            tip = "Tras cobrar, el mensaje se **actualiza**. · Leyenda / tips: **`?progresoayuda`**"
        else:
            tip = (
                "Tras cobrar, este mensaje se **actualiza**. · `diaria 1–5` · `semanal 1–4` "
                "(**4** = todas las semanales listas) · ver también `?reclamar`."
            )
        if base:
            return f"{base} — {tip}"
        return f"{self.label} — {tip}"

    def _rebuild_pages(self, user_id: int) -> List[List[discord.Embed]]:
        db = self.bot.economia_db
        tc = getattr(self.bot, "task_config", None) or {}
        lay = self.reclaim_layout
        if lay == "inicial":
            return build_pages_inicial(db, tc, user_id)
        if lay == "diaria":
            return build_pages_diaria(db, tc, user_id)
        if lay == "semanal":
            return build_pages_semanal(db, tc, user_id)
        pages: List[List[discord.Embed]] = []
        pages.extend(build_progreso_resumen_pages(db, tc, user_id))
        pages.extend(build_pages_inicial(db, tc, user_id))
        pages.extend(build_pages_diaria(db, tc, user_id))
        pages.extend(build_pages_semanal(db, tc, user_id))
        return pages

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
        await interaction.response.defer(ephemeral=False)
        _ok, ok_msgs, err_msgs = reclaim_rewards(db, tc, interaction.user.id, tipo)  # type: ignore[arg-type]
        emb = build_reclaim_result_embed(db, tc, interaction.user.id, ok_msgs, err_msgs)
        self.pages = self._rebuild_pages(interaction.user.id)
        if self.pages:
            self.idx = min(self.idx, len(self.pages) - 1)
        else:
            self.idx = 0
        self._sync_buttons()
        try:
            await interaction.edit_original_response(
                content=self.header(),
                embeds=self.pages[self.idx] if self.pages else [],
                view=self,
            )
        except discord.HTTPException:
            pass
        await interaction.followup.send(embed=emb, ephemeral=False)
