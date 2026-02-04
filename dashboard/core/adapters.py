"""
Custom adapters for django-allauth.
"""
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class DiscordSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Custom adapter for Discord OAuth."""

    def populate_user(self, request, sociallogin, data):
        """Populate user data from Discord."""
        user = super().populate_user(request, sociallogin, data)

        # Get Discord data
        extra_data = sociallogin.account.extra_data

        user.username = extra_data.get('username', '')
        user.email = extra_data.get('email', '')

        return user

    def save_user(self, request, sociallogin, form=None):
        """Save user after Discord login."""
        user = super().save_user(request, sociallogin, form)
        return user
