"""
Django REST Framework views (viewsets and API views) for the Discord Bot API.

This module provides the ``/api/v1/`` endpoints that power programmatic
access to the bot's data.  Every endpoint that operates on a specific guild
is protected by the custom :class:`IsGuildAdmin` permission, which verifies
(via the Discord API) that the authenticated user holds **Administrator** or
**Manage Server** permissions in the target guild.

Viewsets / views:
    IsGuildAdmin         -- Custom DRF permission class.
    GuildViewSet         -- List, retrieve, and update guild configs + stats.
    UserViewSet          -- CRUD for per-user-per-guild profiles.
    WarningViewSet       -- Create, list, and delete moderation warnings.
    ProfanityConfigView  -- Get / patch profanity filter settings.
    BannedWordViewSet    -- CRUD for per-guild banned words.
    InfractionViewSet    -- Read-only listing of profanity infractions.
    LeaderboardView      -- XP leaderboard for a guild.
    LevelRoleViewSet     -- CRUD for level-role reward mappings.
    HealthCheckView      -- Unauthenticated health-check endpoint.

All viewsets are registered in ``api/urls.py`` and mounted under
``/api/v1/``.
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Avg, Max, Count
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
import requests

from core.models import (
    GuildConfig, BotUser, Warning, BannedWord,
    ProfanityConfig, ProfanityInfraction, UserProfanityStats, LevelRole
)
from .serializers import (
    GuildConfigSerializer, BotUserSerializer, BotUserUpdateSerializer,
    WarningSerializer, WarningCreateSerializer, BannedWordSerializer,
    BannedWordCreateSerializer, ProfanityConfigSerializer,
    ProfanityInfractionSerializer, UserProfanityStatsSerializer,
    LevelRoleSerializer, LevelRoleCreateSerializer, LeaderboardEntrySerializer,
    GuildStatsSerializer, GuildDetailSerializer, GuildListSerializer
)


class IsGuildAdmin(permissions.BasePermission):
    """DRF permission that verifies the user is an admin of the target guild.

    For every API request that includes a ``guild_id`` URL parameter, this
    permission class calls the Discord ``/users/@me/guilds`` endpoint using
    the stored OAuth2 token and checks that the user has **Administrator**
    (``0x8``) or **Manage Server** (``0x20``) permissions in the specified
    guild.

    If no ``guild_id`` is present in the URL (e.g. the top-level guild
    list), the permission is granted automatically (the view itself is
    responsible for filtering data the user may see).

    Note:
        Each permission check makes a live call to the Discord API.  In a
        high-traffic deployment this should be cached (e.g. with
        ``django.core.cache``) to avoid rate-limiting by Discord.
    """

    def has_permission(self, request, view):
        """Determine whether the request should be permitted.

        Args:
            request: The incoming DRF ``Request``.
            view: The view or viewset instance handling the request.

        Returns:
            bool: ``True`` if the user is authenticated **and** holds admin
            or manage-server permissions in the guild identified by
            ``view.kwargs['guild_id']``.  Returns ``True`` unconditionally
            if there is no ``guild_id`` in the URL.  Returns ``False`` on
            any authentication or API error.
        """
        if not request.user.is_authenticated:
            return False

        guild_id = view.kwargs.get('guild_id')
        if not guild_id:
            # No guild scope -- let the view handle its own filtering
            return True

        # Retrieve the user's Discord OAuth2 token stored by django-allauth
        try:
            social_account = request.user.socialaccount_set.filter(provider='discord').first()
            if not social_account:
                return False

            token = social_account.socialtoken_set.first()
            if not token:
                return False

            headers = {'Authorization': f'Bearer {token.token}'}
            response = requests.get(
                f'{settings.DISCORD_API_BASE}/users/@me/guilds',
                headers=headers,
                timeout=10
            )

            if response.status_code != 200:
                return False

            # Search for the target guild and verify admin/manage permissions
            for guild in response.json():
                if str(guild['id']) == str(guild_id):
                    permissions_value = int(guild.get('permissions', 0))
                    # Bitwise check: Administrator (0x8) or Manage Server (0x20)
                    return bool(permissions_value & 0x8 or permissions_value & 0x20)

            # User is not a member of the requested guild
            return False
        except Exception:
            return False


@extend_schema_view(
    list=extend_schema(
        summary="List user's guilds",
        description="Returns guilds where the authenticated user has admin permissions.",
        responses={200: GuildListSerializer(many=True)}
    ),
    retrieve=extend_schema(
        summary="Get guild details",
        description="Returns detailed information about a specific guild.",
        responses={200: GuildDetailSerializer}
    ),
    partial_update=extend_schema(
        summary="Update guild configuration",
        description="Update configuration settings for a guild.",
        request=GuildConfigSerializer,
        responses={200: GuildConfigSerializer}
    )
)
class GuildViewSet(viewsets.ViewSet):
    """ViewSet for top-level guild operations (list, retrieve, update, stats).

    Unlike the other viewsets in this module, ``GuildViewSet`` extends the
    bare ``ViewSet`` (not ``ModelViewSet``) because guild data is a hybrid
    of Discord API responses and local :class:`~core.models.GuildConfig`
    rows -- there is no single Django model that represents a "guild".

    Endpoints:
        GET    /api/v1/guilds/           -- List the user's admin guilds.
        GET    /api/v1/guilds/{id}/      -- Guild detail (config + stats).
        PATCH  /api/v1/guilds/{id}/      -- Update guild config fields.
        GET    /api/v1/guilds/{id}/stats/ -- Aggregated statistics only.
    """

    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]

    def list(self, request):
        """Return a list of guilds where the user has admin permissions.

        Each entry includes the guild name, icon, approximate member count,
        and a ``bot_present`` flag indicating whether the bot has a config
        row for that guild.

        Args:
            request: The incoming DRF ``Request``.

        Returns:
            Response: Serialized list of :class:`~api.serializers.GuildListSerializer`.
        """
        guilds = self._get_user_guilds(request)
        serializer = GuildListSerializer(guilds, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """Return detailed information for a single guild.

        Combines Discord guild metadata, the bot's
        :class:`~core.models.GuildConfig`, and aggregated statistics into
        a single response.  If no ``GuildConfig`` row exists yet, one is
        created with default values.

        Args:
            request: The incoming DRF ``Request``.
            pk: The guild's Discord snowflake ID (from the URL).

        Returns:
            Response: Serialized :class:`~api.serializers.GuildDetailSerializer`,
            or 404 if the guild is not found or the user lacks access.
        """
        guilds = self._get_user_guilds(request)
        guild = next((g for g in guilds if str(g['id']) == str(pk)), None)

        if not guild:
            return Response(
                {'error': 'Guild not found or access denied'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Auto-create a config row with defaults if one does not exist
        try:
            config = GuildConfig.objects.get(guild_id=pk)
        except GuildConfig.DoesNotExist:
            config = GuildConfig.objects.create(guild_id=pk)

        stats = self._get_guild_stats(pk)

        data = {
            'id': str(pk),
            'name': guild.get('name', ''),
            'icon': guild.get('icon'),
            'config': GuildConfigSerializer(config).data,
            'stats': stats
        }

        return Response(data)

    def partial_update(self, request, pk=None):
        """Update selected fields of the guild configuration (PATCH).

        Accepts any subset of the fields defined in
        :class:`~api.serializers.GuildConfigSerializer`.  If no config row
        exists, one is created before applying the update.

        Args:
            request: The incoming DRF ``Request`` containing the fields to
                update.
            pk: The guild's Discord snowflake ID.

        Returns:
            Response: The updated config on success (200), or validation
            errors on failure (400).
        """
        try:
            config = GuildConfig.objects.get(guild_id=pk)
        except GuildConfig.DoesNotExist:
            config = GuildConfig.objects.create(guild_id=pk)

        serializer = GuildConfigSerializer(config, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Get guild statistics",
        responses={200: GuildStatsSerializer}
    )
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Return aggregated statistics for the guild.

        Args:
            request: The incoming DRF ``Request``.
            pk: The guild's Discord snowflake ID.

        Returns:
            Response: Serialized :class:`~api.serializers.GuildStatsSerializer`.
        """
        stats = self._get_guild_stats(pk)
        return Response(stats)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_user_guilds(self, request):
        """Fetch the user's guilds from the Discord API, filtered for admin access.

        Mirrors the logic in :func:`core.views.get_user_guilds` but also
        injects ``member_count`` for the list serializer.

        Args:
            request: The incoming DRF ``Request``.

        Returns:
            list[dict]: Augmented guild dictionaries, or an empty list on
            any error.
        """
        try:
            social_account = request.user.socialaccount_set.filter(provider='discord').first()
            if not social_account:
                return []

            token = social_account.socialtoken_set.first()
            if not token:
                return []

            headers = {'Authorization': f'Bearer {token.token}'}
            response = requests.get(
                f'{settings.DISCORD_API_BASE}/users/@me/guilds',
                headers=headers,
                timeout=10
            )

            if response.status_code != 200:
                return []

            admin_guilds = []
            for guild in response.json():
                permissions_value = int(guild.get('permissions', 0))
                # Bitwise check: Administrator (0x8) or Manage Server (0x20)
                if permissions_value & 0x8 or permissions_value & 0x20:
                    config = GuildConfig.objects.filter(guild_id=int(guild['id'])).first()
                    guild['bot_present'] = config is not None
                    guild['member_count'] = guild.get('approximate_member_count', 0)
                    admin_guilds.append(guild)

            return admin_guilds
        except Exception:
            return []

    def _get_guild_stats(self, guild_id):
        """Calculate aggregated statistics for a guild.

        Performs a single aggregate query for user/XP/level/message counts,
        plus individual count queries for moderation, activity, and
        infraction data.

        Args:
            guild_id: Discord guild snowflake ID.

        Returns:
            dict: A dictionary matching the structure expected by
            :class:`~api.serializers.GuildStatsSerializer` with keys
            ``users``, ``messages``, ``moderation``, and ``leveling``.
        """
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())

        # Single aggregate query for the bulk of user-related stats
        user_stats = BotUser.objects.filter(guild_id=guild_id).aggregate(
            total=Count('user_id'),
            total_xp=Sum('total_xp'),
            avg_level=Avg('level'),
            max_level=Max('level'),
            total_messages=Sum('messages_count')
        )

        return {
            'users': {
                'total': user_stats['total'] or 0,
                'active_today': BotUser.objects.filter(
                    guild_id=guild_id,
                    last_message__gte=today_start
                ).count(),
                # Guarded attribute check -- ``joined_at`` may not exist on
                # all BotUser schema versions.
                'new_this_week': BotUser.objects.filter(
                    guild_id=guild_id,
                    joined_at__gte=week_start
                ).count() if hasattr(BotUser, 'joined_at') else 0
            },
            'messages': {
                'total': user_stats['total_messages'] or 0,
                'today': 0  # Would need per-message tracking (not yet implemented)
            },
            'moderation': {
                'warnings': Warning.objects.filter(guild_id=guild_id).count(),
                'infractions': ProfanityInfraction.objects.filter(guild_id=guild_id).count(),
                'bans': UserProfanityStats.objects.filter(guild_id=guild_id, is_banned=1).count()
            },
            'leveling': {
                'total_xp': user_stats['total_xp'] or 0,
                'average_level': round(user_stats['avg_level'] or 0, 1),
                'max_level': user_stats['max_level'] or 0
            }
        }


