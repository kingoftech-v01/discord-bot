"""
Support ticket system cog with persistent UI views and full ticket lifecycle management.

This module implements a complete support ticket system for Discord servers with
the following capabilities:

- **Persistent ticket panel**: A button-based UI (``TicketView``) that survives
  bot restarts, allowing users to open tickets at any time by clicking a button.
- **Ticket creation modal**: A modal dialog (``TicketModal``) that collects the
  ticket subject and optional description from the user.
- **Ticket channels**: Each ticket creates a private text channel under a
  "Tickets" category with scoped permissions (visible only to the ticket creator,
  staff roles, and the bot).
- **Ticket controls**: An in-channel control panel (``TicketControlView``) with
  buttons to close the ticket, add a member, or transfer to another staff member.
- **Transcript generation**: When a ticket is closed, the message history is
  captured as a text transcript before the channel is deleted.
- **Management commands**: Staff commands for setup, manual close, add/remove
  members, and rename tickets.

All ticket metadata (creator, channel, status) is persisted in the SQLite
database via the ``utils.database`` module.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional
import asyncio

from config import Colors, Emojis
from utils.database import db


class TicketView(discord.ui.View):
    """Persistent view containing the "Open a Ticket" button for the ticket panel.

    This view is registered with ``timeout=None`` so it persists across bot
    restarts. It is attached to the ticket panel embed sent by the ``ticket setup``
    command. When a user clicks the button, it checks for existing open tickets
    and presents the ticket creation modal.

    Attributes:
        bot: The Discord bot instance (needed to pass to modals).
    """

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Ouvrir un Ticket", style=discord.ButtonStyle.primary, custom_id="ticket:open", emoji="")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle the "Open a Ticket" button click.

        Checks if the user already has an open ticket in this guild. If so,
        sends an ephemeral error. Otherwise, presents the TicketModal for
        the user to fill in the ticket subject and description.

        Args:
            interaction: The button click interaction.
            button: The button UI element that was clicked.
        """
        # Prevent users from opening multiple tickets simultaneously
        existing = await self.check_existing_ticket(interaction.user.id, interaction.guild.id)
        if existing:
            return await interaction.response.send_message(
                f"{Emojis.ERROR} Vous avez déjà un ticket ouvert!",
                ephemeral=True
            )

        # Present the ticket creation modal
        modal = TicketModal(self.bot)
        await interaction.response.send_modal(modal)

    async def check_existing_ticket(self, user_id: int, guild_id: int) -> bool:
        """Check whether a user already has an open ticket in the guild.

        Queries the database directly for any ticket with status 'open'
        belonging to this user in this guild.

        Args:
            user_id: The Discord user ID to check.
            guild_id: The guild ID to check within.

        Returns:
            True if the user has at least one open ticket, False otherwise.
        """
        import aiosqlite
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute(
                "SELECT id FROM tickets WHERE user_id = ? AND guild_id = ? AND status = 'open'",
                (user_id, guild_id)
            ) as cursor:
                return await cursor.fetchone() is not None


