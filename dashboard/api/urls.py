"""
API URL routing for the Discord Bot Dashboard REST API.

This module defines the URL patterns for all ``/api/`` endpoints.  It uses
DRF's :class:`~rest_framework.routers.DefaultRouter` to automatically
generate standard CRUD URLs for viewsets, plus manual ``path()`` entries
for non-viewset views and the OpenAPI documentation endpoints.

URL structure overview::

    /api/health/                                   -- Health check (unauthenticated)
    /api/schema/                                   -- OpenAPI 3.0 JSON/YAML schema
    /api/docs/                                     -- Swagger UI
    /api/redoc/                                    -- ReDoc

    /api/v1/guilds/                                -- Guild list
    /api/v1/guilds/{id}/                           -- Guild detail / update

    /api/v1/guilds/{guild_id}/users/               -- User list / CRUD
    /api/v1/guilds/{guild_id}/warnings/            -- Warning list / create / delete
    /api/v1/guilds/{guild_id}/profanity/words/     -- Banned-word list / create / delete
    /api/v1/guilds/{guild_id}/profanity/infractions/ -- Infraction list (read-only)
    /api/v1/guilds/{guild_id}/profanity/config/    -- Profanity config get / patch
    /api/v1/guilds/{guild_id}/level-roles/         -- Level-role list / create / delete
    /api/v1/guilds/{guild_id}/leaderboard/         -- XP leaderboard

Routing strategy:
    Two ``DefaultRouter`` instances are used:

    1. ``router`` -- Top-level router for the ``/api/v1/guilds/`` collection
       (handled by :class:`~api.views.GuildViewSet`).
    2. ``guild_router`` -- Nested router whose URL patterns are included
       under ``/api/v1/guilds/<int:guild_id>/``.  This gives every
       guild-scoped viewset access to the ``guild_id`` URL parameter via
       ``self.kwargs['guild_id']``.

    The ``ProfanityConfigView`` and ``LeaderboardView`` are plain
    ``APIView`` subclasses (not viewsets), so they are registered with
    explicit ``path()`` calls inside the same nested include.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView
)

from .views import (
    GuildViewSet, UserViewSet, WarningViewSet, BannedWordViewSet,
    InfractionViewSet, LevelRoleViewSet, ProfanityConfigView,
    LeaderboardView, HealthCheckView
)

# ---------------------------------------------------------------------------
# Top-level router: handles /api/v1/guilds/ (list + detail + stats action)
# ---------------------------------------------------------------------------
router = DefaultRouter()
router.register(r'guilds', GuildViewSet, basename='guild')

# ---------------------------------------------------------------------------
# Guild-scoped router: generates CRUD URLs for resources nested under a
# specific guild.  These patterns are included under
# /api/v1/guilds/<int:guild_id>/ below.
# ---------------------------------------------------------------------------
guild_router = DefaultRouter()
guild_router.register(r'users', UserViewSet, basename='guild-user')
guild_router.register(r'warnings', WarningViewSet, basename='guild-warning')
guild_router.register(r'profanity/words', BannedWordViewSet, basename='guild-banned-word')
guild_router.register(r'profanity/infractions', InfractionViewSet, basename='guild-infraction')
guild_router.register(r'level-roles', LevelRoleViewSet, basename='guild-level-role')

urlpatterns = [
    # Unauthenticated health-check for monitoring / load-balancer probes
    path('health/', HealthCheckView.as_view(), name='api-health'),

    # OpenAPI schema and interactive documentation (powered by drf-spectacular)
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Top-level API routes (guild list, guild detail, guild stats action)
    path('v1/', include(router.urls)),

    # Guild-specific (nested) routes -- every viewset in ``guild_router``
    # receives the ``guild_id`` keyword argument from the URL.
    path('v1/guilds/<int:guild_id>/', include([
        # Viewset-generated routes (users, warnings, profanity words/infractions, level-roles)
        path('', include(guild_router.urls)),
        # Singleton profanity config (GET + PATCH)
        path('profanity/config/', ProfanityConfigView.as_view(), name='guild-profanity-config'),
        # XP leaderboard (GET only)
        path('leaderboard/', LeaderboardView.as_view(), name='guild-leaderboard'),
    ])),
]
