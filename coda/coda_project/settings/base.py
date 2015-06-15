# Base settings for coda_project
import os
import json
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured

# Absolute path to the settings module
SETTINGS_ROOT = os.path.dirname(__file__)

# Absolute path to the project 
PROJECT_ROOT = os.path.dirname(SETTINGS_ROOT)

# Absolute path to the site directory
SITE_ROOT = os.path.dirname(PROJECT_ROOT)

# Compose a path from the project root
project_path = lambda path: os.path.join(PROJECT_ROOT, path)

# Compose path from the site root
site_path = lambda path: os.path.join(SITE_ROOT, path)

# Get our secrets from a file outside of version control.
# This helps to keep the settings files generic.
with open(os.path.join(SETTINGS_ROOT, "secrets.json")) as f:
    secrets = json.loads(f.read())

def get_secret(setting, secrets=secrets):
    try:
        return secrets[setting]
    except KeyError:
        error_msg = "The {0} secret is not set.".format(setting)
        raise ImproperlyConfigured(error_msg)


DEBUG = True

TEMPLATE_DEBUG = DEBUG

MAINTENANCE_MSG = get_secret("MAINTENANCE_MSG")

TIME_ZONE = 'America/Chicago'

LANGUAGE_CODE = 'en-us'

USE_I18N = True

MEDIA_ROOT = site_path('media')

MEDIA_URL = '/media/'

ADMIN_MEDIA_PREFIX = '/media/admin/'

SECRET_KEY = get_secret("SECRET_KEY")

DATABASES = {
    'default': {
        'NAME': get_secret("DB_NAME"),
        'USER': get_secret("DB_USER"),
        'ENGINE': 'django.db.backends.mysql',
        'PASSWORD': get_secret("DB_PASSWORD"),
        'HOST': get_secret("DB_HOST"),
        'PORT': get_secret("DB_PORT"),
    }
}


TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',)

ROOT_URLCONF = 'coda_project.urls'

TEMPLATE_DIRS = (
    site_path('templates'),)

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.auth.context_processors.auth',
    'django.core.context_processors.i18n',
    'django.core.context_processors.media',
    'django.core.context_processors.request',)

# Let the view know if we are in "proxy mode" or not.
# this uses the coda instance as a reverse proxy for the archival storage nodes
# setting to false sends requests directly to the archival servers.
CODA_PROXY_MODE = False

DJANGO_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'django.contrib.admindocs',
    'django.contrib.admin',
    'django.contrib.humanize',)

THIRD_PARTY_APPS = (
    'premis_event_service',
)

LOCAL_APPS = (
    'coda_mdstore',
    'coda_replication',
    'coda_oaipmh',
    'coda_validate',)

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

VALIDATION_PERIOD = timedelta(days=365)
