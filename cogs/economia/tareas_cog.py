# cogs/economia/tareas_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List, Literal, Optional

from .db_manager import EconomiaDBManagerV2
from .progreso_vistas import (
    build_pages_diaria,
    build_pages_inicial,
    build_pages_semanal,
    flatten_embed_pages,
)
from .reclamar_service import (
    MSG_TIP_INICIACION_AL_RECLAMAR,
    RECLAMO_TIPOS_AYUDA,
    build_inicial_reclaim_hint,
    build_reclaim_status_block,
    reclaim_rewards,
)

class TareasCog(commands.Cog, name="Economia Tareas"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self.log = logging.getLogger(self.__class__.__name__)
        self.task_config = bot.task_config
        super().__init__()

    async def _send_progress_pages(
        self, interaction: discord.Interaction, pages: List[List[discord.Embed]]
    ) -> None:
        flat = flatten_embed_pages(pages)
        for i in range(0, len(flat), 10):
            await interaction.followup.send(embeds=flat[i : i + 10], ephemeral=True)

    @app_commands.command(
        name="aat-progreso-iniciacion",
        description="Progreso Iniciación (initial / onboarding): Discord + perfil.",
    )
    async def progreso_iniciacion(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = self.task_config or {}
        pages = build_pages_inicial(self.db, cfg, interaction.user.id)
        await self._send_progress_pages(interaction, pages)

    @app_commands.command(
        name="aat-progreso-diaria",
        description="Progreso Diario (daily): actividad + oráculo y trampa.",
    )
    async def progreso_diaria(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = self.task_config or {}
        pages = build_pages_diaria(self.db, cfg, interaction.user.id)
        await self._send_progress_pages(interaction, pages)

    @app_commands.command(
        name="aat-progreso-semanal",
        description="Progreso Semanal (weekly): base, especial Impostor (special) y minijuegos.",
    )
    async def progreso_semanal(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = self.task_config or {}
        pages = build_pages_semanal(self.db, cfg, interaction.user.id)
        await self._send_progress_pages(interaction, pages)


    # --- ¡¡¡COMANDO RECLAMAR MEJORADO!!! ---
    @app_commands.command(
        name="aat-reclamar",
        description="Reclama: inicial, diaria, semanal base, especial Impostor, minijuegos. Vacío = todo lo listo.",
    )
    @app_commands.describe(
        tipo="Vacío = todo. O elegí un tipo (mismos nombres que `?reclamar diaria`, `weekly`, `especial`…)."
    )
    async def reclamar(self, interaction: discord.Interaction, tipo: Optional[Literal["inicial", "diaria", "semanal", "semanal_especial", "semanal_minijuegos"]] = None):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        cfg = self.task_config or {}

        ok, mensajes_exito, mensajes_error = reclaim_rewards(self.db, cfg, user_id, tipo)
        snap = build_reclaim_status_block(self.db, cfg, user_id)
        parts: List[str] = []
        if mensajes_exito:
            parts.append("**Reclamado:**\n" + "\n".join(mensajes_exito))
        if mensajes_error:
            parts.append("**Avisos:**\n" + "\n".join(mensajes_error))
        if not ok and not mensajes_error:
            parts.append("_Nada listo en este intento._")
        parts.append("**Tu estado ahora:**\n" + snap)
        parts.append(f"_En prefijo: {RECLAMO_TIPOS_AYUDA}_")
        desc = "\n\n".join(parts)[:4000]
        color = discord.Color.green() if ok else (discord.Color.orange() if mensajes_error else discord.Color.blurple())
        embed = discord.Embed(title="Reclamar", description=desc, color=color)
        prog_ini = self.db.get_progress_inicial(user_id)
        if int(prog_ini.get("completado") or 0) != 1:
            embed.set_footer(text=MSG_TIP_INICIACION_AL_RECLAMAR[:2048])
        await interaction.followup.send(embed=embed, ephemeral=True)
        if not ok and not mensajes_error and tipo is None:
            extra = build_inicial_reclaim_hint(self.db, user_id)
            if extra:
                await interaction.followup.send(
                    extra + "\n\n`/aat-progreso-*` o `?progreso` en el canal del bot.",
                    ephemeral=True,
                )

async def setup(bot):
    await bot.add_cog(TareasCog(bot))