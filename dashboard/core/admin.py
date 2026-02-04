"""
Admin configuration for the dashboard.
"""
from django.contrib import admin
from .models import (
    GuildConfig, BotUser, BannedWord, ProfanityConfig,
    ProfanityInfraction, UserProfanityStats, LevelRole, Warning
)


@admin.register(GuildConfig)
class GuildConfigAdmin(admin.ModelAdmin):
    list_display = ['guild_id', 'prefix', 'auto_mod_enabled', 'leveling_enabled']
    search_fields = ['guild_id']


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'guild_id', 'level', 'total_xp', 'coins']
    search_fields = ['user_id', 'guild_id']
    list_filter = ['guild_id']


@admin.register(BannedWord)
class BannedWordAdmin(admin.ModelAdmin):
    list_display = ['word', 'language', 'severity', 'guild_id']
    search_fields = ['word']
    list_filter = ['language', 'severity']


@admin.register(ProfanityInfraction)
class ProfanityInfractionAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'guild_id', 'word_used', 'action_taken', 'created_at']
    search_fields = ['user_id', 'word_used']
    list_filter = ['action_taken', 'guild_id']


@admin.register(UserProfanityStats)
class UserProfanityStatsAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'guild_id', 'total_infractions', 'warnings_count', 'mutes_count', 'kicks_count']
    search_fields = ['user_id']


@admin.register(LevelRole)
class LevelRoleAdmin(admin.ModelAdmin):
    list_display = ['guild_id', 'level', 'role_id']
    list_filter = ['guild_id']
