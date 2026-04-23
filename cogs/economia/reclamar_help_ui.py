# Vista paginada `?reclamar` + botones Ver progreso / Reclamar todo.
from __future__ import annotations

from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands

from cogs.economia.guia_contenido import GuiaEmbedsPaginator
from cogs.economia.progreso_vistas import (
    build_pages_diaria,
    build_pages_inicial,
    build_pages_semanal,
    flatten_embed_pages,
)
from cogs.economia.reclamar_service import (
    MSG_TIP_INICIACION_AL_RECLAMAR,
    build_reclaim_status_block,
    reclaim_rewards,
)


def build_reclaim_result_embed(
    db: Any,
    task_config: Dict[str, Any],
    user_id: int,
    ok_msgs: List[str],
    err_msgs: List[str],
) -> discord.Embed:
    snap = build_reclaim_status_block(db, task_config, user_id)
    parts: List[str] = []
    if ok_msgs:
        parts.append("**Reclamado:**\n" + "\n".join(ok_msgs))
    if err_msgs:
        parts.append("**Avisos:**\n" + "\n".join(err_msgs))
    if not ok_msgs and not err_msgs:
        parts.append("_No se cobró nada en este paso (nada listo o ya reclamado)._")
    parts.append("**Tu estado ahora:**\n" + snap)
    desc = "\n\n".join(parts)[:4000]
    color = discord.Color.green() if ok_msgs else (discord.Color.orange() if err_msgs else discord.Color.light_grey())
    emb = discord.Embed(title="Reclamar", description=desc, color=color)
    prog_ini = db.get_progress_inicial(user_id)
    if int(prog_ini.get("completado") or 0) != 1:
        emb.set_footer(text=MSG_TIP_INICIACION_AL_RECLAMAR[:2048])
    return emb


class _VerProgresoBtn(discord.ui.Button):
    def __init__(self, *, label: str, kind: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=1)
        self.kind = kind

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, ReclamarHelpView):
            return
        await view._send_ver(interaction, self.kind)


class _ReclamarTodoBtn(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Reclamar todo lo listo", style=discord.ButtonStyle.success, row=2, emoji="🎁")

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, ReclamarHelpView):
            return
        await view._send_reclamar_todo(interaction)


class ReclamarHelpView(GuiaEmbedsPaginator):
    """Guía `?reclamar` paginada + accesos rápidos a progreso + reclamar todo."""

    def __init__(self, bot: commands.Bot, author_id: int, pages: List[List[discord.Embed]], *, label: str):
        super().__init__(author_id, pages, label=label)
        self.bot = bot
        self.add_item(_VerProgresoBtn(label="Ver inicial", kind="inicial"))
        self.add_item(_VerProgresoBtn(label="Ver diario", kind="diaria"))
        self.add_item(_VerProgresoBtn(label="Ver semanal", kind="semanal"))
        self.add_item(_VerProgresoBtn(label="Ver especial", kind="especial"))
        self.add_item(_ReclamarTodoBtn())

    def header(self) -> Optional[str]:
        base = super().header()
        tip = "Abajo: **Ver …** (mensaje nuevo) · **Reclamar todo**"
        if base:
            return f"{base}\n{tip}"
        return f"{self.label}\n{tip}"

    async def _send_ver(self, interaction: discord.Interaction, kind: str) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Solo quien abrió esta guía puede usar los botones. Ejecutá `?reclamar` vos.",
                ephemeral=True,
            )
            return
        db = self.bot.economia_db
        tc = getattr(self.bot, "task_config", None) or {}
        uid = interaction.user.id
        if kind == "inicial":
            parts = build_pages_inicial(db, tc, uid)
            title = "**Progreso — Iniciación**"
        elif kind == "diaria":
            parts = build_pages_diaria(db, tc, uid)
            title = "**Progreso — Diario** (*daily*)"
        elif kind == "semanal":
            parts = build_pages_semanal(db, tc, uid)
            title = "**Progreso — Semanal** (*weekly*: base + especial + minijuegos)"
        else:
            full = build_pages_semanal(db, tc, uid)
            parts = [full[2]] if len(full) >= 3 else full[-1:]
            title = "**Progreso — Especial Impostor** (*weekly special*)"
        flat = flatten_embed_pages(parts)[:10]
        if not flat:
            await interaction.response.send_message(
                f"{title}\n_No hay embeds para mostrar._",
                ephemeral=False,
            )
            return
        await interaction.response.send_message(content=title, embeds=flat, ephemeral=False)

    async def _send_reclamar_todo(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Solo quien abrió esta guía puede reclamar desde acá.",
                ephemeral=True,
            )
            return
        db = self.bot.economia_db
        tc = getattr(self.bot, "task_config", None) or {}
        uid = interaction.user.id
        ok, ok_msgs, err_msgs = reclaim_rewards(db, tc, uid, None)
        emb = build_reclaim_result_embed(db, tc, uid, ok_msgs, err_msgs)
        await interaction.response.send_message(embed=emb, ephemeral=False)
