"""
Cog pour la gestion des reaction roles (auto-attribution de rôles).
"""
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from config import Colors, Emojis
from utils.database import db


class ReactionRoleView(discord.ui.View):
    """Vue persistante pour les reaction roles avec boutons."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot


class ReactionRoles(commands.Cog):
    """Système de reaction roles pour l'auto-attribution de rôles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Gère l'ajout de réactions pour attribuer des rôles."""
        if payload.member.bot:
            return

        emoji = str(payload.emoji)
        reaction_role = await db.get_reaction_role(payload.message_id, emoji)

        if not reaction_role:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        role = guild.get_role(reaction_role['role_id'])
        if not role:
            return

        try:
            await payload.member.add_roles(role, reason="Reaction Role")
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Gère le retrait de réactions pour retirer des rôles."""
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        emoji = str(payload.emoji)
        reaction_role = await db.get_reaction_role(payload.message_id, emoji)

        if not reaction_role:
            return

        role = guild.get_role(reaction_role['role_id'])
        if not role:
            return

        try:
            await member.remove_roles(role, reason="Reaction Role")
        except discord.Forbidden:
            pass

    @commands.hybrid_group(name="reactionrole", aliases=["rr"])
    @commands.has_permissions(administrator=True)
    async def reactionrole(self, ctx: commands.Context):
        """Commandes pour gérer les reaction roles."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @reactionrole.command(name="add")
    @app_commands.describe(
        message_id="L'ID du message",
        emoji="L'emoji à utiliser",
        role="Le rôle à attribuer"
    )
    async def rr_add(self, ctx: commands.Context, message_id: str, emoji: str, role: discord.Role):
        """Ajoute un reaction role à un message existant."""
        try:
            msg_id = int(message_id)
        except ValueError:
            return await ctx.send(f"{Emojis.ERROR} ID de message invalide.")

        # Vérifier si le message existe
        message = None
        for channel in ctx.guild.text_channels:
            try:
                message = await channel.fetch_message(msg_id)
                break
            except discord.NotFound:
                continue
            except discord.Forbidden:
                continue

        if not message:
            return await ctx.send(f"{Emojis.ERROR} Message introuvable.")

        # Vérifier si le rôle est attribuable
        if role >= ctx.guild.me.top_role:
            return await ctx.send(f"{Emojis.ERROR} Ce rôle est trop haut dans la hiérarchie.")

        # Ajouter la réaction au message
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            return await ctx.send(f"{Emojis.ERROR} Impossible d'ajouter cette réaction.")

        # Sauvegarder en base
        await db.add_reaction_role(ctx.guild.id, msg_id, message.channel.id, emoji, role.id)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Reaction Role Ajouté",
            description=f"Réagissez avec {emoji} sur [ce message]({message.jump_url}) pour obtenir le rôle {role.mention}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @reactionrole.command(name="remove")
    @app_commands.describe(message_id="L'ID du message", emoji="L'emoji à retirer")
    async def rr_remove(self, ctx: commands.Context, message_id: str, emoji: str):
        """Retire un reaction role d'un message."""
        try:
            msg_id = int(message_id)
        except ValueError:
            return await ctx.send(f"{Emojis.ERROR} ID de message invalide.")

        await db.remove_reaction_role(msg_id, emoji)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Reaction Role Retiré",
            description=f"Le reaction role avec {emoji} a été retiré.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @reactionrole.command(name="list")
    async def rr_list(self, ctx: commands.Context):
        """Affiche tous les reaction roles du serveur."""
        reaction_roles = await db.get_all_reaction_roles(ctx.guild.id)

        if not reaction_roles:
            return await ctx.send(f"{Emojis.INFO} Aucun reaction role configuré.")

        embed = discord.Embed(
            title=f"{Emojis.INFO} Reaction Roles",
            color=Colors.PRIMARY
        )

        for rr in reaction_roles[:25]:  # Max 25 fields
            role = ctx.guild.get_role(rr['role_id'])
            channel = ctx.guild.get_channel(rr['channel_id'])
            role_name = role.name if role else "Rôle supprimé"
            channel_name = channel.mention if channel else "Channel inconnu"
            embed.add_field(
                name=f"{rr['emoji']} → {role_name}",
                value=f"Channel: {channel_name}\nMessage ID: `{rr['message_id']}`",
                inline=True
            )

        await ctx.send(embed=embed)

    @reactionrole.command(name="create")
    @app_commands.describe(titre="Titre de l'embed", description="Description de l'embed")
    async def rr_create(self, ctx: commands.Context, titre: str, *, description: str = None):
        """Crée un nouveau message pour les reaction roles."""
        embed = discord.Embed(
            title=titre,
            description=description or "Réagissez pour obtenir des rôles!",
            color=Colors.PRIMARY
        )
        embed.set_footer(text="Utilisez !reactionrole add pour ajouter des rôles")

        message = await ctx.send(embed=embed)

        info_embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Message Créé",
            description=f"ID du message: `{message.id}`\n\nUtilisez `!reactionrole add {message.id} [emoji] [role]` pour ajouter des reaction roles.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=info_embed, delete_after=30)

    @commands.hybrid_command(name="rolemenu")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(titre="Titre du menu")
    async def rolemenu(self, ctx: commands.Context, *, titre: str = "Menu de Rôles"):
        """Crée un menu interactif de rôles avec des boutons."""

        class RoleMenuModal(discord.ui.Modal, title="Configurer le Menu de Rôles"):
            roles_input = discord.ui.TextInput(
                label="Rôles (emoji:@role par ligne)",
                style=discord.TextStyle.paragraph,
                placeholder="🎮:@Gamer\n🎵:@Music\n🎨:@Artist",
                required=True
            )

            async def on_submit(modal_self, interaction: discord.Interaction):
                lines = modal_self.roles_input.value.strip().split('\n')
                roles_config = []

                for line in lines:
                    if ':' not in line:
                        continue
                    parts = line.split(':', 1)
                    if len(parts) != 2:
                        continue
                    emoji = parts[0].strip()
                    role_mention = parts[1].strip()

                    # Extraire l'ID du rôle
                    role_id = None
                    if role_mention.startswith('<@&') and role_mention.endswith('>'):
                        try:
                            role_id = int(role_mention[3:-1])
                        except ValueError:
                            continue

                    if role_id:
                        role = ctx.guild.get_role(role_id)
                        if role:
                            roles_config.append((emoji, role))

                if not roles_config:
                    await interaction.response.send_message(
                        f"{Emojis.ERROR} Aucun rôle valide trouvé.",
                        ephemeral=True
                    )
                    return

                # Créer l'embed
                embed = discord.Embed(
                    title=titre,
                    description="\n".join(f"{emoji} - {role.mention}" for emoji, role in roles_config),
                    color=Colors.PRIMARY
                )
                embed.set_footer(text="Réagissez pour obtenir un rôle!")

                message = await ctx.channel.send(embed=embed)

                # Ajouter les réactions et sauvegarder
                for emoji, role in roles_config:
                    try:
                        await message.add_reaction(emoji)
                        await db.add_reaction_role(ctx.guild.id, message.id, ctx.channel.id, emoji, role.id)
                    except discord.HTTPException:
                        continue

                await interaction.response.send_message(
                    f"{Emojis.SUCCESS} Menu de rôles créé avec succès!",
                    ephemeral=True
                )

        await ctx.interaction.response.send_modal(RoleMenuModal())


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