@extend_schema_view(
    list=extend_schema(
        summary="List guild users",
        parameters=[
            OpenApiParameter('ordering', str, description='Order by field (-total_xp, level, etc.)'),
        ]
    ),
    retrieve=extend_schema(summary="Get user details"),
    partial_update=extend_schema(summary="Update user data", request=BotUserUpdateSerializer)
)
class UserViewSet(viewsets.ModelViewSet):
    """ModelViewSet for per-user-per-guild profiles.

    Provides full CRUD on :class:`~core.models.BotUser` rows scoped to a
    specific guild.  The queryset is filtered by the ``guild_id`` URL
    parameter, and individual users are looked up by ``user_id`` (Discord
    snowflake) rather than the default ``pk``.

    Endpoints (all under ``/api/v1/guilds/{guild_id}/users/``):
        GET    /           -- List all users (ordered by total_xp descending).
        GET    /{user_id}/ -- Retrieve a specific user.
        PATCH  /{user_id}/ -- Admin-update level, xp, total_xp, or balance.
    """

    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = BotUserSerializer
    # Look up users by their Discord snowflake ID instead of Django PK
    lookup_field = 'user_id'

    def get_queryset(self):
        """Return users belonging to the guild specified in the URL.

        Returns:
            QuerySet: :class:`~core.models.BotUser` rows for the guild,
            ordered by ``total_xp`` descending (leaderboard order).
        """
        guild_id = self.kwargs.get('guild_id')
        return BotUser.objects.filter(guild_id=guild_id).order_by('-total_xp')

    def get_serializer_class(self):
        """Choose the appropriate serializer based on the action.

        Returns:
            type: :class:`~api.serializers.BotUserUpdateSerializer` for
            update/partial_update actions;
            :class:`~api.serializers.BotUserSerializer` for everything else.
        """
        if self.action in ['update', 'partial_update']:
            return BotUserUpdateSerializer
        return BotUserSerializer


