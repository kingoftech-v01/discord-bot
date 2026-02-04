"""
API Views for Discord Bot Dashboard.
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
    """Check if user has admin permissions for the guild."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        guild_id = view.kwargs.get('guild_id')
        if not guild_id:
            return True

        # Get user's guilds from Discord
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

            for guild in response.json():
                if str(guild['id']) == str(guild_id):
                    permissions_value = int(guild.get('permissions', 0))
                    # Administrator (0x8) or Manage Server (0x20)
                    return bool(permissions_value & 0x8 or permissions_value & 0x20)

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
    """ViewSet for guild operations."""
    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]

    def list(self, request):
        """List guilds where user has admin permissions."""
        guilds = self._get_user_guilds(request)
        serializer = GuildListSerializer(guilds, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """Get guild details with stats."""
        guilds = self._get_user_guilds(request)
        guild = next((g for g in guilds if str(g['id']) == str(pk)), None)

        if not guild:
            return Response(
                {'error': 'Guild not found or access denied'},
                status=status.HTTP_404_NOT_FOUND
            )

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
        """Update guild configuration."""
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
        """Get detailed guild statistics."""
        stats = self._get_guild_stats(pk)
        return Response(stats)

    def _get_user_guilds(self, request):
        """Get guilds where user has admin permissions."""
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
                if permissions_value & 0x8 or permissions_value & 0x20:
                    config = GuildConfig.objects.filter(guild_id=int(guild['id'])).first()
                    guild['bot_present'] = config is not None
                    guild['member_count'] = guild.get('approximate_member_count', 0)
                    admin_guilds.append(guild)

            return admin_guilds
        except Exception:
            return []

    def _get_guild_stats(self, guild_id):
        """Calculate guild statistics."""
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())

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
                'new_this_week': BotUser.objects.filter(
                    guild_id=guild_id,
                    joined_at__gte=week_start
                ).count() if hasattr(BotUser, 'joined_at') else 0
            },
            'messages': {
                'total': user_stats['total_messages'] or 0,
                'today': 0  # Would need message tracking
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
    """ViewSet for user operations within a guild."""
    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = BotUserSerializer
    lookup_field = 'user_id'

    def get_queryset(self):
        guild_id = self.kwargs.get('guild_id')
        return BotUser.objects.filter(guild_id=guild_id).order_by('-total_xp')

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return BotUserUpdateSerializer
        return BotUserSerializer


@extend_schema_view(
    list=extend_schema(summary="List guild warnings"),
    create=extend_schema(summary="Create a warning", request=WarningCreateSerializer),
    destroy=extend_schema(summary="Delete a warning")
)
class WarningViewSet(viewsets.ModelViewSet):
    """ViewSet for warning operations within a guild."""
    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = WarningSerializer
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        guild_id = self.kwargs.get('guild_id')
        queryset = Warning.objects.filter(guild_id=guild_id).order_by('-created_at')

        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return WarningCreateSerializer
        return WarningSerializer

    def perform_create(self, serializer):
        guild_id = self.kwargs.get('guild_id')
        social_account = self.request.user.socialaccount_set.filter(provider='discord').first()
        moderator_id = social_account.uid if social_account else 0

        Warning.objects.create(
            user_id=serializer.validated_data['user_id'],
            guild_id=guild_id,
            moderator_id=moderator_id,
            reason=serializer.validated_data.get('reason', 'No reason provided')
        )


class ProfanityConfigView(APIView):
    """View for profanity filter configuration."""
    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]

    @extend_schema(
        summary="Get profanity config",
        responses={200: ProfanityConfigSerializer}
    )
    def get(self, request, guild_id):
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
    """ViewSet for banned words within a guild."""
    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = BannedWordSerializer
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        guild_id = self.kwargs.get('guild_id')
        return BannedWord.objects.filter(guild_id__in=[0, guild_id]).order_by('-severity', 'word')

    def get_serializer_class(self):
        if self.action == 'create':
            return BannedWordCreateSerializer
        return BannedWordSerializer

    def perform_create(self, serializer):
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
        instance = self.get_object()
        guild_id = self.kwargs.get('guild_id')

        # Only allow deleting server-specific words
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
    """ViewSet for profanity infractions (read-only)."""
    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = ProfanityInfractionSerializer

    def get_queryset(self):
        guild_id = self.kwargs.get('guild_id')
        queryset = ProfanityInfraction.objects.filter(guild_id=guild_id).order_by('-created_at')

        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        action_taken = self.request.query_params.get('action_taken')
        if action_taken:
            queryset = queryset.filter(action_taken=action_taken)

        return queryset[:100]


class LeaderboardView(APIView):
    """View for guild leaderboard."""
    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]

    @extend_schema(
        summary="Get guild leaderboard",
        parameters=[
            OpenApiParameter('limit', int, description='Number of entries (default 10, max 100)'),
        ],
        responses={200: LeaderboardEntrySerializer(many=True)}
    )
    def get(self, request, guild_id):
        limit = min(int(request.query_params.get('limit', 10)), 100)

        users = BotUser.objects.filter(guild_id=guild_id).order_by('-total_xp')[:limit]

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
    """ViewSet for level roles within a guild."""
    permission_classes = [permissions.IsAuthenticated, IsGuildAdmin]
    serializer_class = LevelRoleSerializer
    http_method_names = ['get', 'post', 'delete']

    def get_queryset(self):
        guild_id = self.kwargs.get('guild_id')
        return LevelRole.objects.filter(guild_id=guild_id).order_by('level')

    def get_serializer_class(self):
        if self.action == 'create':
            return LevelRoleCreateSerializer
        return LevelRoleSerializer

    def perform_create(self, serializer):
        guild_id = self.kwargs.get('guild_id')
        LevelRole.objects.update_or_create(
            guild_id=guild_id,
            level=serializer.validated_data['level'],
            defaults={'role_id': serializer.validated_data['role_id']}
        )


class HealthCheckView(APIView):
    """Health check endpoint."""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Health check",
        description="Returns OK if the API is healthy.",
        responses={200: {'type': 'object', 'properties': {'status': {'type': 'string'}}}}
    )
    def get(self, request):
        return Response({'status': 'ok'})
