from pathlib import Path
from datetime import timedelta

from decouple import config
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent.parent

AUTH_USER_MODEL = 'accounts.StaffUser'

# Case-insensitive username lookup at login — see accounts/backends.py.
AUTHENTICATION_BACKENDS = ['accounts.backends.CaseInsensitiveModelBackend']

SECRET_KEY = config('SECRET_KEY')

# --- Multi-tenancy (django-tenants: one Postgres schema per club) ---
# SHARED_APPS live once, in the `public` schema — mostly just what's needed
# to identify a tenant before its own schema can even be switched into.
# TENANT_APPS are synced into EVERY club's own schema: a club's players,
# transactions, staff logins, permissions, etc. are physically separate
# from every other club's, not merely filtered by a foreign key. See
# tenants/models.py for the Client/Domain models this all pivots on.
#
# django.contrib.contenttypes is deliberately listed in both — it's
# required in SHARED_APPS by django-tenants itself, but several
# TENANT_APPS models (permissions, admin log entries) hold FKs to
# ContentType rows that need to resolve within their own schema too.
SHARED_APPS = [
    'django_tenants',  # must load before anything else that touches the DB
    'tenants',
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
]

TENANT_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'rest_framework_simplejwt.token_blacklist',
    'django_celery_results',
    'django_celery_beat',
    'accounts',
    'gaming',
    'payments',
]

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

TENANT_MODEL = 'tenants.Client'
TENANT_DOMAIN_MODEL = 'tenants.Domain'

DATABASE_ROUTERS = ['django_tenants.routers.TenantSyncRouter']

MIDDLEWARE = [
    # Must run first: resolves the tenant from the request's Host header
    # and switches the DB connection to that club's schema before any
    # other middleware or view code runs.
    'django_tenants.middleware.main.TenantMainMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'lpc_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'lpc_backend.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [],  # no global throttle
    'DEFAULT_THROTTLE_RATES': {
        'auth': '100/hour',       # staff login
        'payout': '50/hour',      # payout initiation/approval
        'webhook': '600/hour',    # Paystack webhook intake
    },
    'NUM_PROXIES': 1,  # Railway
    'EXCEPTION_HANDLER': 'lpc_backend.exception_handling.exception_handler',
}

# Paystack — one key pair for the club's single integration. A player's
# "Gaming Account" is a Paystack Customer + Dedicated Virtual Account under
# this same integration, not a separate key pair (see payments/paystack_client.py,
# SCHEMA.md — revised 2026-09-13).
PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY', default='')
PAYSTACK_PUBLIC_KEY = config('PAYSTACK_PUBLIC_KEY', default='')

DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@example.com')
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)

CELERY_BROKER_URL = config('REDIS_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

CORS_ALLOW_HEADERS = list(default_headers)
