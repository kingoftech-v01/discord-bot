"""
Advanced multi-language profanity filter with progressive punishments.

This module provides a comprehensive profanity detection and enforcement system
that supports multiple languages and applies escalating sanctions based on a
user's infraction history. Key features include:

- **Multi-language support**: Banned words can be categorized by language
  (French, English, Spanish, German, Italian, Portuguese, Arabic, Russian,
  Chinese, Japanese) or applied globally with the "all" category.
- **Progressive punishments**: Sanctions escalate as infractions accumulate:
  warn -> mute -> kick -> ban. Thresholds are fully configurable per guild.
- **DM notifications**: Optionally notifies offending users via DM with details
  about their infraction, the applied sanction, and upcoming punishment thresholds.
- **Logging**: All infractions are logged to the guild's configured log channel
  with details including the detected word (spoilered), severity, sanction, and
  the original message content.
- **Management commands**: Guild staff can add, remove, import, and list banned
  words, view infraction statistics, and configure punishment thresholds.

All banned word lists, infraction records, and configuration are persisted in
the SQLite database via the ``utils.database`` module.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from typing import Optional, List
import re
import asyncio

from config import Colors, Emojis
from utils.database import db


class ProfanityFilter(commands.Cog):
    """Discord cog for detecting banned words and applying progressive punishments.

    Scans every non-bot, non-admin message for profanity matches against a
    per-guild database of banned words. When a match is found, the system:
    1. Optionally deletes the offending message.
    2. Determines the appropriate punishment based on the user's infraction count.
    3. Applies the punishment (warn, mute, kick, or ban).
    4. Notifies the user via DM (if configured).
    5. Posts a warning in the channel (auto-deletes after 10 seconds).
    6. Logs the infraction to the moderation log channel.

    Attributes:
        bot: The Discord bot instance.
        language_names: Mapping of language codes to their display names,
            used for user-facing labels in embeds and command output.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Mapping of ISO language codes to human-readable display names
        self.language_names = {
            "all": "Toutes",
            "fr": "Français",
            "en": "Anglais",
            "es": "Espagnol",
            "de": "Allemand",
            "it": "Italien",
            "pt": "Portugais",
            "ar": "Arabe",
            "ru": "Russe",
            "zh": "Chinois",
            "ja": "Japonais"
        }

    async def log_infraction(self, guild: discord.Guild, embed: discord.Embed):
        """Send an infraction log embed to the guild's configured log channel.

        Silently does nothing if no log channel is configured, if the channel
        no longer exists, or if the bot lacks permission to send messages there.

        Args:
            guild: The Discord guild where the infraction occurred.
            embed: The embed containing infraction details to log.
        """
        config = await db.get_guild_config(guild.id)
        log_channel_id = config.get('log_channel_id')
        if log_channel_id:
            channel = guild.get_channel(log_channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    async def apply_punishment(self, member: discord.Member, punishment: str,
                               guild: discord.Guild, reason: str) -> bool:
        """Apply the determined punishment to a guild member.

        Executes the appropriate Discord action based on the punishment type.
        For "warn", no Discord API action is taken (the warning is only recorded
        in the database). For "mute", the configured mute duration from the
        guild's profanity config is used.

        Args:
            member: The guild member to punish.
            punishment: The type of punishment to apply. One of:
                ``"warn"``, ``"mute"``, ``"kick"``, ``"ban"``.
            guild: The Discord guild where the infraction occurred.
            reason: The reason string for the audit log.

        Returns:
            True if the punishment was successfully applied, False if the bot
            lacked permissions or an error occurred.
        """
        try:
            if punishment == "warn":
                # Warning only -- no Discord API action needed, just database record
                return True

            elif punishment == "mute":
                # Apply a timed mute using the guild's configured mute duration
                config = await db.get_profanity_config(guild.id)
                duration = config.get('mute_duration', 3600)  # Default: 1 hour
                until = datetime.now() + timedelta(seconds=duration)
                await member.timeout(until, reason=reason)
                return True

            elif punishment == "kick":
                await member.kick(reason=reason)
                return True

            elif punishment == "ban":
                await member.ban(reason=reason)
                return True

        except discord.Forbidden:
            return False
        except Exception:
            return False

        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Scan incoming messages for banned words and enforce punishments.

        This is the main detection pipeline. For each eligible message, it:
        1. Checks the message content against the guild's banned word database.
        2. If a match is found, deletes the message (if configured).
        3. Determines the punishment level based on the user's infraction history.
        4. Records the infraction in the database.
        5. Applies the punishment (warn/mute/kick/ban).
        6. Optionally DMs the user with infraction details and upcoming thresholds.
        7. Posts a temporary warning in the channel (auto-deletes after 10s).
        8. Logs the full infraction to the moderation log channel.

        Bots, DMs, and administrators are always exempt from filtering.

        Args:
            message: The incoming Discord message to scan.
        """
        # Skip bot messages and DMs (filter only applies in guilds)
        if message.author.bot or not message.guild:
            return

        # Administrators are exempt from the profanity filter
        if message.author.guild_permissions.administrator:
            return

        # Check if the profanity filter is enabled for this guild
        config = await db.get_profanity_config(message.guild.id)
        if not config.get('enabled', True):
            return

        # Scan the message content against the guild's banned word database
        detected = await db.check_message_for_profanity(message.content, message.guild.id)

        if detected:
            word = detected['word']
            severity = detected['severity']

            # Delete the offending message if the guild config requires it
            if config.get('delete_message', True):
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass

            # Determine the appropriate punishment based on infraction history
            punishment = await db.determine_punishment(message.author.id, message.guild.id)

            # Record the infraction in the database and get updated stats
            stats = await db.add_profanity_infraction(
                user_id=message.author.id,
                guild_id=message.guild.id,
                word_used=word,
                message_content=message.content,
                action_taken=punishment
            )

            # Apply the determined punishment to the member
            reason = f"Utilisation de mot interdit (infraction #{stats['total_infractions']})"
            punishment_applied = await self.apply_punishment(
                message.author, punishment, message.guild, reason
            )

            # Human-readable punishment descriptions for embeds
            punishment_messages = {
                "warn": f"Vous avez reçu un avertissement.",
                "mute": f"Vous avez été mute.",
                "kick": f"Vous avez été expulsé du serveur.",
                "ban": f"Vous avez été banni du serveur."
            }

            # Send a DM to the user with infraction details (if configured)
            if config.get('dm_user', True):
                try:
                    dm_embed = discord.Embed(
                        title=f"{Emojis.WARNING} Infraction sur {message.guild.name}",
                        description=f"Votre message contenait un mot interdit.",
                        color=Colors.ERROR,
                        timestamp=datetime.now()
                    )
                    dm_embed.add_field(
                        name="Sanction",
                        value=punishment_messages.get(punishment, "Avertissement"),
                        inline=True
                    )
                    dm_embed.add_field(
                        name="Infractions totales",
                        value=str(stats['total_infractions']),
                        inline=True
                    )

                    # Warn the user about upcoming punishment escalations
                    next_config = await db.get_profanity_config(message.guild.id)
                    next_actions = []
                    if stats['total_infractions'] + 1 >= next_config['mute_threshold'] and punishment != "mute":
                        next_actions.append(f"Mute à {next_config['mute_threshold']} infractions")
                    if stats['total_infractions'] + 1 >= next_config['kick_threshold'] and punishment != "kick":
                        next_actions.append(f"Kick à {next_config['kick_threshold']} infractions")
                    if stats['total_infractions'] + 1 >= next_config['ban_threshold'] and punishment != "ban":
                        next_actions.append(f"Ban à {next_config['ban_threshold']} infractions")

                    if next_actions:
                        dm_embed.add_field(
                            name="Prochaines sanctions",
                            value="\n".join(next_actions),
                            inline=False
                        )

                    await message.author.send(embed=dm_embed)
                except discord.Forbidden:
                    # User has DMs disabled; silently skip
                    pass

            # Post a temporary warning in the channel (auto-deletes after 10s)
            warning_embed = discord.Embed(
                title=f"{Emojis.WARNING} Mot interdit détecté",
                description=f"{message.author.mention}, votre message a été supprimé.",
                color=Colors.ERROR
            )
            warning_embed.add_field(
                name="Sanction",
                value=punishment_messages.get(punishment, "Avertissement"),
                inline=True
            )
            warning_embed.add_field(
                name="Infractions",
                value=f"{stats['total_infractions']}",
                inline=True
            )

            try:
                warning_msg = await message.channel.send(embed=warning_embed, delete_after=10)
            except discord.Forbidden:
                pass

            # Log the infraction to the moderation log channel
            if config.get('log_infractions', True):
                log_embed = discord.Embed(
                    title=f"{Emojis.WARNING} Infraction - Mot Interdit",
                    color=Colors.ERROR,
                    timestamp=datetime.now()
                )
                log_embed.add_field(name="Utilisateur", value=f"{message.author.mention} ({message.author.id})", inline=True)
                log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                # Word is wrapped in spoiler tags to avoid displaying it openly in logs
                log_embed.add_field(name="Mot détecté", value=f"||{word}||", inline=True)
                log_embed.add_field(name="Sévérité", value=f"{severity}/5", inline=True)
                log_embed.add_field(name="Sanction", value=punishment.capitalize(), inline=True)
                log_embed.add_field(name="Total infractions", value=str(stats['total_infractions']), inline=True)
                log_embed.add_field(name="Message original", value=f"||{message.content[:200]}||" if message.content else "N/A", inline=False)

                await self.log_infraction(message.guild, log_embed)

    # =========================================================================
    # BANNED WORD MANAGEMENT COMMANDS
    # =========================================================================

    @commands.hybrid_group(name="badword", aliases=["bw", "motinterdit"])
    @commands.has_permissions(manage_messages=True)
    async def badword(self, ctx: commands.Context):
        """Command group for managing the banned word list.

        If invoked without a subcommand, displays the help text for available
        subcommands (add, remove, list, import).

        Args:
            ctx: The command invocation context.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @badword.command(name="add", aliases=["ajouter"])
    @app_commands.describe(
        mot="Le mot à interdire",
        langue="Langue du mot (fr, en, es, de, it, pt, ar, all)",
        severite="Sévérité de 1 à 5 (5 = ban immédiat)"
    )
    async def badword_add(self, ctx: commands.Context, mot: str,
                          langue: str = "all", severite: int = 2):
        """Add a word to the guild's banned word list.

        The word is stored in lowercase and associated with a language category
        and severity level. Higher severity words result in harsher punishments.

        Args:
            ctx: The command invocation context.
            mot: The word to ban (stored in lowercase).
            langue: Language category code (e.g., "fr", "en", "all"). Defaults to "all".
            severite: Severity level from 1 (mild) to 5 (maximum). Defaults to 2.
        """
        if severite < 1 or severite > 5:
            return await ctx.send(f"{Emojis.ERROR} La sévérité doit être entre 1 et 5.")

        # Add the word specifically for this guild
        success = await db.add_banned_word(
            word=mot.lower(),
            language=langue,
            guild_id=ctx.guild.id,
            severity=severite,
            added_by=ctx.author.id
        )

        if success:
            embed = discord.Embed(
                title=f"{Emojis.SUCCESS} Mot interdit ajouté",
                description=f"**Mot:** ||{mot}||\n**Langue:** {self.language_names.get(langue, langue)}\n**Sévérité:** {severite}/5",
                color=Colors.SUCCESS
            )
        else:
            embed = discord.Embed(
                title=f"{Emojis.ERROR} Erreur",
                description="Ce mot est déjà dans la liste.",
                color=Colors.ERROR
            )

        await ctx.send(embed=embed)

    @badword.command(name="remove", aliases=["supprimer", "rm"])
    @app_commands.describe(mot="Le mot à retirer de la liste")
    async def badword_remove(self, ctx: commands.Context, mot: str):
        """Remove a word from the guild's banned word list.

        Args:
            ctx: The command invocation context.
            mot: The word to remove (matched case-insensitively).
        """
        success = await db.remove_banned_word(mot.lower(), ctx.guild.id)

        if success:
            embed = discord.Embed(
                title=f"{Emojis.SUCCESS} Mot retiré",
                description=f"Le mot ||{mot}|| a été retiré de la liste.",
                color=Colors.SUCCESS
            )
        else:
            embed = discord.Embed(
                title=f"{Emojis.ERROR} Erreur",
                description="Ce mot n'est pas dans la liste du serveur.",
                color=Colors.ERROR
            )

        await ctx.send(embed=embed)

    @badword.command(name="list", aliases=["liste"])
    @app_commands.describe(langue="Filtrer par langue (optionnel)")
    async def badword_list(self, ctx: commands.Context, langue: str = None):
        """Display the guild's banned word list, optionally filtered by language.

        Words are grouped by language and displayed with their severity levels.
        Each word is wrapped in spoiler tags. To prevent embed overflow, at most
        10 language groups and 15 words per group are shown.

        Args:
            ctx: The command invocation context.
            langue: Optional language code to filter by (e.g., "fr", "en").
        """
        words = await db.get_banned_words(ctx.guild.id, langue)

        if not words:
            return await ctx.send(f"{Emojis.INFO} Aucun mot interdit configuré.")

        # Group words by their language category
        by_language = {}
        for w in words:
            lang = w['language']
            if lang not in by_language:
                by_language[lang] = []
            by_language[lang].append(w)

        embed = discord.Embed(
            title="Liste des mots interdits",
            description=f"Total: **{len(words)}** mots",
            color=Colors.PRIMARY
        )

        # Show at most 10 language groups to avoid exceeding embed limits
        for lang, word_list in list(by_language.items())[:10]:
            lang_name = self.language_names.get(lang, lang)
            # Show at most 15 words per language, with spoiler tags
            words_str = ", ".join(f"||{w['word']}|| ({w['severity']})" for w in word_list[:15])
            if len(word_list) > 15:
                words_str += f" ... et {len(word_list) - 15} autres"
            embed.add_field(
                name=f"{lang_name} ({len(word_list)})",
                value=words_str,
                inline=False
            )

        embed.set_footer(text="Utilisez !badword add/remove pour gérer la liste")
        await ctx.send(embed=embed)

    @badword.command(name="import", aliases=["importer"])
    @commands.has_permissions(administrator=True)
    @app_commands.describe(mots="Liste de mots séparés par des virgules")
    async def badword_import(self, ctx: commands.Context, *, mots: str):
        """[Admin] Bulk-import multiple banned words at once.

        Accepts a comma-separated list of words. All words are added with
        the "all" language category and a default severity of 2. Duplicate
        words (already in the list) are silently skipped.

        Args:
            ctx: The command invocation context.
            mots: Comma-separated list of words to ban.
        """
        words = [w.strip().lower() for w in mots.split(",") if w.strip()]

        added = 0
        for word in words:
            success = await db.add_banned_word(word, "all", ctx.guild.id, 2, ctx.author.id)
            if success:
                added += 1

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Import terminé",
            description=f"**{added}** mots ajoutés sur **{len(words)}** fournis.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    # =========================================================================
    # INFRACTION STATISTICS COMMANDS
    # =========================================================================

    @commands.hybrid_command(name="infractions", aliases=["profanity"])
    @app_commands.describe(membre="Le membre dont voir les infractions")
    async def infractions(self, ctx: commands.Context, membre: Optional[discord.Member] = None):
        """Display a member's profanity infraction statistics and recent history.

        Shows total infractions, breakdown by punishment type (warnings, mutes,
        kicks), ban status, last infraction date, and the 5 most recent
        infraction entries with detected words (spoilered) and actions taken.

        Args:
            ctx: The command invocation context.
            membre: The member whose stats to view. Defaults to the command author.
        """
        member = membre or ctx.author

        stats = await db.get_user_profanity_stats(member.id, ctx.guild.id)
        history = await db.get_user_profanity_history(member.id, ctx.guild.id, 5)

        embed = discord.Embed(
            title=f"Infractions de {member.display_name}",
            color=Colors.WARNING if stats['total_infractions'] > 0 else Colors.SUCCESS,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="Total infractions", value=str(stats['total_infractions']), inline=True)
        embed.add_field(name="Avertissements", value=str(stats['warnings_count']), inline=True)
        embed.add_field(name="Mutes", value=str(stats['mutes_count']), inline=True)
        embed.add_field(name="Kicks", value=str(stats['kicks_count']), inline=True)
        embed.add_field(name="Banni", value="Oui" if stats['is_banned'] else "Non", inline=True)

        if stats['last_infraction']:
            last = datetime.fromisoformat(stats['last_infraction'])
            embed.add_field(name="Dernière infraction", value=last.strftime("%d/%m/%Y %H:%M"), inline=True)

        if history:
            history_text = ""
            for h in history:
                date = datetime.fromisoformat(h['created_at']).strftime("%d/%m")
                # Words are spoilered to avoid displaying profanity in the embed
                history_text += f"`{date}` ||{h['word_used']}|| → {h['action_taken']}\n"
            embed.add_field(name="Historique récent", value=history_text, inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="infractionsleaderboard", aliases=["badusers"])
    async def infractions_leaderboard(self, ctx: commands.Context):
        """Display a leaderboard of users with the most profanity infractions.

        Shows the top 10 users ranked by total infraction count, with medal
        emojis for the top 3 positions.

        Args:
            ctx: The command invocation context.
        """
        leaderboard = await db.get_profanity_leaderboard(ctx.guild.id, 10)

        if not leaderboard:
            return await ctx.send(f"{Emojis.INFO} Aucune infraction enregistrée.")

        embed = discord.Embed(
            title=f"{Emojis.WARNING} Classement des infractions",
            color=Colors.WARNING
        )

        lines = []
        medals = ["", "", ""]  # Gold, silver, bronze for top 3
        for i, data in enumerate(leaderboard, 1):
            member = ctx.guild.get_member(data['user_id'])
            name = member.display_name if member else f"Utilisateur #{data['user_id']}"
            medal = medals[i-1] if i <= 3 else f"**{i}.**"
            lines.append(f"{medal} {name} - {data['total_infractions']} infractions")

        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="resetinfractions")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(membre="Le membre dont réinitialiser les infractions")
    async def reset_infractions(self, ctx: commands.Context, membre: discord.Member):
        """[Admin] Reset all profanity infractions for a member.

        Clears the member's entire infraction history, effectively giving them
        a clean slate. Requires the ``administrator`` permission.

        Args:
            ctx: The command invocation context.
            membre: The member whose infractions should be reset.
        """
        await db.reset_user_profanity_stats(membre.id, ctx.guild.id)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Infractions réinitialisées",
            description=f"Les infractions de {membre.mention} ont été remises à zéro.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    # =========================================================================
    # PUNISHMENT CONFIGURATION COMMANDS
    # =========================================================================

    @commands.hybrid_group(name="profanityconfig", aliases=["pconfig"])
    @commands.has_permissions(administrator=True)
    async def profanity_config(self, ctx: commands.Context):
        """Command group for configuring the profanity filter system.

        When invoked without a subcommand, displays the current configuration
        including enabled state, message deletion setting, DM preference,
        punishment thresholds, and mute duration.

        Args:
            ctx: The command invocation context.
        """
        if ctx.invoked_subcommand is None:
            config = await db.get_profanity_config(ctx.guild.id)

            embed = discord.Embed(
                title="Configuration du filtre de profanity",
                color=Colors.PRIMARY
            )

            embed.add_field(name="Activé", value="Oui" if config['enabled'] else "Non", inline=True)
            embed.add_field(name="Supprimer message", value="Oui" if config['delete_message'] else "Non", inline=True)
            embed.add_field(name="DM utilisateur", value="Oui" if config['dm_user'] else "Non", inline=True)

            embed.add_field(name="Seuil warn", value=f"{config['warn_threshold']} infractions", inline=True)
            embed.add_field(name="Seuil mute", value=f"{config['mute_threshold']} infractions", inline=True)
            embed.add_field(name="Seuil kick", value=f"{config['kick_threshold']} infractions", inline=True)
            embed.add_field(name="Seuil ban", value=f"{config['ban_threshold']} infractions", inline=True)
            embed.add_field(name="Durée mute", value=f"{config['mute_duration'] // 60} minutes", inline=True)

            embed.set_footer(text="Utilisez !profanityconfig <option> <valeur> pour modifier")
            await ctx.send(embed=embed)

    @profanity_config.command(name="enable")
    @app_commands.describe(etat="on/off")
    async def pconfig_enable(self, ctx: commands.Context, etat: str):
        """Enable or disable the profanity filter for this guild.

        Accepts various truthy/falsy values: on/off, true/false, 1/0, oui/non, yes/no.

        Args:
            ctx: The command invocation context.
            etat: The desired state ("on"/"off" or equivalent).
        """
        enabled = etat.lower() in ['on', 'true', '1', 'oui', 'yes']
        await db.update_profanity_config(ctx.guild.id, enabled=1 if enabled else 0)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Filtre {'activé' if enabled else 'désactivé'}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @profanity_config.command(name="threshold")
    @app_commands.describe(
        type="Type de sanction (warn, mute, kick, ban)",
        nombre="Nombre d'infractions avant cette sanction"
    )
    async def pconfig_threshold(self, ctx: commands.Context, type: str, nombre: int):
        """Configure the infraction count threshold for a specific punishment type.

        Sets how many infractions a user must accumulate before the specified
        punishment is applied. The thresholds should be ordered:
        warn < mute < kick < ban.

        Args:
            ctx: The command invocation context.
            type: The punishment type to configure ("warn", "mute", "kick", or "ban").
            nombre: The number of infractions required to trigger this punishment.
        """
        type = type.lower()
        if type not in ['warn', 'mute', 'kick', 'ban']:
            return await ctx.send(f"{Emojis.ERROR} Type invalide. Utilisez: warn, mute, kick, ban")

        if nombre < 1:
            return await ctx.send(f"{Emojis.ERROR} Le nombre doit être positif.")

        # Dynamically build the keyword argument for the database update
        await db.update_profanity_config(ctx.guild.id, **{f"{type}_threshold": nombre})

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Seuil modifié",
            description=f"**{type.capitalize()}** sera appliqué après **{nombre}** infractions.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @profanity_config.command(name="muteduration")
    @app_commands.describe(minutes="Durée du mute en minutes")
    async def pconfig_muteduration(self, ctx: commands.Context, minutes: int):
        """Configure the duration of mute punishments (in minutes).

        The duration is stored in seconds internally. Discord's maximum
        timeout is 28 days (40,320 minutes).

        Args:
            ctx: The command invocation context.
            minutes: Mute duration in minutes (1 to 40320).
        """
        # Discord timeout maximum is 28 days (40320 minutes)
        if minutes < 1 or minutes > 40320:
            return await ctx.send(f"{Emojis.ERROR} La durée doit être entre 1 et 40320 minutes.")

        # Convert minutes to seconds for internal storage
        await db.update_profanity_config(ctx.guild.id, mute_duration=minutes * 60)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Durée de mute modifiée",
            description=f"Les utilisateurs seront mute pendant **{minutes}** minutes.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    @profanity_config.command(name="dm")
    @app_commands.describe(etat="on/off - Envoyer un DM aux utilisateurs")
    async def pconfig_dm(self, ctx: commands.Context, etat: str):
        """Enable or disable sending DM notifications to users on infractions.

        When enabled, users receive a DM with details about their infraction,
        the applied punishment, and upcoming punishment thresholds.

        Args:
            ctx: The command invocation context.
            etat: The desired state ("on"/"off" or equivalent).
        """
        enabled = etat.lower() in ['on', 'true', '1', 'oui', 'yes']
        await db.update_profanity_config(ctx.guild.id, dm_user=1 if enabled else 0)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} DM {'activés' if enabled else 'désactivés'}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Entry point for loading this cog into the bot.

    Called by ``bot.load_extension('cogs.profanity_filter')``.

    Args:
        bot: The Discord bot instance to attach the cog to.
    """
    await bot.add_cog(ProfanityFilter(bot))
