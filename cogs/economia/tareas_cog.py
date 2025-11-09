# cogs/economia/tareas_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import time
import logging
import datetime
from typing import Literal

from .db_manager import EconomiaDBManagerV2

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
            "*Cuando completes todo, usa `/aat_reclamar inicial`.*"
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
        
        # --- ¡¡¡MODIFICADO!!! ---
        check_general = self._check_task(prog_dia['general_mensajes'], 5)
        desc_dia = (
            f"{check_general} Escribir 5 mensajes en `#general` (Llevas {prog_dia['general_mensajes']}/5)\n"
            # (Línea de debate eliminada)
            f"{self._check_task(prog_dia['media_actividad'])} Participar (escribir/reaccionar) en canales de Media (Fanarts, etc)\n\n"
        )
        if prog_dia['completado'] == 1:
            desc_dia += "✅ **¡Ya reclamaste la recompensa de hoy!**"
        else:
            desc_dia += f"**Recompensa:** {self.task_config['rewards']['diaria']} Puntos + 1 Blister.\n*Cuando completes todo, usa `/aat_reclamar diaria`.*"
        embed_dia.description = desc_dia
        await interaction.followup.send(embed=embed_dia, ephemeral=True)

    @app_commands.command(name="aat_progreso_semanal", description="Muestra tu progreso en las tareas Semanales.")
    async def progreso_semanal(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        _, semana = self.db.get_current_date_keys()
        prog_sem = self.db.get_progress_semanal(user_id)
        embed_sem = discord.Embed(title=f"Progreso: Tareas Semanales (Semana {semana.split('-')[-1]})", color=discord.Color.purple())
        desc_sem = (
            f"{self._check_task(prog_sem['debate_post'])} Crear 1 post en Foros de Debate\n"
            f"{self._check_task(prog_sem['videos_reaccion'])} Reaccionar a un post en `#videos`\n"
            f"{self._check_task(prog_sem['media_escrito'])} Escribir en canales de Media (Fanarts, etc)\n\n"
        )
        if prog_sem['completado'] == 1:
            desc_sem += "✅ **¡Ya reclamaste la recompensa de esta semana!**"
        else:
            desc_sem += f"**Recompensa:** {self.task_config['rewards']['semanal']} Puntos + 1 Blister.\n*Cuando completes todo, usa `/aat_reclamar semanal`.*"
        embed_sem.description = desc_sem
        await interaction.followup.send(embed=embed_sem, ephemeral=True)


    @app_commands.command(name="aat_reclamar", description="Reclama tu recompensa de tareas (diaria, semanal, o inicial).")
    @app_commands.describe(tipo="El tipo de recompensa que quieres reclamar.")
    async def reclamar(self, interaction: discord.Interaction, tipo: Literal["inicial", "diaria", "semanal"]):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        if tipo == "inicial":
            prog = self.db.get_progress_inicial(user_id)
            if prog['completado'] == 1:
                await interaction.followup.send("Ya has reclamado esta recompensa.", ephemeral=True)
                return
            if all(prog[key] >= 1 for key in ['presentacion', 'reaccion_pais', 'reaccion_rol', 'reaccion_social', 'reaccion_reglas', 'general_mensaje']):
                recompensa = self.task_config['rewards']['inicial']
                self.db.modify_points(user_id, recompensa)
                self.db.modify_blisters(user_id, "trampa", 3)
                self.db.claim_reward(user_id, "inicial")
                embed = discord.Embed(title="🎉 ¡Tareas de Iniciación Completadas!", description=f"¡Felicidades! Has completado todas las tareas.\n\nRecibiste:\n• **{recompensa} Puntos** 🪙\n• **3 Blisters de Cartas Trampa** 🃏", color=discord.Color.green())
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("Aún no has completado todas las tareas de iniciación. Usa `/aat_progreso_iniciacion` para ver qué te falta.", ephemeral=True)
        
        elif tipo == "diaria":
            prog = self.db.get_progress_diaria(user_id)
            if prog['completado'] == 1:
                await interaction.followup.send("Ya has reclamado la recompensa diaria de hoy.", ephemeral=True)
                return
            
            # --- ¡¡¡MODIFICADO!!! ---
            # Eliminada la comprobación de 'debate_actividad'
            if (prog['general_mensajes'] >= 5 and 
                prog['media_actividad'] >= 1):
                
                recompensa = self.task_config['rewards']['diaria']
                self.db.modify_points(user_id, recompensa)
                self.db.modify_blisters(user_id, "trampa", 1)
                self.db.claim_reward(user_id, "diaria")
                embed = discord.Embed(title="✅ ¡Tareas Diarias Completadas!",
                                      description=f"¡Buen trabajo!\n\nRecibiste:\n• **{recompensa} Puntos** 🪙\n• **1 Blister de Cartas Trampa** 🃏",
                                      color=discord.Color.green())
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("Aún no has completado todas las tareas diarias. Usa `/aat_progreso_diaria` para ver qué te falta.", ephemeral=True)

        elif tipo == "semanal":
            prog = self.db.get_progress_semanal(user_id)
            if prog['completado'] == 1:
                await interaction.followup.send("Ya has reclamado la recompensa de esta semana.", ephemeral=True)
                return
            if (prog['debate_post'] >= 1 and 
                prog['videos_reaccion'] >= 1 and 
                prog['media_escrito'] >= 1):
                
                recompensa = self.task_config['rewards']['semanal']
                self.db.modify_points(user_id, recompensa)
                self.db.modify_blisters(user_id, "trampa", 1)
                self.db.claim_reward(user_id, "semanal")
                embed = discord.Embed(title="📅 ¡Tareas Semanales Completadas!",
                                      description=f"¡Excelente trabajo esta semana!\n\nRecibiste:\n• **{recompensa} Puntos** 🪙\n• **1 Blister de Cartas Trampa** 🃏",
                                      color=discord.Color.gold())
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("Aún no has completado todas las tareas semanales. Usa `/aat_progreso_semanal` para ver qué te falta.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TareasCog(bot))