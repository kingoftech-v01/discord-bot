"""
API URL Configuration for Discord Bot Dashboard.
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

# Main router for guilds
router = DefaultRouter()
router.register(r'guilds', GuildViewSet, basename='guild')

# Nested routes for guild-specific resources
guild_router = DefaultRouter()
guild_router.register(r'users', UserViewSet, basename='guild-user')
guild_router.register(r'warnings', WarningViewSet, basename='guild-warning')
guild_router.register(r'profanity/words', BannedWordViewSet, basename='guild-banned-word')
guild_router.register(r'profanity/infractions', InfractionViewSet, basename='guild-infraction')
guild_router.register(r'level-roles', LevelRoleViewSet, basename='guild-level-role')

urlpatterns = [
    # Health check
    path('health/', HealthCheckView.as_view(), name='api-health'),

    # OpenAPI schema and documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Main API routes
    path('v1/', include(router.urls)),

    # Guild-specific routes
    path('v1/guilds/<int:guild_id>/', include([
        path('', include(guild_router.urls)),
        path('profanity/config/', ProfanityConfigView.as_view(), name='guild-profanity-config'),
        path('leaderboard/', LeaderboardView.as_view(), name='guild-leaderboard'),
    ])),
]
