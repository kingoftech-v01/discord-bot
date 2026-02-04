"""
Views for the Discord Bot Dashboard.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings
import requests

from .models import (
    GuildConfig, BotUser, BannedWord, ProfanityConfig,
    ProfanityInfraction, UserProfanityStats, LevelRole, Warning
)


def get_user_guilds(request):
    """Get guilds where user has admin permissions and bot is present."""
    if not request.user.is_authenticated:
        return []

    try:
        social_account = request.user.socialaccount_set.filter(provider='discord').first()
        if not social_account:
            return []

        token = social_account.socialtoken_set.first()
        if not token:
            return []

        # Get user's guilds from Discord API
        headers = {'Authorization': f'Bearer {token.token}'}
        response = requests.get(
            f'{settings.DISCORD_API_BASE}/users/@me/guilds',
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            return []

        user_guilds = response.json()

        # Filter guilds where user has admin/manage permissions
        admin_guilds = []
        for guild in user_guilds:
            permissions = int(guild.get('permissions', 0))
            # Check for Administrator (0x8) or Manage Server (0x20)
            if permissions & 0x8 or permissions & 0x20:
                # Check if bot is in this guild
                try:
                    config = GuildConfig.objects.filter(guild_id=int(guild['id'])).first()
                    guild['bot_present'] = config is not None
                    guild['config'] = config
                except Exception:
                    guild['bot_present'] = False
                admin_guilds.append(guild)

        return admin_guilds
    except Exception as e:
        print(f"Error getting guilds: {e}")
        return []


def home(request):
    """Home page."""
    return render(request, 'core/home.html')


@login_required
def dashboard(request):
    """Main dashboard - server selection."""
    guilds = get_user_guilds(request)
    return render(request, 'core/dashboard.html', {'guilds': guilds})


@login_required
def server_dashboard(request, guild_id):
    """Server-specific dashboard."""
    guilds = get_user_guilds(request)
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "Vous n'avez pas accès à ce serveur.")
        return redirect('dashboard')

    try:
        config = GuildConfig.objects.get(guild_id=guild_id)
    except GuildConfig.DoesNotExist:
        config = GuildConfig.objects.create(guild_id=guild_id)

    # Get stats
    users_count = BotUser.objects.filter(guild_id=guild_id).count()
    warnings_count = Warning.objects.filter(guild_id=guild_id).count()
    banned_words_count = BannedWord.objects.filter(guild_id__in=[0, guild_id]).count()

    # Get top users by XP
    top_users = BotUser.objects.filter(guild_id=guild_id).order_by('-total_xp')[:5]

    # Get recent infractions
    recent_infractions = ProfanityInfraction.objects.filter(
        guild_id=guild_id
    ).order_by('-created_at')[:10]

    context = {
        'guild': guild,
        'config': config,
        'guilds': guilds,
        'users_count': users_count,
        'warnings_count': warnings_count,
        'banned_words_count': banned_words_count,
        'top_users': top_users,
        'recent_infractions': recent_infractions,
    }
    return render(request, 'core/server_dashboard.html', context)


@login_required
def server_settings(request, guild_id):
    """Server general settings."""
    guilds = get_user_guilds(request)
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "Vous n'avez pas accès à ce serveur.")
        return redirect('dashboard')

    try:
        config = GuildConfig.objects.get(guild_id=guild_id)
    except GuildConfig.DoesNotExist:
        config = GuildConfig.objects.create(guild_id=guild_id)

    if request.method == 'POST':
        config.prefix = request.POST.get('prefix', '!')[:10]
        config.auto_mod_enabled = 1 if request.POST.get('auto_mod_enabled') else 0
        config.leveling_enabled = 1 if request.POST.get('leveling_enabled') else 0
        config.welcome_message = request.POST.get('welcome_message', '')
        config.goodbye_message = request.POST.get('goodbye_message', '')
        config.level_up_message = request.POST.get('level_up_message', '')
        config.save()
        messages.success(request, 'Configuration sauvegardée!')
        return redirect('server_settings', guild_id=guild_id)

    context = {
        'guild': guild,
        'config': config,
        'guilds': guilds,
    }
    return render(request, 'core/server_settings.html', context)


@login_required
def moderation_settings(request, guild_id):
    """Moderation and profanity filter settings."""
    guilds = get_user_guilds(request)
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "Vous n'avez pas accès à ce serveur.")
        return redirect('dashboard')

    try:
        profanity_config = ProfanityConfig.objects.get(guild_id=guild_id)
    except ProfanityConfig.DoesNotExist:
        profanity_config = ProfanityConfig.objects.create(guild_id=guild_id)

    # Get banned words (global + server-specific)
    banned_words = BannedWord.objects.filter(guild_id__in=[0, guild_id]).order_by('-severity', 'word')

    # Get server-specific words
    server_words = BannedWord.objects.filter(guild_id=guild_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_config':
            profanity_config.enabled = 1 if request.POST.get('enabled') else 0
            profanity_config.warn_threshold = int(request.POST.get('warn_threshold', 3))
            profanity_config.mute_threshold = int(request.POST.get('mute_threshold', 5))
            profanity_config.kick_threshold = int(request.POST.get('kick_threshold', 8))
            profanity_config.ban_threshold = int(request.POST.get('ban_threshold', 10))
            profanity_config.mute_duration = int(request.POST.get('mute_duration', 60)) * 60
            profanity_config.delete_message = 1 if request.POST.get('delete_message') else 0
            profanity_config.dm_user = 1 if request.POST.get('dm_user') else 0
            profanity_config.save()
            messages.success(request, 'Configuration de modération sauvegardée!')

        elif action == 'add_word':
            word = request.POST.get('word', '').strip().lower()
            language = request.POST.get('language', 'all')
            severity = int(request.POST.get('severity', 2))
            if word:
                BannedWord.objects.get_or_create(
                    word=word,
                    guild_id=guild_id,
                    defaults={'language': language, 'severity': severity}
                )
                messages.success(request, f'Mot "{word}" ajouté!')

        elif action == 'delete_word':
            word_id = request.POST.get('word_id')
            BannedWord.objects.filter(id=word_id, guild_id=guild_id).delete()
            messages.success(request, 'Mot supprimé!')

        return redirect('moderation_settings', guild_id=guild_id)

    context = {
        'guild': guild,
        'guilds': guilds,
        'profanity_config': profanity_config,
        'banned_words': banned_words,
        'server_words': server_words,
    }
    return render(request, 'core/moderation_settings.html', context)


@login_required
def leveling_settings(request, guild_id):
    """Leveling system settings."""
    from django.db.models import Sum, Avg, Max, Count

    guilds = get_user_guilds(request)
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "Vous n'avez pas acces a ce serveur.")
        return redirect('dashboard')

    try:
        config = GuildConfig.objects.get(guild_id=guild_id)
    except GuildConfig.DoesNotExist:
        config = GuildConfig.objects.create(guild_id=guild_id)

    level_roles = LevelRole.objects.filter(guild_id=guild_id).order_by('level')
    top_users = BotUser.objects.filter(guild_id=guild_id).order_by('-total_xp')[:5]

    # Compute stats
    stats_qs = BotUser.objects.filter(guild_id=guild_id).aggregate(
        total_users=Count('user_id'),
        total_xp=Sum('total_xp'),
        avg_level=Avg('level'),
        max_level=Max('level')
    )
    stats = {
        'total_users': stats_qs['total_users'] or 0,
        'total_xp': stats_qs['total_xp'] or 0,
        'avg_level': stats_qs['avg_level'] or 0,
        'max_level': stats_qs['max_level'] or 0,
    }

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'toggle_leveling':
            config.leveling_enabled = 1 if request.POST.get('leveling_enabled') else 0
            config.save()
            messages.success(request, 'Parametre mis a jour!')

        elif action == 'add_level_role':
            level = int(request.POST.get('level', 0))
            role_id = request.POST.get('role_id', '')
            if level > 0 and role_id:
                LevelRole.objects.update_or_create(
                    guild_id=guild_id,
                    level=level,
                    defaults={'role_id': int(role_id)}
                )
                messages.success(request, f'Role pour le niveau {level} ajoute!')

        elif action == 'delete_level_role':
            role_id = request.POST.get('role_id')
            if role_id:
                LevelRole.objects.filter(id=role_id, guild_id=guild_id).delete()
            messages.success(request, 'Role de niveau supprime!')

        return redirect('leveling_settings', guild_id=guild_id)

    context = {
        'guild': guild,
        'guilds': guilds,
        'config': config,
        'level_roles': level_roles,
        'top_users': top_users,
        'stats': stats,
        'xp_config': {
            'xp_per_message': 15,
            'xp_cooldown': 60,
            'level_up_base': 100,
            'level_up_factor': 1.5,
            'announce_level_up': True,
            'stack_roles': False,
        },
        'available_roles': [],
    }
    return render(request, 'core/leveling_settings.html', context)


@login_required
def users_list(request, guild_id):
    """List of users with stats."""
    guilds = get_user_guilds(request)
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "Vous n'avez pas accès à ce serveur.")
        return redirect('dashboard')

    users = BotUser.objects.filter(guild_id=guild_id).order_by('-total_xp')

    context = {
        'guild': guild,
        'guilds': guilds,
        'users': users,
    }
    return render(request, 'core/users_list.html', context)


@login_required
def infractions_list(request, guild_id):
    """List of profanity infractions."""
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta

    guilds = get_user_guilds(request)
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "Vous n'avez pas acces a ce serveur.")
        return redirect('dashboard')

    infractions = ProfanityInfraction.objects.filter(
        guild_id=guild_id
    ).order_by('-created_at')[:100]

    top_offenders = UserProfanityStats.objects.filter(
        guild_id=guild_id
    ).order_by('-total_infractions')[:10]

    # Compute stats
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    total_infractions = ProfanityInfraction.objects.filter(guild_id=guild_id).count()
    today_count = ProfanityInfraction.objects.filter(
        guild_id=guild_id, created_at__gte=today_start
    ).count()
    week_count = ProfanityInfraction.objects.filter(
        guild_id=guild_id, created_at__gte=week_start
    ).count()
    unique_users = UserProfanityStats.objects.filter(
        guild_id=guild_id, total_infractions__gt=0
    ).count()

    stats = {
        'total_infractions': total_infractions,
        'today': today_count,
        'this_week': week_count,
        'unique_users': unique_users,
    }

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'reset_user_infractions':
            user_id = request.POST.get('user_id')
            if user_id:
                UserProfanityStats.objects.filter(
                    user_id=user_id,
                    guild_id=guild_id
                ).update(
                    total_infractions=0,
                    warnings_count=0,
                    mutes_count=0,
                    kicks_count=0,
                    is_banned=0
                )
                messages.success(request, 'Stats reinitialisees!')

        elif action == 'delete_infraction':
            infraction_id = request.POST.get('infraction_id')
            ProfanityInfraction.objects.filter(id=infraction_id, guild_id=guild_id).delete()
            messages.success(request, 'Infraction supprimee!')

        elif action == 'clear_all':
            ProfanityInfraction.objects.filter(guild_id=guild_id).delete()
            UserProfanityStats.objects.filter(guild_id=guild_id).update(
                total_infractions=0, warnings_count=0, mutes_count=0, kicks_count=0, is_banned=0
            )
            messages.success(request, 'Toutes les infractions ont ete supprimees!')

        return redirect('infractions_list', guild_id=guild_id)

    context = {
        'guild': guild,
        'guilds': guilds,
        'infractions': infractions,
        'top_offenders': top_offenders,
        'stats': stats,
    }
    return render(request, 'core/infractions_list.html', context)


# API Views
@login_required
@require_POST
def api_toggle_module(request, guild_id):
    """Toggle a module on/off."""
    guilds = get_user_guilds(request)
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        return JsonResponse({'error': 'Access denied'}, status=403)

    module = request.POST.get('module')
    enabled = request.POST.get('enabled') == 'true'

    try:
        config = GuildConfig.objects.get(guild_id=guild_id)

        if module == 'auto_mod':
            config.auto_mod_enabled = 1 if enabled else 0
        elif module == 'leveling':
            config.leveling_enabled = 1 if enabled else 0

        config.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
