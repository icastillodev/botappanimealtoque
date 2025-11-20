# cogs/comandos_prefijo.py
import discord
from discord.ext import commands
import logging
import datetime
import time
from typing import List, Dict, Any

# Importamos las DBs para poder leer los datos
from cogs.economia.db_manager import EconomiaDBManagerV2
from cogs.economia.card_db_manager import CardDBManager
# Reutilizamos la vista del catálogo para no reescribirla
from cogs.economia.cartas_cog import StockCatalogView

class ComandosPrefijoCog(commands.Cog, name="Comandos Prefijo"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(self.__class__.__name__)
        self.db: EconomiaDBManagerV2 = bot.economia_db
        self.card_db: CardDBManager = bot.card_db
        self.task_config = bot.task_config

    def _check_task(self, progress_value: int, required_value: int = 1) -> str:
        return "✅" if progress_value >= required_value else "❌"

    # --- COMANDOS DE PROGRESO ---

    @commands.command(aliases=["daily"])
    async def diaria(self, ctx):
        """Muestra el progreso de las tareas diarias."""
        user_id = ctx.author.id
        fecha, _ = self.db.get_current_date_keys()
        prog = self.db.get_progress_diaria(user_id)
        
        embed = discord.Embed(title=f"Progreso Diario ({fecha})", color=discord.Color.orange())
        desc = (
            f"{self._check_task(prog['general_mensajes'], 5)} Escribir 5 mensajes en `#general` ({prog['general_mensajes']}/5)\n"
            f"{self._check_task(prog['media_actividad'])} Participar en canales de Media (Fanarts, etc)\n\n"
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
        """Muestra el progreso de las tareas semanales."""
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
        """Muestra el progreso de iniciación."""
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
        """Muestra un resumen de todos los progresos."""
        # Simplemente llamamos a los otros embeds uno por uno
        await self.inicial(ctx)
        await self.diaria(ctx)
        await self.semanal_cmd(ctx)

    # --- COMANDOS DE AYUDA ---

    @commands.command(aliases=["ayudaeconomia"])
    async def ayudaeconomiacomandos(self, ctx):
        """Lista los comandos con prefijo."""
        embed = discord.Embed(title="Ayuda de Comandos (!)", color=discord.Color.gold())
        embed.description = (
            "**Progresos:** `!diaria`, `!semanal`, `!iniciacion`, `!progreso`\n"
            "**Acciones:** `!reclamar` (Reclama todo), `!abrir` (Abre todo)\n"
            "**Cartas:** `!inventario`, `!catalogo`, `!usarcarta [ID]`\n"
            "**Info:** `!top`, `!puntos`"
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["ayudapuntos"])
    async def ayudapuntos_cmd(self, ctx):
        """Explica cómo ganar puntos."""
        embed = discord.Embed(title="¿Cómo ganar puntos?", color=discord.Color.green())
        embed.description = (
            "**1. Completa Tareas:** Revisa qué te falta con `!progreso`.\n"
            "**2. Reclama:** Cuando termines, escribe `!reclamar` para obtener Puntos y Sobres.\n"
            "**3. Abre Sobres:** Usa `!abrir` para conseguir cartas.\n"
            "**4. Gasta:** Compra roles y mejoras en la tienda (/aat_tienda_ver)."
        )
        await ctx.send(embed=embed)

    # --- COMANDOS DE ACCIÓN ---

    @commands.command(aliases=["rank"])
    async def top(self, ctx):
        """Muestra el ranking general."""
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
        embed.set_footer(text="¿Cómo conseguir puntos? Usa !puntos")
        await ctx.send(embed=embed)

    @commands.command()
    async def reclamar(self, ctx):
        """Intenta reclamar TODAS las recompensas disponibles."""
        user_id = ctx.author.id
        mensajes = []
        
        # 1. Inicial
        prog_ini = self.db.get_progress_inicial(user_id)
        if prog_ini['completado'] == 0 and all(prog_ini[k] >= 1 for k in ['presentacion', 'reaccion_pais', 'reaccion_rol', 'reaccion_social', 'reaccion_reglas', 'general_mensaje']):
            self.db.modify_points(user_id, self.task_config['rewards']['inicial'])
            self.db.modify_blisters(user_id, "trampa", 3)
            self.db.claim_reward(user_id, "inicial")
            mensajes.append("✅ **Inicial:** ¡Reclamado! (1000 pts + 3 blisters)")

        # 2. Diaria
        prog_dia = self.db.get_progress_diaria(user_id)
        if prog_dia['completado'] == 0 and (prog_dia['general_mensajes'] >= 5 and prog_dia['media_actividad'] >= 1):
            self.db.modify_points(user_id, self.task_config['rewards']['diaria'])
            self.db.modify_blisters(user_id, "trampa", 1)
            self.db.claim_reward(user_id, "diaria")
            mensajes.append("✅ **Diaria:** ¡Reclamado! (50 pts + 1 blister)")

        # 3. Semanal
        prog_sem = self.db.get_progress_semanal(user_id)
        if prog_sem['completado'] == 0 and (prog_sem['debate_post'] >= 1 and prog_sem['videos_reaccion'] >= 1 and prog_sem['media_escrito'] >= 1):
            self.db.modify_points(user_id, self.task_config['rewards']['semanal'])
            self.db.modify_blisters(user_id, "trampa", 1)
            self.db.claim_reward(user_id, "semanal")
            mensajes.append("✅ **Semanal:** ¡Reclamado! (300 pts + 1 blister)")

        if mensajes:
            embed = discord.Embed(title="🎉 ¡Recompensas obtenidas!", description="\n".join(mensajes), color=discord.Color.green())
            embed.set_footer(text="Mira el !top, abre sobres con !abrir o revisa tu !inventario")
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ No tienes nada para reclamar ahora. Usa `!progreso` para ver qué te falta.")

    @commands.command()
    async def inventario(self, ctx):
        """Muestra tu inventario."""
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

    @commands.command()
    async def catalogo(self, ctx):
        """Muestra el catálogo de cartas."""
        all_cards = self.card_db.get_all_cards_stock()
        if not all_cards:
            await ctx.send("El catálogo está vacío.")
            return
        # Reutilizamos la vista de paginación que ya creamos en cartas_cog
        view = StockCatalogView(ctx.author.id, all_cards, "Catálogo Global")
        embed = view.get_page_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def abrir(self, ctx):
        """Abre TODOS los blisters."""
        user_id = ctx.author.id
        blisters = self.db.get_blisters_for_user(user_id)
        
        if not blisters:
            await ctx.send("No tienes blisters para abrir.")
            return
            
        count = 0
        cartas_nuevas = []
        
        for b in blisters:
            cant = b['cantidad']
            if cant > 0:
                self.db.modify_blisters(user_id, b['blister_tipo'], -cant)
                count += cant
                for _ in range(cant * 3):
                    # Gacha sin filtro de tipo
                    c = self.card_db.get_random_card_by_rarity()
                    if c:
                        self.db.add_card_to_inventory(user_id, c['carta_id'], 1)
                        cartas_nuevas.append(c['nombre'])

        if cartas_nuevas:
            # Resumen simple
            resumen = {}
            for nombre in cartas_nuevas:
                resumen[nombre] = resumen.get(nombre, 0) + 1
            
            text = "**Cartas obtenidas:**\n" + "\n".join([f"{k} x{v}" for k, v in resumen.items()])
            if len(text) > 2000: text = text[:1990] + "..."
            
            await ctx.send(f"💥 ¡Abriste {count} blisters!\n{text}")
        else:
            await ctx.send("Abriste los sobres pero estaban vacíos (Error de stock).")

    @commands.command(aliases=["usarcarta"])
    async def usar(self, ctx, carta_id: str):
        """Usa una carta por su ID."""
        if not carta_id.isdigit():
            await ctx.send("Debes poner el ID numérico de la carta. Ej: `!usarcarta 5`")
            return
            
        cid = int(carta_id)
        user_id = ctx.author.id
        
        # 1. Check cooldown
        uso = self.db.get_card_usage_history(user_id)
        if len(uso) >= 5:
            await ctx.send("⏳ Estás en enfriamiento (máx 5 cartas cada 10 min).")
            return

        # 2. Check inventario
        if not self.db.get_card_from_inventory(user_id, cid):
            await ctx.send("❌ No tienes esa carta (o se te acabaron).")
            return

        # 3. Usar
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