@extend_schema_view(
    list=extend_schema(summary="List guild warnings"),
    create=extend_schema(summary="Create a warning", request=WarningCreateSerializer),
    destroy=extend_schema(summary="Delete a warning")
)
class WarningViewSet(viewsets.ModelViewSet):
    """ModelViewSet for moderation warnings within a guild.

    Supports listing, creating, and deleting warnings.  Update (PUT/PATCH)
    is intentionally disabled -- warnings are immutable once issued.

    The ``?user_id=`` query parameter can be used on the list endpoint to
    filter warnings for a specific user.

    Endpoints (all under ``/api/v1/guilds/{guild_id}/warnings/``):
        GET    /           -- List all warnings (newest first).
        POST   /           -- Issue a new warning.
        DELETE /{id}/      -- Delete a specific warning.
    """

    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = WarningSerializer
    # Restrict allowed HTTP methods (no PUT/PATCH -- warnings are immutable)
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        """Return warnings for the guild, optionally filtered by user_id.

        Returns:
            QuerySet: :class:`~core.models.Warning` rows ordered by
            ``created_at`` descending.
        """
        guild_id = self.kwargs.get('guild_id')
        queryset = Warning.objects.filter(guild_id=guild_id).order_by('-created_at')

        # Optional query-param filter for a specific user
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        return queryset

    def get_serializer_class(self):
        """Use a minimal serializer for creation (user_id + reason only).

        Returns:
            type: :class:`~api.serializers.WarningCreateSerializer` for
            the ``create`` action;
            :class:`~api.serializers.WarningSerializer` otherwise.
        """
        if self.action == 'create':
            return WarningCreateSerializer
        return WarningSerializer

    def perform_create(self, serializer):
        """Create a warning, injecting guild_id and moderator_id automatically.

        The ``guild_id`` comes from the URL and the ``moderator_id`` is
        resolved from the authenticated user's linked Discord account.

        Args:
            serializer: The validated
                :class:`~api.serializers.WarningCreateSerializer` instance.
        """
        guild_id = self.kwargs.get('guild_id')
        # Resolve the moderator's Discord ID from their allauth social account
        social_account = self.request.user.socialaccount_set.filter(provider='discord').first()
        moderator_id = social_account.uid if social_account else 0

        Warning.objects.create(
            user_id=serializer.validated_data['user_id'],
            guild_id=guild_id,
            moderator_id=moderator_id,
            reason=serializer.validated_data.get('reason', 'No reason provided')
        )


