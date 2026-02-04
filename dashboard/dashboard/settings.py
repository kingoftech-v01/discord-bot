"""
Django settings for the Discord Bot Pro web dashboard.

This settings module configures the Django application that provides both
a server-rendered admin dashboard and a REST API for the Discord bot.  It
reads sensitive values (secrets, tokens, feature flags) from environment
variables -- with safe defaults for local development -- and applies
production security hardening when ``DEBUG=False``.

Key integrations configured here:
    - **django-allauth** -- Discord OAuth2 login so guild administrators
      can authenticate with their Discord account.
    - **Django REST Framework (DRF)** -- Powers the ``/api/v1/`` endpoints
      with session authentication, pagination, filtering, and rate limiting.
    - **drf-spectacular** -- Auto-generates an OpenAPI 3.0 schema and
      serves Swagger UI / ReDoc documentation.
    - **django-cors-headers** -- Allows cross-origin requests from the
      configured frontend origins (useful when a separate SPA consumes the
      API).
    - **WhiteNoise** -- Serves static files efficiently in production
      without a separate web server for statics.

Environment variables (all optional with defaults):
    DJANGO_SECRET_KEY       -- Django secret key (MUST be set in production).
    DJANGO_DEBUG            -- ``'True'`` to enable debug mode (default
                               ``'False'``).
    DJANGO_ALLOWED_HOSTS    -- Comma-separated list of allowed hostnames.
    DISCORD_CLIENT_ID       -- Discord application client ID for OAuth2.
    DISCORD_CLIENT_SECRET   -- Discord application client secret for OAuth2.
    DISCORD_TOKEN           -- Bot token (used for bot-related API calls).
    BOT_PREFIX              -- Default command prefix.
    CORS_ALLOWED_ORIGINS    -- Comma-separated list of allowed CORS origins.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from a ``.env`` file if present (development).
load_dotenv()

# ---------------------------------------------------------------------------
# Path configuration
# ---------------------------------------------------------------------------
# BASE_DIR points to the ``dashboard/`` directory (one level above this file's
# parent ``dashboard/dashboard/``).
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Security fundamentals
# ---------------------------------------------------------------------------
# SECURITY: SECRET_KEY must be set in production. The fallback is only for local development.
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-this-in-production')
# SECURITY: DEBUG defaults to False in production. Set DJANGO_DEBUG=True only for local dev.
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django built-in apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',       # Template filters for numbers/dates
    'django.contrib.sites',          # Required by django-allauth

    # django-allauth: handles Discord OAuth2 sign-in
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.discord',

    # Django REST Framework and companions
    'rest_framework',                # REST API toolkit
    'drf_spectacular',               # OpenAPI schema generation
    'corsheaders',                   # Cross-Origin Resource Sharing headers
    'django_filters',                # Queryset filtering for DRF

    # Project apps
    'core',                          # Dashboard views, models, templates
    'api',                           # REST API (DRF viewsets, serializers)
]

# Middleware order matters: SecurityMiddleware must be first; WhiteNoise must
# come immediately after it; CorsMiddleware must come before CommonMiddleware.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',       # HTTPS redirects, HSTS
    'whitenoise.middleware.WhiteNoiseMiddleware',           # Serve static files
    'corsheaders.middleware.CorsMiddleware',                # CORS preflight handling
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',        # Required by allauth >= 0.56
]

ROOT_URLCONF = 'dashboard.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Project-wide templates live in ``dashboard/templates/``
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',   # Required by allauth
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # Custom context processor that injects bot metadata
                # (name, prefix, version) into every template context.
                'core.context_processors.bot_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'dashboard.wsgi.application'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# The dashboard shares the **same SQLite database** as the Discord bot.  The
# file lives at ``<project_root>/data/bot.db``.  All ``core`` models use
# ``managed = False`` so Django never tries to create or alter bot tables.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR.parent / 'data' / 'bot.db',
    }
}

# ---------------------------------------------------------------------------
# django-allauth configuration
# ---------------------------------------------------------------------------

# ``SITE_ID`` is required by ``django.contrib.sites``, which allauth depends on.
SITE_ID = 1

# Authentication backends: Django's built-in model backend + allauth's backend.
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Standard allauth account settings
ACCOUNT_AUTHENTICATION_METHOD = 'username'
ACCOUNT_EMAIL_REQUIRED = False            # Discord email is optional
ACCOUNT_EMAIL_VERIFICATION = 'none'       # No email verification needed
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_LOGOUT_ON_GET = True              # Allow logout via GET for simplicity

# Discord OAuth2 provider configuration
SOCIALACCOUNT_PROVIDERS = {
    'discord': {
        'APP': {
            # Falls back to APPLICATION_ID if DISCORD_CLIENT_ID is not set
            'client_id': os.getenv('DISCORD_CLIENT_ID', os.getenv('APPLICATION_ID', '')),
            'secret': os.getenv('DISCORD_CLIENT_SECRET', ''),
            'key': ''
        },
        'SCOPE': [
            'identify',   # Access the user's Discord username and avatar
            'email',      # Access the user's email address
            'guilds',     # List the guilds the user belongs to
        ],
        'AUTH_PARAMS': {
            'prompt': 'consent',  # Always show the OAuth2 consent screen
        },
    }
}

SOCIALACCOUNT_AUTO_SIGNUP = True          # Skip the signup form; create users automatically
SOCIALACCOUNT_LOGIN_ON_GET = True         # Start OAuth2 flow on GET (no intermediate page)
SOCIALACCOUNT_STORE_TOKENS = True         # Persist OAuth2 tokens so we can call the Discord API later
SOCIALACCOUNT_ADAPTER = 'core.adapters.DiscordSocialAccountAdapter'

# Redirect URLs for the authentication flow
LOGIN_URL = '/accounts/discord/login/'    # Where @login_required sends unauthenticated users
LOGIN_REDIRECT_URL = '/dashboard/'        # Landing page after successful login
LOGOUT_REDIRECT_URL = '/'                 # Landing page after logout
ACCOUNT_LOGOUT_REDIRECT_URL = '/'

# ---------------------------------------------------------------------------
# Password validation (Django defaults)
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'fr-fr'       # French locale (the bot's primary audience)
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript, images)
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']       # Development static sources
STATIC_ROOT = BASE_DIR / 'staticfiles'          # ``collectstatic`` output

# ---------------------------------------------------------------------------
# Miscellaneous Django settings
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Discord bot / API settings
# ---------------------------------------------------------------------------
DISCORD_BOT_TOKEN = os.getenv('DISCORD_TOKEN', '')
BOT_PREFIX = os.getenv('BOT_PREFIX', '!')

# Base URL for the Discord REST API (v10).  Used by views and the
# ``IsGuildAdmin`` permission class to fetch user guilds.
DISCORD_API_BASE = 'https://discord.com/api/v10'

# ---------------------------------------------------------------------------
# Django REST Framework (DRF) configuration
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    # Authentication: session-based (shares the same session cookie as the
    # server-rendered dashboard).  Token / JWT auth can be added later.
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    # Default permission: every endpoint requires an authenticated user.
    # Individual views may override this (e.g. HealthCheckView uses AllowAny).
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Filtering / search / ordering available on all list endpoints
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    # Pagination: page-number style, 20 items per page
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # Schema generation powered by drf-spectacular
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Rate limiting to protect against abuse
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/minute',     # Unauthenticated requests
        'user': '60/minute',     # Authenticated requests
    },
}

# ---------------------------------------------------------------------------
# drf-spectacular (OpenAPI / Swagger) settings
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'Discord Bot Pro API',
    'DESCRIPTION': 'REST API for Discord Bot Pro Dashboard',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,    # Do not include the schema endpoint in the schema itself
    'COMPONENT_SPLIT_REQUEST': True,  # Separate request/response schemas for clarity
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
    },
    # Tag groupings shown in Swagger UI / ReDoc sidebar
    'TAGS': [
        {'name': 'guilds', 'description': 'Guild operations'},
        {'name': 'users', 'description': 'User operations'},
        {'name': 'moderation', 'description': 'Moderation operations'},
        {'name': 'leveling', 'description': 'Leveling system'},
        {'name': 'profanity', 'description': 'Profanity filter'},
    ],
}

# ---------------------------------------------------------------------------
# CORS (Cross-Origin Resource Sharing)
# ---------------------------------------------------------------------------
# Allow requests from the configured frontend origins (default: localhost:3000
# for local SPA development).
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
# Allow credentials (cookies) so session-based auth works cross-origin
CORS_ALLOW_CREDENTIALS = True

# ========================
# SECURITY HARDENING
# ========================
# These settings are enforced in production (when DEBUG=False).
# They follow the recommendations from ``django-admin check --deploy``
# and the OWASP Secure Headers Project.
if not DEBUG:
    # --- HTTPS enforcement ---------------------------------------------------
    # Redirect all HTTP requests to HTTPS.
    SECURE_SSL_REDIRECT = True
    # Trust the ``X-Forwarded-Proto`` header set by reverse proxies (e.g.
    # Nginx, AWS ALB) to detect that the original request was HTTPS.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # --- HSTS (HTTP Strict Transport Security) --------------------------------
    # Instruct browsers to only access this site over HTTPS for 1 year.
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # --- Cookie security ------------------------------------------------------
    # Ensure cookies are only sent over HTTPS and are not accessible via JS.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True

    # --- Content security headers ---------------------------------------------
    # Prevent MIME-type sniffing attacks.
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Legacy XSS filter header (still respected by some older browsers).
    SECURE_BROWSER_XSS_FILTER = True
    # Prevent the site from being embedded in an iframe (clickjacking).
    X_FRAME_OPTIONS = 'DENY'
