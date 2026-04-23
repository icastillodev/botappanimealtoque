# cogs/economia/tareas_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import time
import logging
import datetime
from typing import Literal, Optional

from .db_manager import EconomiaDBManagerV2
from .toque_labels import fmt_toque_sentence
from .reclamar_service import (
    INICIAL_HATED_MIN,
    INICIAL_TOP_MIN,
    INICIAL_WISHLIST_MIN,
    MSG_TIP_INICIACION_AL_RECLAMAR,
    PERFIL_HATED_CAP,
    PERFIL_TOP_CAP,
    PERFIL_WISHLIST_CAP,
    build_inicial_reclaim_hint,
    reclaim_rewards,
)

class TareasCog(commands.Cog, name="Economia Tareas"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self.log = logging.getLogger(self.__class__.__name__)
        self.task_config = bot.task_config
        super().__init__()
        
    def _check_task(self, progress_value: int, required_value: int = 1) -> str:
        return "✅" if progress_value >= required_value else "❌"

    @app_commands.command(name="aat-progreso-iniciacion", description="Muestra tu progreso en las tareas de Iniciación.")
    async def progreso_iniciacion(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        prog_ini = self.db.get_progress_inicial(user_id)
        if prog_ini['completado'] == 1:
            embed = discord.Embed(title="Progreso: Tareas de Iniciación", description="✅ ¡Ya has completado todas las tareas de iniciación!", color=discord.Color.green())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        wl = int(self.db.wishlist_total_filled(user_id))
        top10 = int(self.db.anime_top_count_filled(user_id, INICIAL_TOP_MIN))
        hat = int(self.db.hated_total_filled(user_id))
        top_cap = int(self.db.anime_top_count_filled(user_id, PERFIL_TOP_CAP))
        wl_show = min(wl, PERFIL_WISHLIST_CAP)
        hat_show = min(hat, PERFIL_HATED_CAP)
        pie = (
            f"**Recompensa (una vez):** {fmt_toque_sentence(int(self.task_config['rewards']['inicial']))} + 3 blisters — "
            "completá **Discord + perfil mínimo** y `/aat-reclamar` → `inicial`.\n"
            "**¿Discord ya lo hiciste antes?** `/aat-verificar-antiguas`."
        )
        e_disc = discord.Embed(
            title="Iniciación — Discord",
            description=(
                f"{self._check_task(prog_ini['presentacion'])} Escribir en `#presentacion`\n"
                f"{self._check_task(prog_ini['reaccion_pais'])} Reaccionar al post de 'País' (`#autorol`)\n"
                f"{self._check_task(prog_ini['reaccion_rol'])} Reaccionar al post de 'Rol' (`#autorol`)\n"
                f"{self._check_task(prog_ini['reaccion_social'])} Reaccionar en `#redes-sociales`\n"
                f"{self._check_task(prog_ini['reaccion_reglas'])} Reaccionar en `#reglas`\n"
                f"{self._check_task(prog_ini['general_mensaje'])} Escribir 1 vez en `#general`\n\n"
                f"_{pie}_"
            ),
            color=discord.Color.blue(),
        )
        e_prof = discord.Embed(
            title="Iniciación — perfil (mínimo para reclamar)",
            description=(
                f"{self._check_task(wl, INICIAL_WISHLIST_MIN)} **Wishlist:** {wl}/{INICIAL_WISHLIST_MIN} títulos "
                f"(`/aat-wishlist-set`)\n"
                f"{self._check_task(top10, INICIAL_TOP_MIN)} **Top favoritos:** {top10}/{INICIAL_TOP_MIN} posiciones del 1 al {INICIAL_TOP_MIN} "
                f"(`/aat-anime-top-set`)\n"
                f"{self._check_task(hat, INICIAL_HATED_MIN)} **Odiados:** {hat}/{INICIAL_HATED_MIN} (`/aat-hated-set`)\n\n"
                f"_{pie}_"
            ),
            color=discord.Color.dark_blue(),
        )
        e_ext = discord.Embed(
            title="Perfil ampliado (opcional, hasta el máximo)",
            description=(
                f"• Wishlist: **{wl_show}/{PERFIL_WISHLIST_CAP}**\n"
                f"• Top anime: **{top_cap}/{PERFIL_TOP_CAP}**\n"
                f"• Odiados: **{hat_show}/{PERFIL_HATED_CAP}**\n\n"
                "_Los bonos únicos del top 10 / 30 del anime siguen en `/aat-anime-top-guia`._"
            ),
            color=discord.Color.teal(),
        )
        await interaction.followup.send(embeds=[e_disc, e_prof, e_ext], ephemeral=True)

    @app_commands.command(name="aat-progreso-diaria", description="Muestra tu progreso en las tareas Diarias.")
    async def progreso_diaria(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        fecha, _ = self.db.get_current_date_keys()
        prog_dia = self.db.get_progress_diaria(user_id)
        msg_n = int(prog_dia.get("mensajes_servidor") or 0)
        rx_n = int(prog_dia.get("reacciones_servidor") or 0)
        tr = int(prog_dia.get("trampa_enviada") or 0)
        ts = int(prog_dia.get("trampa_sin_objetivo") or 0)
        tr_ok = tr >= 1 or ts >= 1
        or_n = int(prog_dia.get("oraculo_preguntas") or 0)
        or_ok = or_n >= 1
        rw_pts = self.task_config["rewards"]["diaria"]
        pie = (
            "✅ **Ya reclamaste la recompensa de hoy.**"
            if prog_dia["completado"] == 1
            else f"**Recompensa (una sola vez al día):** {fmt_toque_sentence(int(rw_pts))} + 1 blister — completá **las dos partes** y usá `/aat-reclamar`."
        )
        e_act = discord.Embed(
            title=f"Diaria — actividad y oráculo ({fecha})",
            description=(
                f"{self._check_task(msg_n, 10)} Enviar **10** mensajes en el servidor — {msg_n}/10\n"
                f"{self._check_task(rx_n, 3)} Añadir **3** reacciones en el servidor — {rx_n}/3\n"
                f"{'✅' if or_ok else '❌'} **Oráculo:** 1 pregunta al bot (`?pregunta` o `/aat-consulta`) — {or_n}/1\n\n"
                f"{pie}"
            ),
            color=discord.Color.orange(),
        )
        e_tr = discord.Embed(
            title=f"Diaria — trampa ({fecha})",
            description=(
                f"{'✅' if tr_ok else '❌'} **Trampa:** **una** carta trampa — **con** mención (a alguien) **o** **sin** objetivo (sola).\n"
                f"• Con objetivo: **{tr}/1**\n"
                f"• Sin objetivo: **{ts}/1**\n\n"
                f"{pie}"
            ),
            color=discord.Color.dark_orange(),
        )
        await interaction.followup.send(embeds=[e_act, e_tr], ephemeral=True)

    @app_commands.command(name="aat-progreso-semanal", description="Muestra tu progreso en las tareas Semanales.")
    async def progreso_semanal(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        _, semana = self.db.get_current_date_keys()
        prog_sem = self.db.get_progress_semanal(user_id)
        sem_label = semana.split("-")[-1]
        ip = int(prog_sem.get("impostor_partidas") or 0)
        iv = int(prog_sem.get("impostor_victorias") or 0)
        rw = self.task_config["rewards"]
        pie_sem = (
            "✅ **Ya reclamaste el premio semanal base.**"
            if int(prog_sem.get("completado") or 0) == 1
            else f"**Premio único semanal base:** {fmt_toque_sentence(int(self.task_config['rewards']['semanal']))} + 1 blister — "
            "completá **las tres** tareas (media + foro/videos) y `/aat-reclamar` → `semanal`."
        )
        e_media = discord.Embed(
            title=f"Semanal — memes / fanart (sem. {sem_label})",
            description=(
                f"{self._check_task(prog_sem['media_escrito'])} Publicá **algo** con contenido en **memes**, **fanarts** "
                f"u otro canal de creación que cuente el bot (1 por semana) — **{int(prog_sem.get('media_escrito') or 0)}/1**\n\n"
                f"_{pie_sem}_"
            ),
            color=discord.Color.purple(),
        )
        df = int(prog_sem.get("debate_post") or 0)
        dv = int(prog_sem.get("videos_reaccion") or 0)
        e_foro = discord.Embed(
            title=f"Semanal — foro y #videos (sem. {sem_label})",
            description=(
                f"{self._check_task(prog_sem['debate_post'])} **Foro:** escribir en el foro — **abrí un hilo** en debate "
                f"(anime o manga). **{df}/1**\n"
                f"{self._check_task(prog_sem['videos_reaccion'])} **#videos:** reaccionar a **un** mensaje en **#videos**. **{dv}/1**\n\n"
                f"_{pie_sem}_"
            ),
            color=discord.Color.dark_purple(),
        )
        pie_imp = (
            "✅ **Especial Impostor ya reclamado.**"
            if int(prog_sem.get("completado_especial") or 0) == 1
            else (
                f"**Recompensa aparte:** {fmt_toque_sentence(int(rw.get('especial_semanal', 400)))} + {rw.get('especial_semanal_blisters', 2)} blisters — "
                "`/aat-reclamar` → `semanal_especial`."
            )
        )
        e_imp = discord.Embed(
            title=f"Semanal — Impostor (sem. {sem_label})",
            description=(
                f"{self._check_task(ip, 3)} Jugar **3** partidas — **{ip}/3**\n"
                f"{self._check_task(iv)} Ganar **1** vez como **Impostor** — **{iv}/1**\n\n"
                f"_{pie_imp}_"
            ),
            color=discord.Color.dark_red(),
        )
        ra = int(prog_sem.get("mg_ret_roll_apuesta") or 0)
        rc = int(prog_sem.get("mg_roll_casual") or 0)
        du = int(prog_sem.get("mg_duelo") or 0)
        vo = int(prog_sem.get("mg_voto_dom") or 0)
        pie_mg = (
            "✅ **Minijuegos ya reclamados.**"
            if int(prog_sem.get("completado_minijuegos") or 0) == 1
            else (
                f"**Premio aparte:** {fmt_toque_sentence(int(rw.get('minijuegos_semanal', 150)))} + {rw.get('minijuegos_semanal_blisters', 1)} blister(s) — "
                "`/aat-reclamar` → `semanal_minijuegos`."
            )
        )
        e_mg = discord.Embed(
            title=f"Semanal — minijuegos (sem. {sem_label})",
            description=(
                f"{self._check_task(ra)} Reto con apuesta: `/aat-roll-retar` o duelo (`/aat-duelo-retar`…)\n"
                f"{self._check_task(rc)} Roll casual: `/aat-roll`\n"
                f"{self._check_task(du)} Completar un duelo (`/aat-duelo-aceptar`)\n"
                f"{self._check_task(vo)} Voto semanal: `/aat-voto-semanal`\n\n"
                f"_{pie_mg}_"
            ),
            color=discord.Color.teal(),
        )
        await interaction.followup.send(embeds=[e_media, e_foro, e_imp, e_mg], ephemeral=True)


    # --- ¡¡¡COMANDO RECLAMAR MEJORADO!!! ---
    @app_commands.command(name="aat-reclamar", description="Reclama recompensas: inicial, diaria, semanal, especial Impostor, minijuegos semanal.")
    @app_commands.describe(tipo="Opcional: Elige un tipo específico. Si lo dejas vacío, intenta reclamar TODO lo disponible.")
    async def reclamar(self, interaction: discord.Interaction, tipo: Optional[Literal["inicial", "diaria", "semanal", "semanal_especial", "semanal_minijuegos"]] = None):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        reclamado_algo, mensajes_exito, mensajes_error = reclaim_rewards(
            self.db, self.task_config, user_id, tipo
        )

        if reclamado_algo:
            embed = discord.Embed(title="🎉 ¡Recompensas Reclamadas!", color=discord.Color.green())
            embed.description = "\n".join(mensajes_exito)
            prog_ini = self.db.get_progress_inicial(user_id)
            if int(prog_ini.get("completado") or 0) != 1:
                embed.set_footer(text=MSG_TIP_INICIACION_AL_RECLAMAR)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # Si no se reclamó nada
            if mensajes_error:
                # Si el usuario pidió algo específico y falló
                await interaction.followup.send("\n".join(mensajes_error), ephemeral=True)
            else:
                # Si el usuario pidió "todo" pero no había nada listo
                extra = build_inicial_reclaim_hint(self.db, user_id) if tipo is None else None
                msg = (
                    "No hay recompensas listas para reclamar en este momento.\n\n"
                    f"{MSG_TIP_INICIACION_AL_RECLAMAR}\n\n"
                    "Para **diaria** / **semanal**: `/aat-progreso-diaria` · `/aat-progreso-semanal` "
                    "(o `?diaria` · `?semanal` · `?progreso` en el canal)."
                )
                if extra:
                    msg = f"{msg}\n\n{extra}"
                await interaction.followup.send(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TareasCog(bot))