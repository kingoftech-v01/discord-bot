"""
Custom django-allauth social account adapter for Discord OAuth2 login.

django-allauth is a third-party Django package that handles OAuth2 flows.
By default, it populates the Django ``User`` model from a generic set of
fields.  This adapter overrides two hooks so that the user's **Discord
username** and **email** (from the Discord API ``/users/@me`` response)
are stored on the Django ``User`` record, making them available throughout
the dashboard without additional API calls.

Configuration:
    This adapter is activated by the setting::

        SOCIALACCOUNT_ADAPTER = 'core.adapters.DiscordSocialAccountAdapter'

    in ``dashboard/settings.py``.

See Also:
    - django-allauth documentation: https://docs.allauth.org/
    - Discord OAuth2 scopes: ``identify``, ``email``, ``guilds``
      (configured in ``SOCIALACCOUNT_PROVIDERS`` in settings).
"""
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class DiscordSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Adapter that maps Discord profile fields to Django ``User`` attributes.

    Extends the default allauth social account adapter to pull the
    ``username`` and ``email`` fields directly from the Discord API's
    ``extra_data`` payload rather than relying on allauth's generic
    field mapping, which may not resolve Discord-specific keys correctly.
    """

    def populate_user(self, request, sociallogin, data):
        """Populate a new Django ``User`` instance with Discord profile data.

        Called by allauth during the first-time signup flow, before the user
        record is saved to the database.  Overrides the parent to explicitly
        copy the Discord ``username`` and ``email`` from the social-login
        ``extra_data`` dictionary.

        Args:
            request: The current Django ``HttpRequest``.
            sociallogin: An allauth ``SocialLogin`` instance containing the
                social account, tokens, and ``extra_data`` from Discord.
            data: A dictionary of common fields that allauth has already
                extracted (may be incomplete for Discord).

        Returns:
            django.contrib.auth.models.User: The pre-populated (but not yet
            saved) ``User`` instance.
        """
        user = super().populate_user(request, sociallogin, data)

        # ``extra_data`` contains the raw JSON from Discord's /users/@me endpoint
        extra_data = sociallogin.account.extra_data

        user.username = extra_data.get('username', '')
        user.email = extra_data.get('email', '')

        return user

    def save_user(self, request, sociallogin, form=None):
        """Persist the Django ``User`` after a successful Discord OAuth2 login.

        This hook is called after :meth:`populate_user`.  The current
        implementation simply delegates to the parent class.  It exists as
        an explicit extension point in case future logic needs to run after
        the user record is committed (e.g. sending a welcome email, creating
        default preferences, syncing guild memberships).

        Args:
            request: The current Django ``HttpRequest``.
            sociallogin: An allauth ``SocialLogin`` instance.
            form: An optional signup form (``None`` when
                ``SOCIALACCOUNT_AUTO_SIGNUP`` is ``True``).

        Returns:
            django.contrib.auth.models.User: The saved ``User`` instance.
        """
        user = super().save_user(request, sociallogin, form)
        return user
