# cogs/economia/tareas_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import time
import logging
import datetime
from typing import Literal, Optional

from .db_manager import EconomiaDBManagerV2
from .reclamar_service import reclaim_rewards

class TareasCog(commands.Cog, name="Economia Tareas"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self.log = logging.getLogger(self.__class__.__name__)
        self.task_config = bot.task_config
        super().__init__()
        
    def _check_task(self, progress_value: int, required_value: int = 1) -> str:
        return "✅" if progress_value >= required_value else "❌"

    @app_commands.command(name="aat_progreso_iniciacion", description="Muestra tu progreso en las tareas de Iniciación.")
    async def progreso_iniciacion(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        prog_ini = self.db.get_progress_inicial(user_id)
        if prog_ini['completado'] == 1:
            embed = discord.Embed(title="Progreso: Tareas de Iniciación", description="✅ ¡Ya has completado todas las tareas de iniciación!", color=discord.Color.green())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        embed_ini = discord.Embed(title="Progreso: Tareas de Iniciación", color=discord.Color.blue())
        desc_ini = (
            f"{self._check_task(prog_ini['presentacion'])} Escribir en `#presentacion`\n"
            f"{self._check_task(prog_ini['reaccion_pais'])} Reaccionar al post de 'País' (`#autorol`)\n"
            f"{self._check_task(prog_ini['reaccion_rol'])} Reaccionar al post de 'Rol' (`#autorol`)\n"
            f"{self._check_task(prog_ini['reaccion_social'])} Reaccionar en `#redes-sociales`\n"
            f"{self._check_task(prog_ini['reaccion_reglas'])} Reaccionar en `#reglas`\n"
            f"{self._check_task(prog_ini['general_mensaje'])} Escribir 1 vez en `#general`\n\n"
            f"**Recompensa:** {self.task_config['rewards']['inicial']} Puntos + 3 Blisters.\n"
            "--- \n"
            "**¿Ya habías hecho esto?** Usa `/aat_verificar_antiguas` para que el bot revise.\n"
            "*Cuando completes todo, usa `/aat_reclamar`.*"
        )
        embed_ini.description = desc_ini
        await interaction.followup.send(embed=embed_ini, ephemeral=True)

    @app_commands.command(name="aat_progreso_diaria", description="Muestra tu progreso en las tareas Diarias.")
    async def progreso_diaria(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        fecha, _ = self.db.get_current_date_keys()
        prog_dia = self.db.get_progress_diaria(user_id)
        embed_dia = discord.Embed(title=f"Progreso: Tareas Diarias ({fecha})", color=discord.Color.orange())

        msg_n = int(prog_dia.get("mensajes_servidor") or 0)
        rx_n = int(prog_dia.get("reacciones_servidor") or 0)
        tr = int(prog_dia.get("trampa_enviada") or 0)
        ts = int(prog_dia.get("trampa_sin_objetivo") or 0)
        tr_ok = tr >= 1 or ts >= 2
        or_n = int(prog_dia.get("oraculo_preguntas") or 0)
        or_ok = or_n >= 1
        desc_dia = (
            f"{self._check_task(msg_n, 10)} Enviar **10** mensajes en el servidor (cualquier canal de texto) — {msg_n}/10\n"
            f"{self._check_task(rx_n, 3)} Añadir **3** reacciones en el servidor — {rx_n}/3\n"
            f"{'✅' if tr_ok else '❌'} **Trampa:** contra alguien (`/usar`+objetivo) **o** 2× trampa sin objetivo — Dirigida: {tr}/1 · Casual: {ts}/2\n"
            f"{'✅' if or_ok else '❌'} **Oráculo:** 1 pregunta al bot (`!pregunta` o `/aat_consulta`) — {or_n}/1\n\n"
        )
        if prog_dia['completado'] == 1:
            desc_dia += "✅ **¡Ya reclamaste la recompensa de hoy!**"
        else:
            desc_dia += f"**Recompensa:** {self.task_config['rewards']['diaria']} Puntos + 1 Blister.\n*Cuando completes todo, usa `/aat_reclamar`.*"
        embed_dia.description = desc_dia
        await interaction.followup.send(embed=embed_dia, ephemeral=True)

    @app_commands.command(name="aat_progreso_semanal", description="Muestra tu progreso en las tareas Semanales.")
    async def progreso_semanal(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        _, semana = self.db.get_current_date_keys()
        prog_sem = self.db.get_progress_semanal(user_id)
        embed_sem = discord.Embed(title=f"Progreso: Tareas Semanales (Semana {semana.split('-')[-1]})", color=discord.Color.purple())
        ip = int(prog_sem.get("impostor_partidas") or 0)
        iv = int(prog_sem.get("impostor_victorias") or 0)
        desc_sem = (
            f"{self._check_task(prog_sem['debate_post'])} Escribir en el **foro** (nuevo hilo en debate anime/manga)\n"
            f"{self._check_task(prog_sem['media_escrito'])} Enviar un **meme**, **cosplay** o **dibujo** (mensaje en los canales de media)\n"
            f"{self._check_task(prog_sem['videos_reaccion'])} Reaccionar en `#videos`\n\n"
            "**Especial semanal (Impostor)**\n"
            f"{self._check_task(ip, 3)} Jugar al menos **3** partidas a Impostor — {ip}/3\n"
            f"{self._check_task(iv)} Ganar **1** vez como Impostor en la semana\n\n"
        )
        if prog_sem['completado'] == 1:
            desc_sem += "✅ **¡Ya reclamaste la recompensa semanal base!**"
        else:
            desc_sem += f"**Recompensa semanal:** {self.task_config['rewards']['semanal']} Puntos + 1 Blister.\n*Usa `/aat_reclamar`.*\n"
        rw = self.task_config["rewards"]
        if int(prog_sem.get("completado_especial") or 0) == 1:
            desc_sem += "\n✅ **Especial semanal:** ya reclamado."
        else:
            desc_sem += (
                f"\n**Recompensa especial:** {rw.get('especial_semanal', 400)} pts + "
                f"{rw.get('especial_semanal_blisters', 2)} Blisters — `/aat_reclamar` → `semanal_especial`."
            )
        ra = int(prog_sem.get("mg_ret_roll_apuesta") or 0)
        rc = int(prog_sem.get("mg_roll_casual") or 0)
        du = int(prog_sem.get("mg_duelo") or 0)
        vo = int(prog_sem.get("mg_voto_dom") or 0)
        desc_sem += (
            "\n\n**Minijuegos semanal** (recompensa aparte)\n"
            f"{self._check_task(ra)} Reto con apuesta: `/aat_roll_retar` **o** completar un duelo (`/aat_duelo_retar`…)\n"
            f"{self._check_task(rc)} Roll casual: `/aat_roll`\n"
            f"{self._check_task(du)} Completar un **duelo** (`/aat_duelo_aceptar`)\n"
            f"{self._check_task(vo)} Voto semanal: `/aat_voto_semanal`\n"
        )
        if int(prog_sem.get("completado_minijuegos") or 0) == 1:
            desc_sem += "\n✅ **Minijuegos:** ya reclamado."
        else:
            desc_sem += (
                f"\n**Premio minijuegos:** {rw.get('minijuegos_semanal', 150)} pts + "
                f"{rw.get('minijuegos_semanal_blisters', 1)} Blister — `/aat_reclamar` → `semanal_minijuegos`."
            )
        embed_sem.description = desc_sem
        await interaction.followup.send(embed=embed_sem, ephemeral=True)


    # --- ¡¡¡COMANDO RECLAMAR MEJORADO!!! ---
    @app_commands.command(name="aat_reclamar", description="Reclama recompensas: inicial, diaria, semanal, especial Impostor, minijuegos semanal.")
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
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # Si no se reclamó nada
            if mensajes_error:
                # Si el usuario pidió algo específico y falló
                await interaction.followup.send("\n".join(mensajes_error), ephemeral=True)
            else:
                # Si el usuario pidió "todo" pero no había nada listo
                await interaction.followup.send("No hay recompensas listas para reclamar en este momento. Usa `/aat_progreso...` para ver qué te falta.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TareasCog(bot))