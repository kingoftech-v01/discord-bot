"""
Models for the Discord Bot Dashboard.
These models reflect the bot's database tables.
"""
from django.db import models


class GuildConfig(models.Model):
    """Server configuration model."""
    guild_id = models.BigIntegerField(primary_key=True)
    welcome_channel_id = models.BigIntegerField(null=True, blank=True)
    log_channel_id = models.BigIntegerField(null=True, blank=True)
    level_up_channel_id = models.BigIntegerField(null=True, blank=True)
    mute_role_id = models.BigIntegerField(null=True, blank=True)
    auto_mod_enabled = models.IntegerField(default=1)
    leveling_enabled = models.IntegerField(default=1)
    welcome_message = models.TextField(default='Bienvenue {user} sur {server}!')
    goodbye_message = models.TextField(default='{user} a quitté le serveur.')
    level_up_message = models.TextField(default='Félicitations {user}! Tu es maintenant niveau {level}!')
    prefix = models.CharField(max_length=10, default='!')
    settings = models.TextField(default='{}')

    class Meta:
        db_table = 'guild_config'
        managed = False

    def __str__(self):
        return f"Guild {self.guild_id}"


class BotUser(models.Model):
    """User data model (XP, levels, economy)."""
    user_id = models.BigIntegerField()
    guild_id = models.BigIntegerField()
    xp = models.IntegerField(default=0)
    level = models.IntegerField(default=1)
    total_xp = models.IntegerField(default=0)
    messages_count = models.IntegerField(default=0)
    coins = models.IntegerField(default=0)
    last_xp_gain = models.TextField(null=True, blank=True)
    last_daily = models.TextField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'users'
        managed = False
        unique_together = ('user_id', 'guild_id')

    def __str__(self):
        return f"User {self.user_id} in Guild {self.guild_id}"


class Warning(models.Model):
    """Warning model."""
    id = models.AutoField(primary_key=True)
    user_id = models.BigIntegerField()
    guild_id = models.BigIntegerField()
    moderator_id = models.BigIntegerField()
    reason = models.TextField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'warnings'
        managed = False


class BannedWord(models.Model):
    """Banned word model."""
    id = models.AutoField(primary_key=True)
    word = models.TextField()
    language = models.CharField(max_length=10, default='all')
    guild_id = models.BigIntegerField(default=0)
    severity = models.IntegerField(default=1)
    added_by = models.BigIntegerField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'banned_words'
        managed = False
        unique_together = ('word', 'guild_id')

    def __str__(self):
        return f"{self.word} ({self.language})"


class ProfanityInfraction(models.Model):
    """Profanity infraction log."""
    id = models.AutoField(primary_key=True)
    user_id = models.BigIntegerField()
    guild_id = models.BigIntegerField()
    word_used = models.TextField()
    message_content = models.TextField(null=True, blank=True)
    action_taken = models.TextField(null=True, blank=True)
    created_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'profanity_infractions'
        managed = False


class UserProfanityStats(models.Model):
    """User profanity statistics."""
    user_id = models.BigIntegerField(primary_key=True)
    guild_id = models.BigIntegerField()
    total_infractions = models.IntegerField(default=0)
    warnings_count = models.IntegerField(default=0)
    mutes_count = models.IntegerField(default=0)
    kicks_count = models.IntegerField(default=0)
    is_banned = models.IntegerField(default=0)
    last_infraction = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'user_profanity_stats'
        managed = False
        unique_together = ('user_id', 'guild_id')


class ProfanityConfig(models.Model):
    """Profanity filter configuration."""
    guild_id = models.BigIntegerField(primary_key=True)
    enabled = models.IntegerField(default=1)
    warn_threshold = models.IntegerField(default=3)
    mute_threshold = models.IntegerField(default=5)
    kick_threshold = models.IntegerField(default=8)
    ban_threshold = models.IntegerField(default=10)
    mute_duration = models.IntegerField(default=3600)
    delete_message = models.IntegerField(default=1)
    log_infractions = models.IntegerField(default=1)
    dm_user = models.IntegerField(default=1)

    class Meta:
        db_table = 'profanity_config'
        managed = False


class LevelRole(models.Model):
    """Level role rewards."""
    id = models.AutoField(primary_key=True)
    guild_id = models.BigIntegerField()
    level = models.IntegerField()
    role_id = models.BigIntegerField()

    class Meta:
        db_table = 'level_roles'
        managed = False
        unique_together = ('guild_id', 'level')


class ReactionRole(models.Model):
    """Reaction role configuration."""
    id = models.AutoField(primary_key=True)
    guild_id = models.BigIntegerField()
    message_id = models.BigIntegerField()
    channel_id = models.BigIntegerField()
    emoji = models.TextField()
    role_id = models.BigIntegerField()

    class Meta:
        db_table = 'reaction_roles'
        managed = False
        unique_together = ('message_id', 'emoji')


class Ticket(models.Model):
    """Support ticket."""
    id = models.AutoField(primary_key=True)
    guild_id = models.BigIntegerField()
    channel_id = models.BigIntegerField()
    user_id = models.BigIntegerField()
    subject = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, default='open')
    created_at = models.TextField(null=True, blank=True)
    closed_at = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'tickets'
        managed = False
