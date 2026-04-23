# cogs/votacion/poll_view.py
import discord
from discord.ext import commands
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import datetime

if TYPE_CHECKING:
    from .db_manager import PollDBManagerV5

# --- El Embed (Helper) ---
def create_poll_embed(
    poll_data: Dict[str, Any],
    author: Optional[discord.User] = None
) -> discord.Embed:
    """Genera un embed de Discord a partir de los datos de la votación."""
    
    title = poll_data.get('title', 'Votación')
    description = poll_data.get('description') or "Vota usando los botones."
    poll_id = poll_data.get('poll_id')
    if poll_id:
        description = f"**ID de Votación: #{poll_id}**\n{description}"
    
    is_active = poll_data.get('is_active', True)
    
    if is_active:
        embed = discord.Embed(
            title=f"🗳️ Votación: {title}",
            description=description,
            color=discord.Color.blue()
        )
    else:
        embed = discord.Embed(
            title=f"VOTACIÓN CERRADA: {title}",
            description=description,
            color=discord.Color.red()
        )

    if poll_data.get('link_url'):
        embed.description += f"\n\n[Referencia]({poll_data['link_url']})"
    
    if poll_data.get('image_url'):
        embed.set_image(url=poll_data.get('image_url'))

    end_timestamp = poll_data.get('end_timestamp')
    if is_active and end_timestamp:
        end_time_str = discord.utils.format_dt(datetime.datetime.fromtimestamp(end_timestamp), style='R')
        embed.description += f"\n\n*Esta votación finaliza {end_time_str}.*"

    options = poll_data.get('options', [])
    total_votes = sum(opt.get('vote_count', 0) for opt in options)
    
    winner_icon = "✅"
    tie_icon = "🟡"
    loser_icon = "" 
    
    max_votes_count = 0
    if options:
        vote_counts = [opt.get('vote_count', 0) for opt in options]
        max_votes_count = max(vote_counts) if vote_counts else 0
        
    is_tie = False
    if max_votes_count > 0:
        winners_count = sum(1 for v in vote_counts if v == max_votes_count)
        if winners_count > 1:
            is_tie = True

    display_format = poll_data.get('formato_votos', 'ambos')

    # Mientras esté activa: en los campos no mostrar número bruto de votos (solo %).
    public_hide_counts = bool(is_active)

    # Marcador en la descripción: TODOS ven % de cada opción y quién va arriba, aunque no hayan votado.
    if is_active and display_format != 'oculto' and options:
        lines_m = []
        for opt in options:
            label = opt.get("label", "Opción")
            vc = int(opt.get("vote_count", 0) or 0)
            pct = (vc / total_votes * 100.0) if total_votes > 0 else 0.0
            lines_m.append(f"• **{label}** — **{pct:.1f}%**")
        block_m = (
            "\n\n**📊 Marcador en vivo** (lo ve todo el mundo; no hace falta haber votado)\n"
            + "\n".join(lines_m)
        )
        if total_votes == 0:
            block_m += "\n_**0** votos todavía: todos los % muestran 0 hasta el primer voto._"
        else:
            winners_list = [
                opt.get("label", "N/A")
                for opt in options
                if int(opt.get("vote_count", 0) or 0) == max_votes_count and max_votes_count > 0
            ]
            pct_leader = (max_votes_count / total_votes * 100.0) if total_votes else 0.0
            if len(winners_list) > 1:
                block_m += (
                    f"\n**Empate al frente:** {', '.join(winners_list)} "
                    f"(**{pct_leader:.1f}%** c/u sobre el total de votos)"
                )
            elif len(winners_list) == 1:
                block_m += f"\n**Va ganando:** **{winners_list[0]}** (**{pct_leader:.1f}%** del total)"
        embed.description += block_m

    if display_format == 'oculto' and is_active:
        for option in options:
            embed.add_field(name=f"❓ {option.get('label', 'Opción desconocida')}", value="Votos ocultos", inline=False)
    else:
        for option in options:
            label = option.get('label', 'Opción desconocida')
            vote_count = option.get('vote_count', 0)
            
            icon = loser_icon
            if vote_count == max_votes_count and max_votes_count > 0:
                icon = tie_icon if is_tie else winner_icon
            
            percentage = 0.0
            if total_votes > 0:
                percentage = (vote_count / total_votes) * 100
            
            value_str = ""
            if public_hide_counts:
                # Activa: solo porcentaje visible para todos
                value_str = f"{percentage:.1f}%"
            else:
                if display_format == 'ambos':
                    value_str = f"**{vote_count}** votos ({percentage:.1f}%)"
                elif display_format == 'numeros':
                    value_str = f"**{vote_count}** votos"
                elif display_format == 'porcentaje':
                    value_str = f"{percentage:.1f}%"
                elif display_format == 'oculto' and not is_active:
                    value_str = f"**{vote_count}** votos ({percentage:.1f}%)"
            
            embed.add_field(
                name=f"{icon} {label}".strip(),
                value=value_str,
                inline=False
            )
            
    if author:
        embed.set_footer(text=f"Votación creada por {author.display_name}", icon_url=author.display_avatar)
    
    if not is_active:
        winner_text = ""
        
        winners_list = []
        if max_votes_count > 0:
            for opt in options:
                if opt.get('vote_count', 0) == max_votes_count:
                    winners_list.append(opt.get('label', 'N/A'))

        if not winners_list:
            winner_text = "EL GANADOR ES: NADIE (0 VOTOS)"
        elif is_tie:
            winner_text = f"HAY UN EMPATE ENTRE: {', '.join(winners_list)}"
        else:
            winner_text = f"EL GANADOR ES: {winners_list[0]}"

        if max_votes_count > 0:
            percentage = (max_votes_count / total_votes) * 100 if total_votes > 0 else 0
            
            if display_format == 'ambos' or (display_format == 'oculto' and not is_active):
                winner_text += f"\nCON **{max_votes_count}** VOTOS ({percentage:.1f}%)"
            elif display_format == 'numeros':
                winner_text += f"\nCON **{max_votes_count}** VOTOS"
            elif display_format == 'porcentaje':
                winner_text += f"\nCON EL {percentage:.1f}% DE LOS VOTOS"
        
        embed.description += f"\n\n---\n**{winner_text}**"

    return embed


