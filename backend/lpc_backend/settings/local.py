from decouple import config

from .base import *

DEBUG = True

ALLOWED_HOSTS = [
    'localhost', '127.0.0.1', '192.168.100.2', '192.168.88.12',
    '4448-102-88-168-35.ngrok-free.app', 'test1.localhost', 'test2.localhost',
]

DATABASES = {
    'default': {
        # django-tenants' backend wraps the plain postgresql one — it's
        # what actually switches the connection's search_path per request.
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': config('DB_NAME', default='lpc_reconciliation'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default='postgres'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://localhost:5174',
    'http://localhost:3000',
]

CORS_ALLOW_CREDENTIALS = True
