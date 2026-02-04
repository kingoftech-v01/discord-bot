"""
Context processors for templates.
"""
from django.conf import settings


def bot_context(request):
    """Add bot-related context to all templates."""
    context = {
        'bot_prefix': settings.BOT_PREFIX,
        'site_name': 'Discord Bot Dashboard',
    }

    # Add Discord avatar if user is logged in
    if request.user.is_authenticated:
        try:
            social_account = request.user.socialaccount_set.filter(provider='discord').first()
            if social_account:
                extra_data = social_account.extra_data
                avatar_hash = extra_data.get('avatar')
                user_id = extra_data.get('id')

                if avatar_hash:
                    context['discord_avatar'] = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
                else:
                    # Default avatar
                    discriminator = int(extra_data.get('discriminator', 0))
                    context['discord_avatar'] = f"https://cdn.discordapp.com/embed/avatars/{discriminator % 5}.png"

                context['discord_username'] = extra_data.get('username', '')
                context['discord_id'] = user_id
        except Exception:
            pass

    return context
