# cogs/votacion/poll_view.py
import discord
from discord.ext import commands
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .db_manager import PollDBManagerV4

# --- El Embed (Helper) ---
def create_poll_embed(
    poll_data: Dict[str, Any],
    author: Optional[discord.User] = None
) -> discord.Embed:
    """Genera un embed de Discord a partir de los datos de la votación."""
    
    title = poll_data.get('title', 'Votación')
    # --- ¡¡¡AQUÍ ESTÁ EL ARREGLO!!! ---
    # Si get('description') devuelve None, usamos el texto por defecto.
    description = poll_data.get('description') or "Vota usando los botones."
    
    is_active = poll_data.get('is_active', True)
    
    if is_active:
        embed = discord.Embed(
            title=f"🗳️ Votación: {title}",
            description=description, # Ahora 'description' NUNCA es None
            color=discord.Color.blue()
        )
    else:
        # Votación cerrada
        embed = discord.Embed(
            title=f"VOTACIÓN CERRADA: {title}",
            description=description, # Ahora 'description' NUNCA es None
            color=discord.Color.red()
        )

    if poll_data.get('link_url'):
        embed.description += f"\n\n[Referencia]({poll_data['link_url']})"
    
    if poll_data.get('image_url'):
        embed.set_image(url=poll_data['image_url'])

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
        
        # Ahora esto es seguro porque 'embed.description' es un string
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
        db: "PollDBManagerV4" = view.db_manager
        
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
            await interaction.response.send_message(f"Has quitado tu voto para '{self.label}'.", ephemeral=True)
        
        elif len(user_votes) < limite_votos: 
            db.add_vote(message_id, user_id, self.option_id)
            await interaction.response.send_message(f"Has votado por '{self.label}'.", ephemeral=True)
        
        else:
            await interaction.response.send_message(
                f"Límite de {limite_votos} voto(s) alcanzado. Quita otro voto primero.",
                ephemeral=True
            )
            return

        user_votes = db.get_user_votes_for_poll(message_id, user_id)
        updated_poll_data = db.get_poll_data(message_id)
        
        for item in view.children:
            if isinstance(item, PollButton):
                item.style = discord.ButtonStyle.green if item.option_id in user_votes else discord.ButtonStyle.secondary
        
        author = None
        if interaction.message.embeds and interaction.message.embeds[0].footer:
            footer_text = interaction.message.embeds[0].footer.text
            footer_icon_url = interaction.message.embeds[0].footer.icon_url
            if footer_text.startswith("Votación creada por "):
                class FakeAuthor:
                    display_name = footer_text.replace("Votación creada por ", "")
                    display_avatar = footer_icon_url
                author = FakeAuthor()
        
        new_embed = create_poll_embed(updated_poll_data, author=author)
        await interaction.message.edit(embed=new_embed, view=view)


# --- La Vista Persistente (Madre) ---
class PollView(discord.ui.View):
    def __init__(self, poll_options: Optional[List[Dict[str, Any]]], db_manager: "PollDBManagerV4"):
        super().__init__(timeout=None)
        self.db_manager = db_manager 
        
        if poll_options:
            for option in poll_options:
                self.add_item(PollButton(
                    label=option['label'],
                    option_id=option['option_id']
                ))