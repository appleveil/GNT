from urllib.parse import urlparse

from decouple import config

from .base import *

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='', cast=lambda v: [h.strip() for h in v.split(',') if h.strip()])

_db = urlparse(config('DATABASE_URL'))
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': _db.path[1:],
        'USER': _db.username,
        'PASSWORD': _db.password,
        'HOST': _db.hostname,
        'PORT': _db.port or 5432,
    }
}

CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS', default='', cast=lambda v: [o.strip() for o in v.split(',') if o.strip()]
)
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS', default='', cast=lambda v: [o.strip() for o in v.split(',') if o.strip()]
)
CORS_ALLOW_CREDENTIALS = True

# Whitenoise — insert after SecurityMiddleware (index 0), before CorsMiddleware
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# No Redis deployed (deliberate, 2026-10-03) — Django's own default
# per-process LocMemCache is used instead. Nothing in this codebase reads
# from the cache today, so there's no cross-process consistency need yet;
# revisit if that changes. Celery itself (base.py's CELERY_BROKER_URL)
# still defaults to a localhost Redis URL, but that connection is only
# ever opened when a task is actually submitted — there are none, and the
# `worker`/`beat` Procfile processes aren't deployed, so this is inert.
