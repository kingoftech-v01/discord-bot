"""
Server-rendered Django views for the Discord Bot web dashboard.

This module powers the traditional (non-API) web interface that guild
administrators interact with after logging in via Discord OAuth2.  Each view
checks that the authenticated user has administrator or "Manage Server"
permissions in the target guild before displaying or modifying data.

View hierarchy:
    home                -- Public landing page (no auth required).
    dashboard           -- Server-selection page listing the user's guilds.
    server_dashboard    -- Overview page for a single guild (stats, top users).
    server_settings     -- General guild settings (prefix, messages, toggles).
    moderation_settings -- Profanity filter thresholds and banned-word management.
    leveling_settings   -- Leveling system configuration and level-role rewards.
    users_list          -- Paginated list of tracked users with XP / level info.
    infractions_list    -- Profanity infraction log with top-offender sidebar.
    api_toggle_module   -- AJAX endpoint to toggle individual modules on/off.

Helper:
    get_user_guilds     -- Fetches the user's Discord guilds via the Discord API
                           and filters for admin/manage-server permissions.

Security notes:
    - Every view that accesses guild data first calls :func:`get_user_guilds` to
      verify the caller actually has Discord-level admin permissions.  This
      prevents horizontal privilege escalation (accessing a guild you are not
      admin of).
    - ``api_toggle_module`` intentionally catches all exceptions with a bare
      ``except`` to avoid leaking internal error details to the HTTP client.
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
    """Fetch the authenticated user's Discord guilds and filter for admin access.

    Uses the stored Discord OAuth2 access token to call the Discord
    ``/users/@me/guilds`` endpoint, then filters the results to only include
    guilds where the user holds the **Administrator** (``0x8``) or
    **Manage Server** (``0x20``) permission.

    For each qualifying guild, a ``bot_present`` boolean and a ``config``
    reference (:class:`~core.models.GuildConfig` or ``None``) are injected
    into the guild dictionary so templates can show whether the bot has been
    set up for that server.

    Args:
        request: The current Django ``HttpRequest``.  The user must be
            authenticated and must have a linked Discord social account
            with a valid access token.

    Returns:
        list[dict]: A list of guild dictionaries (as returned by the Discord
        API) augmented with ``bot_present`` (bool) and ``config``
        (GuildConfig | None) keys.  Returns an empty list on any error
        (unauthenticated user, missing token, Discord API failure, etc.).
    """
    if not request.user.is_authenticated:
        return []

    try:
        # Retrieve the Discord social-account record managed by django-allauth
        social_account = request.user.socialaccount_set.filter(provider='discord').first()
        if not social_account:
            return []

        # The OAuth2 access token stored by allauth when the user logged in
        token = social_account.socialtoken_set.first()
        if not token:
            return []

        # Call the Discord REST API to list guilds the user belongs to
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
            # Bitwise check: Administrator (0x8) or Manage Server (0x20)
            if permissions & 0x8 or permissions & 0x20:
                # Determine whether the bot is present by checking for a
                # GuildConfig row (created when the bot joins a server).
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
    """Render the public landing / home page.

    This is the only view that does not require authentication.  It
    typically shows a marketing-style overview of the bot's features
    and a "Login with Discord" button.

    Args:
        request: The current Django ``HttpRequest``.

    Returns:
        HttpResponse: The rendered ``core/home.html`` template.
    """
    return render(request, 'core/home.html')


@login_required
def dashboard(request):
    """Render the server-selection page (main dashboard landing).

    Lists every Discord guild where the authenticated user has admin or
    manage-server permissions.  Each guild card indicates whether the bot
    is present so the user knows which servers they can manage.

    Args:
        request: The current Django ``HttpRequest`` (user must be logged in).

    Returns:
        HttpResponse: The rendered ``core/dashboard.html`` template with
        a ``guilds`` context variable.
    """
    guilds = get_user_guilds(request)
    return render(request, 'core/dashboard.html', {'guilds': guilds})


@login_required
def server_dashboard(request, guild_id):
    """Render the overview dashboard for a single guild.

    Displays key statistics (user count, warning count, banned-word count),
    a "top 5 users by XP" leaderboard, and the 10 most recent profanity
    infractions.  If no :class:`~core.models.GuildConfig` row exists yet,
    one is created with default values.

    Args:
        request: The current Django ``HttpRequest`` (user must be logged in).
        guild_id (int): Discord guild snowflake ID from the URL.

    Returns:
        HttpResponse: The rendered ``core/server_dashboard.html`` template,
        or a redirect to the dashboard page with an error message if the
        user does not have admin access to the specified guild.
    """
    guilds = get_user_guilds(request)
    # Verify the caller actually has admin permissions on this guild
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "Vous n'avez pas accès à ce serveur.")
        return redirect('dashboard')

    # Ensure a config row exists (auto-create with defaults if missing)
    try:
        config = GuildConfig.objects.get(guild_id=guild_id)
    except GuildConfig.DoesNotExist:
        config = GuildConfig.objects.create(guild_id=guild_id)

    # Aggregate high-level statistics for the overview cards
    users_count = BotUser.objects.filter(guild_id=guild_id).count()
    warnings_count = Warning.objects.filter(guild_id=guild_id).count()
    # Include both global (guild_id=0) and server-specific banned words
    banned_words_count = BannedWord.objects.filter(guild_id__in=[0, guild_id]).count()

    # Get top users by XP for the mini-leaderboard widget
    top_users = BotUser.objects.filter(guild_id=guild_id).order_by('-total_xp')[:5]

    # Get the most recent profanity infractions for the activity feed
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
    """Display and handle the general settings form for a guild.

    On **GET**, renders the settings form pre-populated with the current
    :class:`~core.models.GuildConfig` values.  On **POST**, validates and
    saves the submitted values, then redirects back to the same page with
    a success message (POST-Redirect-GET pattern).

    Editable fields:
        - Command prefix (truncated to 10 characters).
        - Auto-moderation toggle.
        - Leveling system toggle.
        - Welcome, goodbye, and level-up message templates.

    Args:
        request: The current Django ``HttpRequest`` (user must be logged in).
        guild_id (int): Discord guild snowflake ID from the URL.

    Returns:
        HttpResponse: The rendered ``core/server_settings.html`` form on GET,
        or a redirect back to the same URL on successful POST.  Redirects
        to the dashboard with an error if the user lacks admin access.
    """
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
        # Truncate prefix to the max column length to prevent DB errors
        config.prefix = request.POST.get('prefix', '!')[:10]
        # Checkbox fields: present in POST data means checked (truthy)
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
    """Display and handle the moderation / profanity-filter settings page.

    This view combines three different POST actions on the same page:

    1. ``update_config`` -- Update profanity filter thresholds and toggles.
    2. ``add_word`` -- Add a new server-specific banned word.
    3. ``delete_word`` -- Remove a server-specific banned word (global words
       cannot be deleted from here).

    The template displays both **global** (``guild_id=0``) and
    **server-specific** banned words, ordered by severity descending then
    alphabetically.

    Args:
        request: The current Django ``HttpRequest`` (user must be logged in).
        guild_id (int): Discord guild snowflake ID from the URL.

    Returns:
        HttpResponse: The rendered ``core/moderation_settings.html`` template
        on GET, or a redirect back to the same URL on POST.  Redirects to
        the dashboard with an error if the user lacks admin access.
    """
    guilds = get_user_guilds(request)
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "Vous n'avez pas accès à ce serveur.")
        return redirect('dashboard')

    # Ensure a profanity config row exists for this guild
    try:
        profanity_config = ProfanityConfig.objects.get(guild_id=guild_id)
    except ProfanityConfig.DoesNotExist:
        profanity_config = ProfanityConfig.objects.create(guild_id=guild_id)

    # Combine global (guild_id=0) and server-specific banned words
    banned_words = BannedWord.objects.filter(guild_id__in=[0, guild_id]).order_by('-severity', 'word')

    # Server-specific words only (used by the template to show a "delete"
    # button -- global words should not be deletable from a single server).
    server_words = BannedWord.objects.filter(guild_id=guild_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_config':
            profanity_config.enabled = 1 if request.POST.get('enabled') else 0
            profanity_config.warn_threshold = int(request.POST.get('warn_threshold', 3))
            profanity_config.mute_threshold = int(request.POST.get('mute_threshold', 5))
            profanity_config.kick_threshold = int(request.POST.get('kick_threshold', 8))
            profanity_config.ban_threshold = int(request.POST.get('ban_threshold', 10))
            # The form sends minutes; convert to seconds for storage
            profanity_config.mute_duration = int(request.POST.get('mute_duration', 60)) * 60
            profanity_config.delete_message = 1 if request.POST.get('delete_message') else 0
            profanity_config.dm_user = 1 if request.POST.get('dm_user') else 0
            profanity_config.save()
            messages.success(request, 'Configuration de modération sauvegardée!')

        elif action == 'add_word':
            # Normalize to lowercase to ensure case-insensitive matching
            word = request.POST.get('word', '').strip().lower()
            language = request.POST.get('language', 'all')
            severity = int(request.POST.get('severity', 2))
            if word:
                # get_or_create prevents duplicate entries for the same word
                BannedWord.objects.get_or_create(
                    word=word,
                    guild_id=guild_id,
                    defaults={'language': language, 'severity': severity}
                )
                messages.success(request, f'Mot "{word}" ajouté!')

        elif action == 'delete_word':
            word_id = request.POST.get('word_id')
            # Only delete words that belong to this guild (not global words)
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
    """Display and handle the leveling system settings page.

    Provides three POST actions:

    1. ``toggle_leveling`` -- Enable or disable the leveling system.
    2. ``add_level_role`` -- Create or update a role reward for a given
       level (uses ``update_or_create`` so re-submitting the same level
       simply updates the role).
    3. ``delete_level_role`` -- Remove a level-role mapping.

    The page also displays aggregated statistics (total users, total XP,
    average level, max level) and a mini leaderboard of the top 5 users.

    A static ``xp_config`` dictionary is passed to the template for display
    purposes -- these values are hardcoded in the bot and are shown here
    so admins understand the XP curve.

    Args:
        request: The current Django ``HttpRequest`` (user must be logged in).
        guild_id (int): Discord guild snowflake ID from the URL.

    Returns:
        HttpResponse: The rendered ``core/leveling_settings.html`` template
        on GET, or a redirect back to the same URL on POST.  Redirects to
        the dashboard with an error if the user lacks admin access.
    """
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

    # Existing level-role rewards, ordered lowest level first
    level_roles = LevelRole.objects.filter(guild_id=guild_id).order_by('level')
    # Top 5 users by total XP for the mini-leaderboard widget
    top_users = BotUser.objects.filter(guild_id=guild_id).order_by('-total_xp')[:5]

    # Compute aggregated leveling statistics in a single query
    stats_qs = BotUser.objects.filter(guild_id=guild_id).aggregate(
        total_users=Count('user_id'),
        total_xp=Sum('total_xp'),
        avg_level=Avg('level'),
        max_level=Max('level')
    )
    # Default to 0 if no users exist yet (aggregate returns None)
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
                # update_or_create allows reassigning the role for an
                # existing level without requiring a separate delete step.
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
        # Static XP curve parameters (hardcoded in the bot) shown for
        # informational purposes so admins understand the leveling curve.
        'xp_config': {
            'xp_per_message': 15,
            'xp_cooldown': 60,
            'level_up_base': 100,
            'level_up_factor': 1.5,
            'announce_level_up': True,
            'stack_roles': False,
        },
        # Placeholder -- would be populated from the Discord API in a
        # future iteration to let admins pick roles from a dropdown.
        'available_roles': [],
    }
    return render(request, 'core/leveling_settings.html', context)


@login_required
def users_list(request, guild_id):
    """Display a list of all tracked users in a guild, sorted by XP.

    Shows every :class:`~core.models.BotUser` row for the given guild,
    ordered from highest ``total_xp`` to lowest.  This gives admins a
    full leaderboard view with level, XP, and message-count data.

    Args:
        request: The current Django ``HttpRequest`` (user must be logged in).
        guild_id (int): Discord guild snowflake ID from the URL.

    Returns:
        HttpResponse: The rendered ``core/users_list.html`` template, or a
        redirect to the dashboard with an error if the user lacks access.
    """
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
    """Display the profanity infraction log and handle moderation actions.

    Shows the 100 most recent :class:`~core.models.ProfanityInfraction`
    records, a "top 10 offenders" sidebar, and summary statistics (total,
    today, this week, unique offenders).

    POST actions:

    1. ``reset_user_infractions`` -- Zero-out all profanity stats for a
       specific user (warnings, mutes, kicks, ban flag).
    2. ``delete_infraction`` -- Delete a single infraction record.
    3. ``clear_all`` -- **Destructive**: delete every infraction for this
       guild and reset all user profanity stats to zero.

    Args:
        request: The current Django ``HttpRequest`` (user must be logged in).
        guild_id (int): Discord guild snowflake ID from the URL.

    Returns:
        HttpResponse: The rendered ``core/infractions_list.html`` template
        on GET, or a redirect back to the same URL on POST.  Redirects to
        the dashboard with an error if the user lacks admin access.
    """
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta

    guilds = get_user_guilds(request)
    guild = next((g for g in guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "Vous n'avez pas acces a ce serveur.")
        return redirect('dashboard')

    # Latest 100 infractions, newest first
    infractions = ProfanityInfraction.objects.filter(
        guild_id=guild_id
    ).order_by('-created_at')[:100]

    # Top 10 users with the most infractions (for the sidebar widget)
    top_offenders = UserProfanityStats.objects.filter(
        guild_id=guild_id
    ).order_by('-total_infractions')[:10]

    # ---- Summary statistics ------------------------------------------------
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Monday of the current week (weekday() returns 0 for Monday)
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

    # ---- POST action handling -----------------------------------------------
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'reset_user_infractions':
            # Reset a single user's profanity record back to a clean slate
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
            # Remove a single infraction log entry
            infraction_id = request.POST.get('infraction_id')
            ProfanityInfraction.objects.filter(id=infraction_id, guild_id=guild_id).delete()
            messages.success(request, 'Infraction supprimee!')

        elif action == 'clear_all':
            # Nuclear option: wipe all infractions and reset every user's stats
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


# ---------------------------------------------------------------------------
# Lightweight AJAX endpoint (used by JavaScript toggle switches on the
# dashboard, separate from the full REST API in the ``api`` app).
# ---------------------------------------------------------------------------


@login_required
@require_POST
def api_toggle_module(request, guild_id):
    """AJAX endpoint to toggle a bot module on or off for a guild.

    Called by JavaScript toggle switches on the server dashboard.  Expects
    two POST parameters:

    - ``module`` (str): The module identifier -- currently ``'auto_mod'``
      or ``'leveling'``.
    - ``enabled`` (str): ``'true'`` to enable, anything else to disable.

    Args:
        request: The current Django ``HttpRequest`` (user must be logged in).
            Must be a POST request (enforced by ``@require_POST``).
        guild_id (int): Discord guild snowflake ID from the URL.

    Returns:
        JsonResponse: ``{"success": true}`` on success, or an error object
        with an appropriate HTTP status code (403 for access denied, 500
        for internal errors).

    Security:
        The bare ``except Exception`` clause is intentional -- it prevents
        internal error details (stack traces, DB errors) from leaking to
        the HTTP client.  The generic message ``"An internal error occurred"``
        is returned instead.
    """
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
    except Exception:
        # SECURITY: Do not expose internal error details to the client.
        return JsonResponse({'error': 'An internal error occurred'}, status=500)
