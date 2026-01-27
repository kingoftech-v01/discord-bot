"""
Cog pour le système de tickets de support.
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
    """Vue persistante pour les tickets."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Ouvrir un Ticket", style=discord.ButtonStyle.primary, custom_id="ticket:open", emoji="")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ouvre un nouveau ticket."""
        # Vérifier si l'utilisateur a déjà un ticket ouvert
        existing = await self.check_existing_ticket(interaction.user.id, interaction.guild.id)
        if existing:
            return await interaction.response.send_message(
                f"{Emojis.ERROR} Vous avez déjà un ticket ouvert!",
                ephemeral=True
            )

        # Modal pour le sujet
        modal = TicketModal(self.bot)
        await interaction.response.send_modal(modal)

    async def check_existing_ticket(self, user_id: int, guild_id: int) -> bool:
        """Vérifie si l'utilisateur a déjà un ticket ouvert."""
        import aiosqlite
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute(
                "SELECT id FROM tickets WHERE user_id = ? AND guild_id = ? AND status = 'open'",
                (user_id, guild_id)
            ) as cursor:
                return await cursor.fetchone() is not None


class TicketModal(discord.ui.Modal, title="Ouvrir un Ticket"):
    """Modal pour créer un ticket."""

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
        guild = interaction.guild

        # Trouver ou créer la catégorie tickets
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            try:
                category = await guild.create_category(
                    "Tickets",
                    reason="Catégorie pour les tickets de support"
                )
            except discord.Forbidden:
                return await interaction.response.send_message(
                    f"{Emojis.ERROR} Je n'ai pas la permission de créer des catégories.",
                    ephemeral=True
                )

        # Créer le channel du ticket
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        # Ajouter les rôles staff
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

        # Sauvegarder en base
        ticket_id = await db.create_ticket(guild.id, channel.id, interaction.user.id, self.sujet.value)

        # Créer l'embed du ticket
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

        # Vue de contrôle du ticket
        view = TicketControlView(self.bot)
        await channel.send(
            content=f"{interaction.user.mention} - Le support vous répondra bientôt!",
            embed=embed,
            view=view
        )

        await interaction.response.send_message(
            f"{Emojis.SUCCESS} Votre ticket a été créé: {channel.mention}",
            ephemeral=True
        )


class TicketControlView(discord.ui.View):
    """Vue de contrôle pour un ticket."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, custom_id="ticket:close", emoji="")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ferme le ticket."""
        ticket = await db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(
                f"{Emojis.ERROR} Ce n'est pas un ticket valide.",
                ephemeral=True
            )

        # Vérifier les permissions
        if interaction.user.id != ticket['user_id'] and not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message(
                f"{Emojis.ERROR} Vous n'avez pas la permission de fermer ce ticket.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"{Emojis.INFO} Fermeture du ticket dans 5 secondes...",
        )

        await asyncio.sleep(5)

        # Sauvegarder le transcript
        messages = []
        async for message in interaction.channel.history(limit=500, oldest_first=True):
            messages.append(f"[{message.created_at.strftime('%H:%M')}] {message.author}: {message.content}")

        transcript = "\n".join(messages)

        # Fermer le ticket
        await db.close_ticket(ticket['id'])

        # Supprimer le channel
        try:
            await interaction.channel.delete(reason="Ticket fermé")
        except discord.Forbidden:
            await interaction.channel.send(f"{Emojis.ERROR} Je n'ai pas pu supprimer le channel.")

    @discord.ui.button(label="Ajouter un membre", style=discord.ButtonStyle.secondary, custom_id="ticket:add", emoji="")
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ajoute un membre au ticket."""
        modal = AddMemberModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Transférer", style=discord.ButtonStyle.secondary, custom_id="ticket:transfer", emoji="")
    async def transfer_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Transfère le ticket à un autre staff."""
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message(
                f"{Emojis.ERROR} Vous n'avez pas la permission de transférer ce ticket.",
                ephemeral=True
            )

        modal = TransferModal()
        await interaction.response.send_modal(modal)


class AddMemberModal(discord.ui.Modal, title="Ajouter un Membre"):
    """Modal pour ajouter un membre au ticket."""

    member_id = discord.ui.TextInput(
        label="ID du membre",
        placeholder="Entrez l'ID du membre à ajouter...",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            member = interaction.guild.get_member(int(self.member_id.value))
            if not member:
                return await interaction.response.send_message(
                    f"{Emojis.ERROR} Membre introuvable.",
                    ephemeral=True
                )

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
    """Modal pour transférer un ticket."""

    staff_id = discord.ui.TextInput(
        label="ID du staff",
        placeholder="Entrez l'ID du membre du staff...",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            staff = interaction.guild.get_member(int(self.staff_id.value))
            if not staff:
                return await interaction.response.send_message(
                    f"{Emojis.ERROR} Staff introuvable.",
                    ephemeral=True
                )

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