# --- El Botón de Voto (Hijo) ---
class PollButton(discord.ui.Button):
    def __init__(self, label: str, option_id: int):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"poll_option:{option_id}"
        )
        self.option_id = option_id

    async def callback(self, interaction: discord.Interaction):
        view: PollView = self.view
        db: "PollDBManagerV5" = view.db_manager
        
        message_id = interaction.message.id
        user_id = interaction.user.id
        
        poll_data = db.get_poll_data(message_id)
        if not poll_data or not poll_data.get('is_active', False):
            await interaction.response.send_message("Esta votación ya no está activa.", ephemeral=True)
            return

        limite_votos = poll_data.get('limite_votos', 1) 
        user_votes: List[int] = db.get_user_votes_for_poll(message_id, user_id)
        
        if self.option_id in user_votes:
            db.remove_vote(message_id, user_id, self.option_id)
        
        elif len(user_votes) < limite_votos: 
            db.add_vote(message_id, user_id, self.option_id)
        
        else:
            await interaction.response.send_message(
                f"Límite de {limite_votos} voto(s) alcanzado. Quita otro voto primero.",
                ephemeral=True
            )
            return

        updated_poll_data = db.get_poll_data(message_id)

        author = None
        if interaction.message.embeds and interaction.message.embeds[0].footer:
            footer_text = interaction.message.embeds[0].footer.text
            footer_icon_url = interaction.message.embeds[0].footer.icon_url

            if footer_text.startswith("Votación creada por "):
                class FakeAuthor:
                    display_name = footer_text.replace("Votación creada por ", "")
                    display_avatar = footer_icon_url

                author = FakeAuthor()

        new_public_embed = create_poll_embed(updated_poll_data, author=author)

        await interaction.response.defer(ephemeral=True)
        await interaction.message.edit(embed=new_public_embed, view=view)

        # --- Respuesta privada de confirmación ---
        user_votes_final: List[int] = db.get_user_votes_for_poll(message_id, user_id)
        
        private_embed = discord.Embed(title="🗳️ Votación Actualizada", color=discord.Color.green())
        private_embed.description = f"Tus votos para \"{poll_data['title']}\":\n\n"
        
        voted_options_labels = []
        if poll_data.get('options'):
            for option in poll_data['options']:
                if option['option_id'] in user_votes_final:
                    private_embed.description += f"✅ {option['label']}\n"
                    voted_options_labels.append(option['label'])

        if not voted_options_labels:
            private_embed.description += "*(No has votado por ninguna opción)*\n"
            
        votos_restantes = limite_votos - len(voted_options_labels)
        private_embed.set_footer(text=f"Te quedan {votos_restantes} voto(s) disponible(s).")

        # Extra privado: mostrar marcador con números + % y quién va ganando
        try:
            opts2 = (updated_poll_data or {}).get("options", []) or []
            total2 = sum(int(o.get("vote_count", 0) or 0) for o in opts2)
            if total2 > 0:
                max2 = max(int(o.get("vote_count", 0) or 0) for o in opts2) if opts2 else 0
                winners2 = [str(o.get("label", "N/A")) for o in opts2 if int(o.get("vote_count", 0) or 0) == max2 and max2 > 0]
                if winners2:
                    pct2 = (max2 / total2) * 100
                    if len(winners2) > 1:
                        private_embed.add_field(name="Marcador (privado)", value=f"Empate: {', '.join(winners2)} ({pct2:.1f}% c/u) · Total votos: {total2}", inline=False)
                    else:
                        private_embed.add_field(name="Marcador (privado)", value=f"Va ganando: {winners2[0]} ({pct2:.1f}%) · Total votos: {total2}", inline=False)
        except Exception:
            pass

        await interaction.followup.send(embed=private_embed, ephemeral=True)


# --- La Vista Persistente (Madre) ---
class PollView(discord.ui.View):
    def __init__(self, poll_options: Optional[List[Dict[str, Any]]], db_manager: "PollDBManagerV5"):
        super().__init__(timeout=None)
        self.db_manager = db_manager 
        
        if poll_options:
            for option in poll_options:
                self.add_item(PollButton(
                    label=option['label'],
                    option_id=option['option_id']
                ))