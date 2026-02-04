"""
Reaction roles cog for the Discord bot.

Enables server administrators to set up self-assignable roles via emoji
reactions on designated messages. When a member reacts with a configured
emoji, the corresponding role is automatically granted; when they remove
the reaction, the role is revoked.

The cog provides commands to:
- Add/remove reaction-role mappings on existing messages.
- List all configured reaction roles for the server.
- Create new embed messages specifically for reaction-role menus.
- Build interactive role menus via a Discord modal (``rolemenu``).

Reaction-role mappings are persisted in the database so they survive bot
restarts. The cog listens for raw reaction events (``on_raw_reaction_add``
and ``on_raw_reaction_remove``) to handle reactions on any message, even
those not in the bot's message cache.
"""
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from config import Colors, Emojis
from utils.database import db


class ReactionRoleView(discord.ui.View):
    """Persistent UI view for button-based reaction roles.

    This is a placeholder view with no timeout, intended for future
    button-based role assignment. Currently unused but available for
    extension.

    Attributes:
        bot: The bot instance this view is associated with.
    """

    def __init__(self, bot: commands.Bot):
        """Initialize the persistent view.

        Args:
            bot: The bot instance for accessing guild and role data.
        """
        super().__init__(timeout=None)
        self.bot = bot


class ReactionRoles(commands.Cog):
    """Cog for managing emoji-based self-assignable roles.

    Listens for raw reaction add/remove events and maps them to role
    grant/revoke operations using the database-stored reaction-role
    configuration. Provides administrator commands for managing mappings.

    Attributes:
        bot: The bot instance this cog is attached to.
    """

    def __init__(self, bot: commands.Bot):
        """Initialize the ReactionRoles cog.

        Args:
            bot: The bot instance to bind this cog to.
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Grant a role when a user adds a reaction to a configured message.

        Uses raw reaction events so it works even for messages not in the
        bot's internal cache. Looks up the emoji/message combination in the
        database and, if a mapping exists, adds the corresponding role to
        the reacting member.

        Args:
            payload: The raw reaction event data containing message ID,
                emoji, guild ID, and the member who reacted.
        """
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
            pass  # Bot lacks permission to assign this role

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Revoke a role when a user removes their reaction from a configured message.

        Since ``on_raw_reaction_remove`` does not provide a ``member``
        attribute, the member is fetched from the guild cache using the
        user ID from the payload.

        Args:
            payload: The raw reaction event data containing message ID,
                emoji, guild ID, and the user ID of the person who
                removed their reaction.
        """
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        # Raw reaction remove events don't include the member object
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
            pass  # Bot lacks permission to remove this role

    @commands.hybrid_group(name="reactionrole", aliases=["rr"])
    @commands.has_permissions(administrator=True)
    async def reactionrole(self, ctx: commands.Context):
        """Command group for managing reaction roles (admin only).

        When invoked without a subcommand, shows the group's help page.

        Args:
            ctx: The invocation context.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @reactionrole.command(name="add")
    @app_commands.describe(
        message_id="L'ID du message",
        emoji="L'emoji à utiliser",
        role="Le rôle à attribuer"
    )
    async def rr_add(self, ctx: commands.Context, message_id: str, emoji: str, role: discord.Role):
        """Add a reaction-role mapping to an existing message.

        Searches all text channels in the guild to locate the target message,
        validates that the role is below the bot's highest role in the
        hierarchy (so it can be assigned), adds the emoji reaction to the
        message, and persists the mapping in the database.

        Args:
            ctx: The invocation context.
            message_id: The snowflake ID of the target message (as a string).
            emoji: The emoji to react with (Unicode or custom Discord emoji).
            role: The role to assign when users react with the emoji.
        """
        try:
            msg_id = int(message_id)
        except ValueError:
            return await ctx.send(f"{Emojis.ERROR} ID de message invalide.")

        # Search all text channels for the target message
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

        # Ensure the role is below the bot's highest role in the hierarchy
        if role >= ctx.guild.me.top_role:
            return await ctx.send(f"{Emojis.ERROR} Ce rôle est trop haut dans la hiérarchie.")

        # Add the emoji reaction to the target message
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            return await ctx.send(f"{Emojis.ERROR} Impossible d'ajouter cette réaction.")

        # Persist the mapping in the database
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
        """Remove a reaction-role mapping from a message.

        Deletes the mapping from the database. Note: does not remove the
        existing reaction from the message itself.

        Args:
            ctx: The invocation context.
            message_id: The snowflake ID of the target message (as a string).
            emoji: The emoji whose mapping should be removed.
        """
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
        """List all reaction-role mappings configured for this server.

        Displays up to 25 mappings (Discord embed field limit), each showing
        the emoji, the role it maps to, the channel, and the message ID.

        Args:
            ctx: The invocation context.
        """
        reaction_roles = await db.get_all_reaction_roles(ctx.guild.id)

        if not reaction_roles:
            return await ctx.send(f"{Emojis.INFO} Aucun reaction role configuré.")

        embed = discord.Embed(
            title=f"{Emojis.INFO} Reaction Roles",
            color=Colors.PRIMARY
        )

        for rr in reaction_roles[:25]:  # Discord embeds support max 25 fields
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
        """Create a new embed message to be used as a reaction-role menu.

        Posts an embed with the given title and description, then sends a
        temporary follow-up message with the new message's ID and
        instructions for adding reaction-role mappings to it.

        Args:
            ctx: The invocation context.
            titre: The title for the reaction-role embed.
            description: Optional description text. Defaults to a generic
                instruction to react for roles.
        """
        embed = discord.Embed(
            title=titre,
            description=description or "Réagissez pour obtenir des rôles!",
            color=Colors.PRIMARY
        )
        embed.set_footer(text="Utilisez !reactionrole add pour ajouter des rôles")

        message = await ctx.send(embed=embed)

        # Send a temporary instruction message that auto-deletes after 30 seconds
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
        """Create an interactive role menu via a Discord modal (admin only, slash-only).

        Opens a modal dialog where the administrator enters emoji-to-role
        mappings (one per line in ``emoji:@role`` format). On submission,
        the bot creates a reaction-role embed, adds all the emoji reactions,
        and persists the mappings in the database.

        This command only works as a slash command because it requires
        ``ctx.interaction`` to present the modal.

        Args:
            ctx: The invocation context (must be a slash command interaction).
            titre: The title for the role menu embed. Defaults to
                ``"Menu de Roles"``.
        """

        class RoleMenuModal(discord.ui.Modal, title="Configurer le Menu de Rôles"):
            """Modal for configuring emoji-to-role mappings.

            The user enters one mapping per line in the format
            ``emoji:@role``. The modal parses each line, resolves the
            role mention to a guild role, and collects valid pairs.
            """

            roles_input = discord.ui.TextInput(
                label="Rôles (emoji:@role par ligne)",
                style=discord.TextStyle.paragraph,
                placeholder="🎮:@Gamer\n🎵:@Music\n🎨:@Artist",
                required=True
            )

            async def on_submit(modal_self, interaction: discord.Interaction):
                """Process the modal submission and create the role menu.

                Args:
                    interaction: The modal submission interaction.
                """
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

                    # Extract the role ID from the mention format <@&ID>
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

                # Build the role menu embed with emoji-role pairs
                embed = discord.Embed(
                    title=titre,
                    description="\n".join(f"{emoji} - {role.mention}" for emoji, role in roles_config),
                    color=Colors.PRIMARY
                )
                embed.set_footer(text="Réagissez pour obtenir un rôle!")

                message = await ctx.channel.send(embed=embed)

                # Add reactions and persist each mapping to the database
                for emoji, role in roles_config:
                    try:
                        await message.add_reaction(emoji)
                        await db.add_reaction_role(ctx.guild.id, message.id, ctx.channel.id, emoji, role.id)
                    except discord.HTTPException:
                        continue  # Skip emojis the bot cannot use

                await interaction.response.send_message(
                    f"{Emojis.SUCCESS} Menu de rôles créé avec succès!",
                    ephemeral=True
                )

        await ctx.interaction.response.send_modal(RoleMenuModal())


async def setup(bot: commands.Bot):
    """Load the ReactionRoles cog into the bot.

    Args:
        bot: The bot instance to register the cog with.
    """
    await bot.add_cog(ReactionRoles(bot))
