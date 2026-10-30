"""
Django settings for korrep project.
"""

import os
from pathlib import Path
import environ
from django.core.exceptions import ImproperlyConfigured

from monitor.siteconfig import LOCAL_SITE_URL, SERVER_SITE_URL, resolve_site_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False)
)

# Read .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'subscriptions',
    'monitor.apps.MonitorConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'korrep.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'korrep.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static',]
STATIC_ROOT = BASE_DIR / 'staticfiles'
# STATIC_ROOT = '/home/korrep/korrep_project/staticfiles'

# Media fájlok
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
# MEDIA_ROOT = '/home/korrep/korrep_project/media'



# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@korrep.local')
# Where the links in emails (confirmation, admin, reply) point. One switch:
#   SITE_MODE=local   -> http://localhost:8000              (your computer)
#   SITE_MODE=server  -> https://korrep.pythonanywhere.com  (PythonAnywhere)
#   SITE_MODE=custom  -> the SITE_URL value from .env       (any other address)
# Each environment has its own .env. The link must point at the app that holds the
# subscriber, so a local signup needs "local" and a signup on the server needs "server".
SITE_MODE = env('SITE_MODE', default='local').strip().lower()
try:
    SITE_URL = resolve_site_url(
        SITE_MODE,
        local_url=env('SITE_URL_LOCAL', default=LOCAL_SITE_URL),
        server_url=env('SITE_URL_SERVER', default=SERVER_SITE_URL),
        custom_url=env('SITE_URL', default=''),
    )
except ValueError as exc:
    raise ImproperlyConfigured(str(exc))
CSRF_TRUSTED_ORIGINS = [SITE_URL] if SITE_URL.startswith('https://') else []

# SMTP (production). Local development keeps the console backend above.
# Set these in .env when a real sender account is available.
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_PORT = env.int('EMAIL_PORT', default=25)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
# Never let a slow SMTP server block a web request indefinitely.
EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=10)


# Monitor app
# Recipient of the instant new-subscriber email and the daily report.
# Empty = no email is sent; data is still collected in the Django admin
# (Monitor > Subscriber notifications / Daily reports).
MONITOR_NOTIFY_EMAIL = env('MONITOR_NOTIFY_EMAIL', default='')
# The daily report covers the previous calendar day in this time zone.
MONITOR_REPORT_TIMEZONE = env('MONITOR_REPORT_TIMEZONE', default='Europe/Budapest')


# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '%(asctime)s %(levelname)s %(name)s: %(message)s'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'loggers': {
        'monitor': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'subscriptions': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
