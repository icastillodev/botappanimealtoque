# cogs/comandos_prefijo.py
import discord
from discord.ext import commands
import logging
import os
from typing import List, Dict, Any

from cogs.economia.db_manager import EconomiaDBManagerV2
from cogs.economia.card_db_manager import CardDBManager
from cogs.economia.cartas_cog import StockCatalogView

class ComandosPrefijoCog(commands.Cog, name="Comandos Prefijo"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(self.__class__.__name__)
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self.card_db: CardDBManager = bot.card_db
        self.task_config = bot.task_config
        
        try:
            self.general_channel_id = int(os.getenv("GENERAL_CHANNEL_ID"))
        except:
            self.general_channel_id = 0

    # --- ¡¡¡EL PORTERO MODIFICADO!!! ---
    async def cog_check(self, ctx):
        """
        Esto se ejecuta ANTES de cualquier comando de este archivo (!).
        """
        # Si estamos en el canal General...
        if ctx.channel.id == self.general_channel_id:
            
            # --- EXCEPCIÓN: Permitir el comando 'usar' ---
            if ctx.command.name == "usar":
                return True
            
            # Bloquear cualquier otro comando (!rank, !inventario, etc.)
            return False
            
        return True

    def _check_task(self, progress_value: int, required_value: int = 1) -> str:
        return "✅" if progress_value >= required_value else "❌"

    # --- COMANDOS DE PROGRESO ---

    @commands.command(aliases=["daily"])
    async def diaria(self, ctx):
        user_id = ctx.author.id
        fecha, _ = self.db.get_current_date_keys()
        prog = self.db.get_progress_diaria(user_id)
        
        embed = discord.Embed(title=f"Progreso Diario ({fecha})", color=discord.Color.orange())
        desc = (
            f"{self._check_task(prog['general_mensajes'], 5)} Escribir 5 mensajes en `#general` ({prog['general_mensajes']}/5)\n"
            f"{self._check_task(prog['media_actividad'])} Participar en canales de Media\n\n"
        )
        if prog['completado'] == 1:
            desc += "✅ **¡Completado!**"
        else:
            desc += f"**Premio:** {self.task_config['rewards']['diaria']} Puntos + 1 Blister."
        
        embed.description = desc
        embed.set_footer(text="Usa !reclamar para obtener tus premios.")
        await ctx.send(embed=embed)

    @commands.command(aliases=["weekly", "semanal"])
    async def semanal_cmd(self, ctx):
        user_id = ctx.author.id
        _, semana = self.db.get_current_date_keys()
        prog = self.db.get_progress_semanal(user_id)

        embed = discord.Embed(title=f"Progreso Semanal", color=discord.Color.purple())
        desc = (
            f"{self._check_task(prog['debate_post'])} Crear 1 post en Foros de Debate\n"
            f"{self._check_task(prog['videos_reaccion'])} Reaccionar en `#videos`\n"
            f"{self._check_task(prog['media_escrito'])} Escribir en canales de Media\n\n"
        )
        if prog['completado'] == 1:
            desc += "✅ **¡Completado!**"
        else:
            desc += f"**Premio:** {self.task_config['rewards']['semanal']} Puntos + 1 Blister."

        embed.description = desc
        embed.set_footer(text="Usa !reclamar para obtener tus premios.")
        await ctx.send(embed=embed)

    @commands.command(aliases=["starter", "iniciacion"])
    async def inicial(self, ctx):
        user_id = ctx.author.id
        prog = self.db.get_progress_inicial(user_id)

        embed = discord.Embed(title="Progreso Inicial", color=discord.Color.blue())
        if prog['completado'] == 1:
            embed.description = "✅ **¡Ya completaste la iniciación!**"
        else:
            embed.description = (
                f"{self._check_task(prog['presentacion'])} Escribir en `#presentacion`\n"
                f"{self._check_task(prog['reaccion_pais'])} Reaccionar 'País' (`#autorol`)\n"
                f"{self._check_task(prog['reaccion_rol'])} Reaccionar 'Rol' (`#autorol`)\n"
                f"{self._check_task(prog['reaccion_social'])} Reaccionar `#redes-sociales`\n"
                f"{self._check_task(prog['reaccion_reglas'])} Reaccionar `#reglas`\n"
                f"{self._check_task(prog['general_mensaje'])} Escribir en `#general`\n\n"
                f"**Premio:** {self.task_config['rewards']['inicial']} Puntos + 3 Blisters."
            )
        
        embed.set_footer(text="Usa !reclamar para obtener tus premios.")
        await ctx.send(embed=embed)

    @commands.command()
    async def progreso(self, ctx):
        await self.inicial(ctx)
        await self.diaria(ctx)
        await self.semanal_cmd(ctx)

    # --- COMANDOS DE ACCIÓN ---

    @commands.command(aliases=["rank"])
    async def top(self, ctx):
        top_actual = self.db.get_top_users("actual", limit=5)
        text = ""
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, u in enumerate(top_actual):
            try:
                user = self.bot.get_user(u['user_id']) or await self.bot.fetch_user(u['user_id'])
                name = user.display_name
            except: name = "Desconocido"
            text += f"{medals[i]} {name} • **{u['puntos_actuales']}**\n"

        embed = discord.Embed(title="🏆 Top 5 Puntos Actuales", description=text or "Nadie aún.", color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.command()
    async def reclamar(self, ctx):
        user_id = ctx.author.id
        mensajes = []
        
        prog_ini = self.db.get_progress_inicial(user_id)
        if prog_ini['completado'] == 0 and all(prog_ini[k] >= 1 for k in ['presentacion', 'reaccion_pais', 'reaccion_rol', 'reaccion_social', 'reaccion_reglas', 'general_mensaje']):
            self.db.modify_points(user_id, self.task_config['rewards']['inicial'])
            self.db.modify_blisters(user_id, "trampa", 3)
            self.db.claim_reward(user_id, "inicial")
            mensajes.append("✅ **Inicial:** ¡Reclamado!")

        prog_dia = self.db.get_progress_diaria(user_id)
        if prog_dia['completado'] == 0 and (prog_dia['general_mensajes'] >= 5 and prog_dia['media_actividad'] >= 1):
            self.db.modify_points(user_id, self.task_config['rewards']['diaria'])
            self.db.modify_blisters(user_id, "trampa", 1)
            self.db.claim_reward(user_id, "diaria")
            mensajes.append("✅ **Diaria:** ¡Reclamado!")

        prog_sem = self.db.get_progress_semanal(user_id)
        if prog_sem['completado'] == 0 and (prog_sem['debate_post'] >= 1 and prog_sem['videos_reaccion'] >= 1 and prog_sem['media_escrito'] >= 1):
            self.db.modify_points(user_id, self.task_config['rewards']['semanal'])
            self.db.modify_blisters(user_id, "trampa", 1)
            self.db.claim_reward(user_id, "semanal")
            mensajes.append("✅ **Semanal:** ¡Reclamado!")

        if mensajes:
            embed = discord.Embed(title="🎉 Recompensas obtenidas", description="\n".join(mensajes), color=discord.Color.green())
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Nada para reclamar. Usa `!progreso`.")

    @commands.command()
    async def inventario(self, ctx):
        user_id = ctx.author.id
        eco = self.db.get_user_economy(user_id)
        blisters = self.db.get_blisters_for_user(user_id)
        
        embed = discord.Embed(title=f"Inventario de {ctx.author.display_name}", color=discord.Color.dark_green())
        embed.add_field(name="🪙 Puntos", value=str(eco['puntos_actuales']))
        
        b_text = "Ninguno"
        if blisters:
            b_text = "\n".join([f"• {b['blister_tipo'].capitalize()}: x{b['cantidad']}" for b in blisters])
        embed.add_field(name="🃏 Blisters", value=b_text, inline=False)
        await ctx.send(embed=embed)

    @commands.command(aliases=["puntos"])
    async def mis_puntos_cmd(self, ctx):
        """Atajo para ver solo los puntos."""
        user_id = ctx.author.id
        eco = self.db.get_user_economy(user_id)
        await ctx.send(f"🪙 **{ctx.author.display_name}**, tienes **{eco['puntos_actuales']}** puntos.")

    @commands.command(name="miscartas")
    async def mis_cartas_cmd(self, ctx):
        """Muestra las cartas en texto simple si se quiere."""
        cartas = self.db.get_cards_in_inventory(ctx.author.id)
        if not cartas:
            await ctx.send("No tienes cartas.")
            return
        
        lines = []
        for c in cartas:
             c_data = self.card_db.get_carta_stock_by_id(c['carta_id'])
             if c_data:
                 lines.append(f"#{c['carta_id']} **{c_data['nombre']}** (x{c['cantidad']})")
        
        embed = discord.Embed(title="Tus Cartas", description="\n".join(lines), color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command()
    async def catalogo(self, ctx):
        all_cards = self.card_db.get_all_cards_stock()
        if not all_cards:
            await ctx.send("El catálogo está vacío.")
            return
        view = StockCatalogView(ctx.author.id, all_cards, "Catálogo Global")
        embed = view.get_page_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def abrir(self, ctx):
        user_id = ctx.author.id
        blisters = self.db.get_blisters_for_user(user_id)
        
        if not blisters:
            await ctx.send("No tienes blisters.")
            return
            
        count = 0
        cartas_nuevas = []
        
        for b in blisters:
            cant = b['cantidad']
            if cant > 0:
                self.db.modify_blisters(user_id, b['blister_tipo'], -cant)
                count += cant
                for _ in range(cant * 3):
                    c = self.card_db.get_random_card_by_rarity()
                    if c:
                        self.db.add_card_to_inventory(user_id, c['carta_id'], 1)
                        cartas_nuevas.append(c['nombre'])

        if cartas_nuevas:
            resumen = {}
            for nombre in cartas_nuevas:
                resumen[nombre] = resumen.get(nombre, 0) + 1
            
            text = "**Cartas:**\n" + "\n".join([f"{k} x{v}" for k, v in resumen.items()])
            if len(text) > 2000: text = text[:1990] + "..."
            await ctx.send(f"💥 ¡Abriste {count} blisters!\n{text}")
        else:
            await ctx.send("Error de stock.")

    @commands.command(aliases=["ayudaeconomia"])
    async def ayudaeconomiacomandos(self, ctx):
        embed = discord.Embed(title="Ayuda Comandos (!)", description="`!progreso`, `!reclamar`, `!inventario`, `!abrir`, `!top`, `!usar`", color=discord.Color.gold())
        await ctx.send(embed=embed)
        
    @commands.command(aliases=["usarcarta"])
    async def usar(self, ctx, carta_id: str):
        if not carta_id.isdigit():
            await ctx.send("Debes poner el ID numérico de la carta. Ej: `!usar 5`")
            return
        cid = int(carta_id)
        user_id = ctx.author.id
        uso = self.db.get_card_usage_history(user_id)
        if len(uso) >= 5:
            await ctx.send("⏳ Estás en enfriamiento (máx 5 cartas cada 10 min).")
            return
        if not self.db.get_card_from_inventory(user_id, cid):
            await ctx.send("❌ No tienes esa carta (o se te acabaron).")
            return
        self.db.use_card_from_inventory(user_id, cid)
        self.db.log_card_usage(user_id)
        c_data = self.card_db.get_carta_stock_by_id(cid)
        
        embed = discord.Embed(title="¡Carta Activada!", description=f"**{ctx.author.name}** usó **{c_data['nombre']}**", color=discord.Color.red())
        if c_data['url_imagen']:
            embed.set_image(url=c_data['url_imagen'])
        embed.add_field(name="Efecto", value=c_data['efecto'])
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ComandosPrefijoCog(bot))