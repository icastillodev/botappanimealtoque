# cogs/impostor/stats_commands.py
import discord
from discord import app_commands
from discord.ext import commands

from .stats import stats_store

class StatsCog(commands.Cog):
    """Comandos de estadísticas: /mis_estadisticas y /tabla_impostor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="mis_estadisticas", description="Ver tus estadísticas en Impostor")
    async def mis_estadisticas(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("Usá este comando dentro del servidor.", ephemeral=True)
        iw, sw = await stats_store.get_user(interaction.guild_id, interaction.user.id)  # type: ignore
        total = iw + sw
        await interaction.response.send_message(
            f"📊 Tus estadísticas:\n"
            f"• 🕵️ Impostor: **{iw}**\n"
            f"• 🛡️ Social: **{sw}**\n"
            f"• Total: **{total}**",
            ephemeral=True
        )

    @app_commands.command(name="tabla_impostor", description="Tabla de victorias (Impostor/Social) del servidor")
    async def tabla_impostor(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("Usá este comando dentro del servidor.", ephemeral=True)

        rows = await stats_store.get_all(interaction.guild_id)  # type: ignore
        if not rows:
            return await interaction.response.send_message("Aún no hay partidas registradas.", ephemeral=True)

        # Armamos lista ordenada (ya viene ordenada por total desc desde el query)
        lines = []
        lines.append("🏆 **Tabla de victorias — IMPOSITOR**")
        lines.append("Usuario — Impostor | Social | Total")
        count = 0
        for user_id, iw, sw, total in rows:
            # Mostramos hasta ~50 para no spamear; si querés full, remove el corte
            mention = f"<@{user_id}>"
            lines.append(f"{mention} — {iw} | {sw} | {total}")
            count += 1
            if count >= 50:
                lines.append(f"... y {len(rows) - 50} más.")
                break

        # pública (no ephemeral) para que todos vean la tabla
        await interaction.response.send_message("\n".join(lines))

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