class TicketModal(discord.ui.Modal, title="Ouvrir un Ticket"):
    """Modal dialog for collecting ticket details from the user.

    Presents two text input fields: a required short subject line and an
    optional longer description. On submission, creates a private ticket
    channel with appropriate permissions and sends the initial ticket embed.

    Attributes:
        bot: The Discord bot instance (passed to the TicketControlView).
        sujet: Text input field for the ticket subject (max 100 chars, required).
        description: Text input field for additional details (max 1000 chars, optional).
    """

    sujet = discord.ui.TextInput(
        label="Sujet du ticket",
        placeholder="Décrivez brièvement votre problème...",
        style=discord.TextStyle.short,
        required=True,
        max_length=100
    )

    description = discord.ui.TextInput(
        label="Description",
        placeholder="Donnez plus de détails sur votre demande...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission: create the ticket channel and initial message.

        This method performs the following steps:
        1. Finds or creates a "Tickets" category in the guild.
        2. Sets up permission overwrites: hidden from @everyone, visible to
           the ticket creator, the bot, and any roles with manage_messages
           or administrator permissions (staff roles).
        3. Creates a private text channel under the Tickets category.
        4. Saves the ticket record in the database.
        5. Sends the initial ticket embed with control buttons (close, add
           member, transfer).
        6. Responds to the user with an ephemeral confirmation linking to
           the new ticket channel.

        Args:
            interaction: The modal submission interaction.
        """
        guild = interaction.guild

        # Find existing "Tickets" category or create one
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            try:
                category = await guild.create_category(
                    "Tickets",
                    reason="Auto-created category for support tickets"
                )
            except discord.Forbidden:
                return await interaction.response.send_message(
                    f"{Emojis.ERROR} Je n'ai pas la permission de créer des catégories.",
                    ephemeral=True
                )

        # Build permission overwrites for the ticket channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        # Grant access to all staff roles (those with manage_messages or admin)
        for role in guild.roles:
            if role.permissions.manage_messages or role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            channel = await guild.create_text_channel(
                f"ticket-{interaction.user.name}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket de {interaction.user.name} | Sujet: {self.sujet.value}",
                reason=f"Ticket ouvert par {interaction.user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                f"{Emojis.ERROR} Je n'ai pas la permission de créer des channels.",
                ephemeral=True
            )

        # Persist the ticket record in the database
        ticket_id = await db.create_ticket(guild.id, channel.id, interaction.user.id, self.sujet.value)

        # Build the initial ticket information embed
        embed = discord.Embed(
            title=f"Ticket #{ticket_id}",
            description=f"**Sujet:** {self.sujet.value}",
            color=Colors.PRIMARY,
            timestamp=datetime.now()
        )
        embed.add_field(name="Créé par", value=interaction.user.mention, inline=True)
        embed.add_field(name="Statut", value="Ouvert", inline=True)

        if self.description.value:
            embed.add_field(name="Description", value=self.description.value, inline=False)

        embed.set_footer(text="Utilisez les boutons ci-dessous pour gérer ce ticket")

        # Send the ticket embed with control buttons (close, add member, transfer)
        view = TicketControlView(self.bot)
        await channel.send(
            content=f"{interaction.user.mention} - Le support vous répondra bientôt!",
            embed=embed,
            view=view
        )

        # Respond to the user with an ephemeral message linking to the new channel
        await interaction.response.send_message(
            f"{Emojis.SUCCESS} Votre ticket a été créé: {channel.mention}",
            ephemeral=True
        )


class TicketControlView(discord.ui.View):
    """Persistent view with control buttons displayed inside a ticket channel.

    Provides three buttons for managing an active ticket:
    - **Close**: Generates a transcript and deletes the channel.
    - **Add Member**: Opens a modal to add a user by ID.
    - **Transfer**: Opens a modal to transfer the ticket to another staff member.

    This view uses ``timeout=None`` for persistence across bot restarts and
    uses fixed ``custom_id`` values so Discord can route button interactions
    back to the correct handler after a restart.

    Attributes:
        bot: The Discord bot instance.
    """

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, custom_id="ticket:close", emoji="")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the ticket: generate a transcript, update the database, and delete the channel.

        Only the ticket creator or users with ``manage_messages`` permission
        can close a ticket. A 5-second countdown is displayed before the
        channel is deleted. Up to 500 messages are captured for the transcript.

        Args:
            interaction: The button click interaction.
            button: The button UI element that was clicked.
        """
        ticket = await db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(
                f"{Emojis.ERROR} Ce n'est pas un ticket valide.",
                ephemeral=True
            )

        # Only the ticket creator or staff with manage_messages can close
        if interaction.user.id != ticket['user_id'] and not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message(
                f"{Emojis.ERROR} Vous n'avez pas la permission de fermer ce ticket.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"{Emojis.INFO} Fermeture du ticket dans 5 secondes...",
        )

        # Brief delay before deletion to allow users to see the closing message
        await asyncio.sleep(5)

        # Generate a text transcript from the channel's message history (up to 500 messages)
        messages = []
        async for message in interaction.channel.history(limit=500, oldest_first=True):
            messages.append(f"[{message.created_at.strftime('%H:%M')}] {message.author}: {message.content}")

        transcript = "\n".join(messages)

        # Mark the ticket as closed in the database
        await db.close_ticket(ticket['id'])

        # Delete the ticket channel
        try:
            await interaction.channel.delete(reason="Ticket fermé")
        except discord.Forbidden:
            await interaction.channel.send(f"{Emojis.ERROR} Je n'ai pas pu supprimer le channel.")

    @discord.ui.button(label="Ajouter un membre", style=discord.ButtonStyle.secondary, custom_id="ticket:add", emoji="")
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open a modal to add a member to this ticket by their user ID.

        Grants the specified member read and send permissions in the ticket channel.

        Args:
            interaction: The button click interaction.
            button: The button UI element that was clicked.
        """
        modal = AddMemberModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Transférer", style=discord.ButtonStyle.secondary, custom_id="ticket:transfer", emoji="")
    async def transfer_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open a modal to transfer this ticket to another staff member.

        Only users with ``manage_messages`` permission can transfer tickets.
        The transfer grants the target staff member read, send, and manage
        permissions in the ticket channel.

        Args:
            interaction: The button click interaction.
            button: The button UI element that was clicked.
        """
        # Only staff can transfer tickets
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message(
                f"{Emojis.ERROR} Vous n'avez pas la permission de transférer ce ticket.",
                ephemeral=True
            )

        modal = TransferModal()
        await interaction.response.send_modal(modal)


class AddMemberModal(discord.ui.Modal, title="Ajouter un Membre"):
    """Modal dialog for adding a member to a ticket channel by their user ID.

    The user enters a Discord user ID, and the modal grants that member
    read and send permissions in the current ticket channel.

    Attributes:
        member_id: Text input field for the Discord user ID to add.
    """

    member_id = discord.ui.TextInput(
        label="ID du membre",
        placeholder="Entrez l'ID du membre à ajouter...",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission: look up the member and grant channel access.

        Validates that the provided ID is a valid integer and corresponds to
        an existing guild member. If valid, grants read and send permissions
        in the ticket channel.

        Args:
            interaction: The modal submission interaction.
        """
        try:
            member = interaction.guild.get_member(int(self.member_id.value))
            if not member:
                return await interaction.response.send_message(
                    f"{Emojis.ERROR} Membre introuvable.",
                    ephemeral=True
                )

            # Grant the member access to the ticket channel
            await interaction.channel.set_permissions(
                member,
                read_messages=True,
                send_messages=True
            )

            await interaction.response.send_message(
                f"{Emojis.SUCCESS} {member.mention} a été ajouté au ticket."
            )
        except ValueError:
            await interaction.response.send_message(
                f"{Emojis.ERROR} ID invalide.",
                ephemeral=True
            )


class TransferModal(discord.ui.Modal, title="Transférer le Ticket"):
    """Modal dialog for transferring a ticket to another staff member.

    The staff member enters the target staff's Discord user ID. The target
    receives read, send, and manage_messages permissions in the ticket channel,
    and a notification embed is posted.

    Attributes:
        staff_id: Text input field for the target staff member's Discord user ID.
    """

    staff_id = discord.ui.TextInput(
        label="ID du staff",
        placeholder="Entrez l'ID du membre du staff...",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission: look up the staff member and grant elevated access.

        Validates the provided ID and grants the target staff member read, send,
        and manage_messages permissions in the ticket channel, then posts a
        transfer notification embed.

        Args:
            interaction: The modal submission interaction.
        """
        try:
            staff = interaction.guild.get_member(int(self.staff_id.value))
            if not staff:
                return await interaction.response.send_message(
                    f"{Emojis.ERROR} Staff introuvable.",
                    ephemeral=True
                )

            # Grant the staff member elevated permissions in the ticket channel
            await interaction.channel.set_permissions(
                staff,
                read_messages=True,
                send_messages=True,
                manage_messages=True
            )

            embed = discord.Embed(
                title=f"{Emojis.INFO} Ticket Transféré",
                description=f"Ce ticket a été transféré à {staff.mention}",
                color=Colors.INFO
            )
            await interaction.response.send_message(embed=embed)
        except ValueError:
            await interaction.response.send_message(
                f"{Emojis.ERROR} ID invalide.",
                ephemeral=True
            )


class Tickets(commands.Cog):
    """Système de tickets de support."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(TicketView(bot))
        bot.add_view(TicketControlView(bot))

    @commands.hybrid_group(name="ticket")
    async def ticket(self, ctx: commands.Context):
        """Commandes de gestion des tickets."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ticket.command(name="setup")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(channel="Le channel où envoyer le panel de tickets")
    async def ticket_setup(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Configure le système de tickets."""
        target_channel = channel or ctx.channel

        embed = discord.Embed(
            title="Support - Ouvrir un Ticket",
            description="Cliquez sur le bouton ci-dessous pour ouvrir un ticket de support.\n\n"
                        "**Avant d'ouvrir un ticket:**\n"
                        " Vérifiez le FAQ\n"
                        " Décrivez clairement votre problème\n"
                        " Soyez patient",
            color=Colors.PRIMARY
        )
        embed.set_footer(text="Notre équipe vous répondra dans les plus brefs délais")

        view = TicketView(self.bot)
        await target_channel.send(embed=embed, view=view)

        if channel:
            await ctx.send(f"{Emojis.SUCCESS} Panel de tickets envoyé dans {channel.mention}", ephemeral=True)

    @ticket.command(name="close")
    async def ticket_close(self, ctx: commands.Context):
        """Ferme le ticket actuel."""
        ticket = await db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.send(f"{Emojis.ERROR} Cette commande doit être utilisée dans un ticket.")

        if ctx.author.id != ticket['user_id'] and not ctx.author.guild_permissions.manage_messages:
            return await ctx.send(f"{Emojis.ERROR} Vous n'avez pas la permission de fermer ce ticket.")

        await ctx.send(f"{Emojis.INFO} Fermeture du ticket dans 5 secondes...")
        await asyncio.sleep(5)
        await db.close_ticket(ticket['id'])

        try:
            await ctx.channel.delete(reason="Ticket fermé")
        except discord.Forbidden:
            await ctx.send(f"{Emojis.ERROR} Je n'ai pas pu supprimer le channel.")

    @ticket.command(name="add")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(membre="Le membre à ajouter au ticket")
    async def ticket_add(self, ctx: commands.Context, membre: discord.Member):
        """Ajoute un membre au ticket."""
        ticket = await db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.send(f"{Emojis.ERROR} Cette commande doit être utilisée dans un ticket.")

        await ctx.channel.set_permissions(membre, read_messages=True, send_messages=True)
        await ctx.send(f"{Emojis.SUCCESS} {membre.mention} a été ajouté au ticket.")

    @ticket.command(name="remove")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(membre="Le membre à retirer du ticket")
    async def ticket_remove(self, ctx: commands.Context, membre: discord.Member):
        """Retire un membre du ticket."""
        ticket = await db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.send(f"{Emojis.ERROR} Cette commande doit être utilisée dans un ticket.")

        if membre.id == ticket['user_id']:
            return await ctx.send(f"{Emojis.ERROR} Vous ne pouvez pas retirer le créateur du ticket.")

        await ctx.channel.set_permissions(membre, overwrite=None)
        await ctx.send(f"{Emojis.SUCCESS} {membre.mention} a été retiré du ticket.")

    @ticket.command(name="rename")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(nom="Le nouveau nom du ticket")
    async def ticket_rename(self, ctx: commands.Context, *, nom: str):
        """Renomme le ticket."""
        ticket = await db.get_ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.send(f"{Emojis.ERROR} Cette commande doit être utilisée dans un ticket.")

        await ctx.channel.edit(name=f"ticket-{nom}")
        await ctx.send(f"{Emojis.SUCCESS} Ticket renommé.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