class ProfanityConfigView(APIView):
    """API view for reading and updating a guild's profanity filter settings.

    Uses a plain ``APIView`` (instead of a viewset) because profanity config
    is a singleton per guild -- there is no list or delete operation.

    Endpoints (under ``/api/v1/guilds/{guild_id}/profanity/config/``):
        GET   -- Retrieve the current config (auto-creates with defaults if
                 missing).
        PATCH -- Partially update one or more config fields.
    """

    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]

    @extend_schema(
        summary="Get profanity config",
        responses={200: ProfanityConfigSerializer}
    )
    def get(self, request, guild_id):
        """Retrieve the profanity filter configuration for a guild.

        If no :class:`~core.models.ProfanityConfig` row exists yet, one is
        created with default thresholds.

        Args:
            request: The incoming DRF ``Request``.
            guild_id (int): Discord guild snowflake ID from the URL.

        Returns:
            Response: Serialized profanity config (200).
        """
        try:
            config = ProfanityConfig.objects.get(guild_id=guild_id)
        except ProfanityConfig.DoesNotExist:
            config = ProfanityConfig.objects.create(guild_id=guild_id)

        serializer = ProfanityConfigSerializer(config)
        return Response(serializer.data)

    @extend_schema(
        summary="Update profanity config",
        request=ProfanityConfigSerializer,
        responses={200: ProfanityConfigSerializer}
    )
    def patch(self, request, guild_id):
        """Partially update the profanity filter configuration.

        Accepts any subset of fields from
        :class:`~api.serializers.ProfanityConfigSerializer`.

        Args:
            request: The incoming DRF ``Request`` with the fields to update.
            guild_id (int): Discord guild snowflake ID from the URL.

        Returns:
            Response: The updated config (200) or validation errors (400).
        """
        try:
            config = ProfanityConfig.objects.get(guild_id=guild_id)
        except ProfanityConfig.DoesNotExist:
            config = ProfanityConfig.objects.create(guild_id=guild_id)

        serializer = ProfanityConfigSerializer(config, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    list=extend_schema(summary="List banned words"),
    create=extend_schema(summary="Add a banned word", request=BannedWordCreateSerializer),
    destroy=extend_schema(summary="Remove a banned word")
)
class BannedWordViewSet(viewsets.ModelViewSet):
    """ModelViewSet for managing banned words within a guild.

    The list endpoint returns **both** global words (``guild_id=0``) and
    server-specific words, but the delete endpoint only allows removal of
    server-specific words -- global words are protected.

    Endpoints (under ``/api/v1/guilds/{guild_id}/profanity/words/``):
        GET    /       -- List all applicable banned words (global + guild).
        POST   /       -- Add a new server-specific banned word.
        DELETE /{id}/  -- Remove a server-specific word (403 for global).
    """

    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = BannedWordSerializer
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        """Return banned words applicable to this guild.

        Includes global words (``guild_id=0``) and guild-specific words,
        ordered by severity descending then alphabetically.

        Returns:
            QuerySet: :class:`~core.models.BannedWord` rows.
        """
        guild_id = self.kwargs.get('guild_id')
        return BannedWord.objects.filter(guild_id__in=[0, guild_id]).order_by('-severity', 'word')

    def get_serializer_class(self):
        """Use a minimal serializer for creation.

        Returns:
            type: :class:`~api.serializers.BannedWordCreateSerializer` for
            the ``create`` action;
            :class:`~api.serializers.BannedWordSerializer` otherwise.
        """
        if self.action == 'create':
            return BannedWordCreateSerializer
        return BannedWordSerializer

    def perform_create(self, serializer):
        """Create a server-specific banned word, preventing duplicates.

        Uses ``get_or_create`` so that adding an already-existing word is
        a no-op rather than an error.  The word is normalized to lowercase
        and stripped of whitespace.

        Args:
            serializer: The validated
                :class:`~api.serializers.BannedWordCreateSerializer` instance.
        """
        guild_id = self.kwargs.get('guild_id')
        BannedWord.objects.get_or_create(
            word=serializer.validated_data['word'].lower().strip(),
            guild_id=guild_id,
            defaults={
                'language': serializer.validated_data.get('language', 'all'),
                'severity': serializer.validated_data.get('severity', 2)
            }
        )

    def destroy(self, request, *args, **kwargs):
        """Delete a banned word, but only if it is server-specific.

        Global words (``guild_id=0``) cannot be deleted from a single
        guild's context -- they must be managed at the global level.

        Returns:
            Response: 204 on success, 403 if the word is global.
        """
        instance = self.get_object()
        guild_id = self.kwargs.get('guild_id')

        # Only allow deleting server-specific words (not global ones)
        if instance.guild_id != int(guild_id):
            return Response(
                {'error': 'Cannot delete global banned words'},
                status=status.HTTP_403_FORBIDDEN
            )

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary="List profanity infractions",
        parameters=[
            OpenApiParameter('user_id', int, description='Filter by user ID'),
            OpenApiParameter('action_taken', str, description='Filter by action (warn, mute, kick, ban)'),
        ]
    )
)
class InfractionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for profanity infraction log entries.

    Infractions are created by the bot at runtime and should not be
    created or modified through the API -- hence ``ReadOnlyModelViewSet``.

    Supports optional query-parameter filters:
        - ``?user_id=<id>`` -- Show only infractions for a specific user.
        - ``?action_taken=<action>`` -- Filter by action type (e.g.
          ``warn``, ``mute``, ``kick``, ``ban``).

    Results are capped at 100 entries to prevent excessively large responses.

    Endpoints (under ``/api/v1/guilds/{guild_id}/profanity/infractions/``):
        GET /       -- List infractions (newest first, max 100).
        GET /{id}/  -- Retrieve a single infraction.
    """

    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = ProfanityInfractionSerializer

    def get_queryset(self):
        """Return infractions for the guild, with optional filters.

        Returns:
            QuerySet: Up to 100 :class:`~core.models.ProfanityInfraction`
            rows, ordered by ``created_at`` descending.
        """
        guild_id = self.kwargs.get('guild_id')
        queryset = ProfanityInfraction.objects.filter(guild_id=guild_id).order_by('-created_at')

        # Optional filters via query parameters
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        action_taken = self.request.query_params.get('action_taken')
        if action_taken:
            queryset = queryset.filter(action_taken=action_taken)

        # Hard cap at 100 rows to avoid oversized API responses
        return queryset[:100]


class LeaderboardView(APIView):
    """API view returning the XP leaderboard for a guild.

    Returns a ranked list of users ordered by ``total_xp`` descending.
    The ``?limit=`` query parameter controls how many entries are returned
    (default 10, maximum 100).

    Endpoint: ``GET /api/v1/guilds/{guild_id}/leaderboard/``
    """

    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]

    @extend_schema(
        summary="Get guild leaderboard",
        parameters=[
            OpenApiParameter('limit', int, description='Number of entries (default 10, max 100)'),
        ],
        responses={200: LeaderboardEntrySerializer(many=True)}
    )
    def get(self, request, guild_id):
        """Return the top users by XP for a guild.

        Args:
            request: The incoming DRF ``Request``.
            guild_id (int): Discord guild snowflake ID from the URL.

        Returns:
            Response: A list of
            :class:`~api.serializers.LeaderboardEntrySerializer` entries.
        """
        # Clamp the requested limit to [1, 100]
        limit = min(int(request.query_params.get('limit', 10)), 100)

        users = BotUser.objects.filter(guild_id=guild_id).order_by('-total_xp')[:limit]

        # Build ranked entries with 1-based rank
        data = []
        for rank, user in enumerate(users, 1):
            data.append({
                'rank': rank,
                'user_id': user.user_id,
                'username': user.username or f'User {user.user_id}',
                'level': user.level,
                'total_xp': user.total_xp
            })

        serializer = LeaderboardEntrySerializer(data, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(summary="List level roles"),
    create=extend_schema(summary="Create a level role", request=LevelRoleCreateSerializer),
    destroy=extend_schema(summary="Delete a level role")
)
class LevelRoleViewSet(viewsets.ModelViewSet):
    """ModelViewSet for managing level-role reward mappings within a guild.

    Each mapping says "when a user reaches level X, assign Discord role Y".
    Creating a mapping for an already-existing level will **update** the
    role rather than creating a duplicate (via ``update_or_create``).

    Endpoints (under ``/api/v1/guilds/{guild_id}/level-roles/``):
        GET    /       -- List all level-role mappings (ordered by level).
        POST   /       -- Create or update a level-role mapping.
        DELETE /{id}/  -- Remove a level-role mapping.
    """

    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = LevelRoleSerializer
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        """Return level-role mappings for the guild, ordered by level ascending.

        Returns:
            QuerySet: :class:`~core.models.LevelRole` rows.
        """
        guild_id = self.kwargs.get('guild_id')
        return LevelRole.objects.filter(guild_id=guild_id).order_by('level')

    def get_serializer_class(self):
        """Use a minimal serializer for creation (level + role_id only).

        Returns:
            type: :class:`~api.serializers.LevelRoleCreateSerializer` for
            the ``create`` action;
            :class:`~api.serializers.LevelRoleSerializer` otherwise.
        """
        if self.action == 'create':
            return LevelRoleCreateSerializer
        return LevelRoleSerializer

    def perform_create(self, serializer):
        """Create or update a level-role mapping for the guild.

        Uses ``update_or_create`` keyed on ``(guild_id, level)`` so that
        re-posting the same level simply reassigns the role without
        creating a duplicate row.

        Args:
            serializer: The validated
                :class:`~api.serializers.LevelRoleCreateSerializer` instance.
        """
        guild_id = self.kwargs.get('guild_id')
        LevelRole.objects.update_or_create(
            guild_id=guild_id,
            level=serializer.validated_data['level'],
            defaults={'role_id': serializer.validated_data['role_id']}
        )


class HealthCheckView(APIView):
    """Unauthenticated health-check endpoint for monitoring and load balancers.

    Returns a simple ``{"status": "ok"}`` response to confirm that the
    Django application and database connection are operational.

    Endpoint: ``GET /api/health/``
    """

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Health check",
        description="Returns OK if the API is healthy.",
        responses={200: {'type': 'object', 'properties': {'status': {'type': 'string'}}}}
    )
    def get(self, request):
        """Return a minimal health status response.

        Args:
            request: The incoming DRF ``Request`` (no authentication
                required).

        Returns:
            Response: ``{"status": "ok"}`` with HTTP 200.
        """
        return Response({'status': 'ok'})
