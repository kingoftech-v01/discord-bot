"""
Cog pour le filtrage des mots interdits avec sanctions progressives.
Détecte les insultes dans toutes les langues et applique des sanctions automatiques.
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
    """Système avancé de filtrage des mots interdits avec sanctions progressives."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
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
        """Envoie un log d'infraction dans le channel de logs."""
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
        """Applique une sanction à un membre."""
        try:
            if punishment == "warn":
                # Juste un avertissement, pas d'action Discord
                return True

            elif punishment == "mute":
                config = await db.get_profanity_config(guild.id)
                duration = config.get('mute_duration', 3600)
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
        """Détecte les mots interdits dans les messages."""
        # Ignorer les bots et les DMs
        if message.author.bot or not message.guild:
            return

        # Ignorer les administrateurs
        if message.author.guild_permissions.administrator:
            return

        # Vérifier si le filtre est activé
        config = await db.get_profanity_config(message.guild.id)
        if not config.get('enabled', True):
            return

        # Vérifier le message
        detected = await db.check_message_for_profanity(message.content, message.guild.id)

        if detected:
            word = detected['word']
            severity = detected['severity']

            # Supprimer le message si configuré
            if config.get('delete_message', True):
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass

            # Déterminer la sanction
            punishment = await db.determine_punishment(message.author.id, message.guild.id)

            # Enregistrer l'infraction
            stats = await db.add_profanity_infraction(
                user_id=message.author.id,
                guild_id=message.guild.id,
                word_used=word,
                message_content=message.content,
                action_taken=punishment
            )

            # Appliquer la sanction
            reason = f"Utilisation de mot interdit (infraction #{stats['total_infractions']})"
            punishment_applied = await self.apply_punishment(
                message.author, punishment, message.guild, reason
            )

            # Messages de sanction
            punishment_messages = {
                "warn": f"Vous avez reçu un avertissement.",
                "mute": f"Vous avez été mute.",
                "kick": f"Vous avez été expulsé du serveur.",
                "ban": f"Vous avez été banni du serveur."
            }

            # Envoyer un DM à l'utilisateur si configuré
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

                    # Avertissements sur les prochaines sanctions
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
                    pass

            # Envoyer un message dans le channel
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

            # Logger l'infraction
            if config.get('log_infractions', True):
                log_embed = discord.Embed(
                    title=f"{Emojis.WARNING} Infraction - Mot Interdit",
                    color=Colors.ERROR,
                    timestamp=datetime.now()
                )
                log_embed.add_field(name="Utilisateur", value=f"{message.author.mention} ({message.author.id})", inline=True)
                log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                log_embed.add_field(name="Mot détecté", value=f"||{word}||", inline=True)
                log_embed.add_field(name="Sévérité", value=f"{severity}/5", inline=True)
                log_embed.add_field(name="Sanction", value=punishment.capitalize(), inline=True)
                log_embed.add_field(name="Total infractions", value=str(stats['total_infractions']), inline=True)
                log_embed.add_field(name="Message original", value=f"||{message.content[:200]}||" if message.content else "N/A", inline=False)

                await self.log_infraction(message.guild, log_embed)

    # ===============================
    # COMMANDES DE GESTION
    # ===============================

    @commands.hybrid_group(name="badword", aliases=["bw", "motinterdit"])
    @commands.has_permissions(manage_messages=True)
    async def badword(self, ctx: commands.Context):
        """Commandes de gestion des mots interdits."""
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
        """Ajoute un mot à la liste des mots interdits."""
        if severite < 1 or severite > 5:
            return await ctx.send(f"{Emojis.ERROR} La sévérité doit être entre 1 et 5.")

        # Ajouter pour ce serveur spécifiquement
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
        """Retire un mot de la liste des mots interdits du serveur."""
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
        """Affiche la liste des mots interdits."""
        words = await db.get_banned_words(ctx.guild.id, langue)

        if not words:
            return await ctx.send(f"{Emojis.INFO} Aucun mot interdit configuré.")

        # Grouper par langue
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

        for lang, word_list in list(by_language.items())[:10]:
            lang_name = self.language_names.get(lang, lang)
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
        """[Admin] Importe plusieurs mots d'un coup."""
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

    # ===============================
    # COMMANDES DE STATISTIQUES
    # ===============================

    @commands.hybrid_command(name="infractions", aliases=["profanity"])
    @app_commands.describe(membre="Le membre dont voir les infractions")
    async def infractions(self, ctx: commands.Context, membre: Optional[discord.Member] = None):
        """Affiche les statistiques d'infractions d'un membre."""
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
                history_text += f"`{date}` ||{h['word_used']}|| → {h['action_taken']}\n"
            embed.add_field(name="Historique récent", value=history_text, inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="infractionsleaderboard", aliases=["badusers"])
    async def infractions_leaderboard(self, ctx: commands.Context):
        """Affiche le classement des utilisateurs avec le plus d'infractions."""
        leaderboard = await db.get_profanity_leaderboard(ctx.guild.id, 10)

        if not leaderboard:
            return await ctx.send(f"{Emojis.INFO} Aucune infraction enregistrée.")

        embed = discord.Embed(
            title=f"{Emojis.WARNING} Classement des infractions",
            color=Colors.WARNING
        )

        lines = []
        medals = ["", "", ""]
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
        """[Admin] Réinitialise les infractions d'un membre."""
        await db.reset_user_profanity_stats(membre.id, ctx.guild.id)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} Infractions réinitialisées",
            description=f"Les infractions de {membre.mention} ont été remises à zéro.",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)

    # ===============================
    # CONFIGURATION DES SANCTIONS
    # ===============================

    @commands.hybrid_group(name="profanityconfig", aliases=["pconfig"])
    @commands.has_permissions(administrator=True)
    async def profanity_config(self, ctx: commands.Context):
        """Configuration du système de filtrage des mots interdits."""
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
        """Active ou désactive le filtre."""
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
        """Configure les seuils de sanction."""
        type = type.lower()
        if type not in ['warn', 'mute', 'kick', 'ban']:
            return await ctx.send(f"{Emojis.ERROR} Type invalide. Utilisez: warn, mute, kick, ban")

        if nombre < 1:
            return await ctx.send(f"{Emojis.ERROR} Le nombre doit être positif.")

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
        """Configure la durée du mute."""
        if minutes < 1 or minutes > 40320:  # Max 28 jours
            return await ctx.send(f"{Emojis.ERROR} La durée doit être entre 1 et 40320 minutes.")

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
        """Active/désactive les DMs aux utilisateurs."""
        enabled = etat.lower() in ['on', 'true', '1', 'oui', 'yes']
        await db.update_profanity_config(ctx.guild.id, dm_user=1 if enabled else 0)

        embed = discord.Embed(
            title=f"{Emojis.SUCCESS} DM {'activés' if enabled else 'désactivés'}",
            color=Colors.SUCCESS
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfanityFilter(bot))
