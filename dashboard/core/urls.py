"""
URL patterns for the core app.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('server/<int:guild_id>/', views.server_dashboard, name='server_dashboard'),
    path('server/<int:guild_id>/settings/', views.server_settings, name='server_settings'),
    path('server/<int:guild_id>/moderation/', views.moderation_settings, name='moderation_settings'),
    path('server/<int:guild_id>/leveling/', views.leveling_settings, name='leveling_settings'),
    path('server/<int:guild_id>/users/', views.users_list, name='users_list'),
    path('server/<int:guild_id>/infractions/', views.infractions_list, name='infractions_list'),

    # API
    path('api/server/<int:guild_id>/toggle-module/', views.api_toggle_module, name='api_toggle_module'),
]
