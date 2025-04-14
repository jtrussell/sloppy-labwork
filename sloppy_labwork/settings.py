"""
Django settings for sloppy_labwork project.

Generated by 'django-admin startproject' using Django 3.0.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.0/ref/settings/
"""

import os

# Prime our environment if we've got a file to do so.
try:
    from . import local_environment
except:
    pass

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ['SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ['DEBUG'] == 'True'

ALLOWED_HOSTS = []
if not DEBUG:
    ALLOWED_HOSTS = ['.sloppylabwork.com', 'sloppy-labwork.herokuapp.com']

SITE_ID = int(os.environ['SITE_ID'])

MAX_UPLOADS_PER_DAY = int(os.environ['MAX_UPLOADS_PER_DAY'])

AWS_S3_BUCKET_VERIFICATION_PHOTOS_BUCKET = os.environ['AWS_S3_BUCKET_VERIFICATION_PHOTOS_BUCKET']
AWS_S3_BUCKET_MV_QRCODE = os.environ['AWS_S3_BUCKET_MV_QRCODE']


GA_TRACKING_ID = os.environ['GA_TRACKING_ID']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.discord',
    'register',
    'ratings',
    'posts',
    'decks',
    'user_profile',
    'tournaments',
    'redacted',
    'transporter_platform',
    'pmc',
    'django_hosts',
]

MIDDLEWARE = [
    'django_hosts.middleware.HostsRequestMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django_hosts.middleware.HostsResponseMiddleware',
]

ROOT_URLCONF = 'sloppy_labwork.urls'
ROOT_HOSTCONF = 'sloppy_labwork.hosts'
DEFAULT_HOST = 'default'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'sloppy_labwork.context_processors.base_template',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.request',
                'django.template.context_processors.static',
                'sloppy_labwork.context_processors.feature_flags',
                'sloppy_labwork.context_processors.teammate_authorized',
                'pmc.context_processors.nav_links',
                'pmc.context_processors.playgroup',
                'pmc.context_processors.playgroup_member',
                'pmc.context_processors.pmc_profile',
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
)

SOCIALACCOUNT_AUTO_SIGNUP = False

LOGIN_REDIRECT_URL = '/@me/'

ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_EMAIL_REQUIRED = True

ACCOUNT_DEFAULT_HTTP_PROTOCOL = os.environ['ACCOUNT_DEFAULT_HTTP_PROTOCOL']


WSGI_APPLICATION = 'sloppy_labwork.wsgi.application'

DEFAULT_FROM_EMAIL = 'no-reply@sloppylabwork.com'
EMAIL_BACKEND = 'django_ses.SESBackend'

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = '/static/'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Feature Flags
FT_USE_REGISTER = os.environ['FT_USE_REGISTER'] == 'True'
FT_USE_RATINGS = os.environ['FT_USE_RATINGS'] == 'True'
FT_USE_POSTS = os.environ['FT_USE_POSTS'] == 'True'
FT_USE_EVENTS = os.environ['FT_USE_EVENTS'] == 'True'

# Bootstrap Heroku settings
MAX_CONN_AGE = 600
if "DATABASE_URL" in os.environ:
    import dj_database_url
    DATABASES["default"] = dj_database_url.config(
        conn_max_age=MAX_CONN_AGE, ssl_require=True)
