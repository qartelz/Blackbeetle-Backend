import os
from pathlib import Path
from dotenv import load_dotenv
# Load environment variables
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-x#gqm@1u!gck1ceqft#bd_2(51c%v%4ecgrf^h$29^4kslwo2d'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_celery_results',
    'channels',
    'phonenumber_field',
    'model_utils',
    # 'silk',
    # 'drf_yasg',
    'django_filters',
    'storages',
    
    
    # 'cloudinary_storage',  # For Cloudinary storage
    # 'cloudinary',  


    # Local apps
    'apps.indexAndCommodity.apps.IndexandcommodityConfig',
    'apps.institutions.apps.InstitutionsConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.subscriptions.apps.SubscriptionsConfig',
    'apps.trades.apps.TradesConfig',
    'apps.users.apps.UsersConfig',
    'apps.analytics.apps.AnalyticsConfig',
    'apps.accuracy.apps.AccuracyConfig',
    'apps.events.apps.EventsConfig',
    'apps.stockreports.apps.StockreportsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 'silk.middleware.SilkyMiddleware',
]

ROOT_URLCONF = 'config.urls'

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


# WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels.layers.InMemoryChannelLayer"
#     }
# }

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

# TIME_ZONE = 'UTC'
TIME_ZONE = 'Asia/Kolkata'  

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'users.User'


# REST Framework settings
# REST_FRAMEWORK = {
#     'DEFAULT_AUTHENTICATION_CLASSES': (
#         'rest_framework_simplejwt.authentication.JWTAuthentication',
#     ),
#     'DEFAULT_PERMISSION_CLASSES': (
#         # 'rest_framework.permissions.IsAuthenticated',
#         'rest_framework.permissions.AllowAny',
#     ),
# }

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        # 'rest_framework.permissions.IsAuthenticated',
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}
# Simple JWT settings
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=10),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
}


# Celery settings
CELERY_BROKER_URL ='redis://localhost:6379/1'
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Kolkata'


# Channels settings
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("redis://localhost:6379/0")],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://localhost:6379/3",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}



# CORS settings
# CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')

# Logging configuration
# LOGGING = {
#     'version': 1,
#     'disable_existing_loggers': False,
#     'handlers': {
#         'console': {
#             'class': 'logging.StreamHandler',
#         },
#     },
#     'root': {
#         'handlers': ['console'],
#         'level': 'INFO',
#     },
# }

# Email configuration
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
# EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
# EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
# EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')



# Enable Python profiling for all views
SILKY_PYTHON_PROFILER = True 

# Profile 100% of all requests (you can change this to a lower number if you only want to profile some requests)
SILKY_INTERCEPT_PERCENT = 100  

# Optionally, enable request body logging (in case you want to see request data as well)
SILKY_MAX_REQUEST_BODY_SIZE = 5120  # Limit size of request bodies in bytes



# # Storage Configuration
# DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
# STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'


# # AWS S3 Credentials
# AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
# AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
# AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
# AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')  # Change to your region


# # S3 Storage Settings
# AWS_DEFAULT_ACL = 'private'  # or 'public-read' if you want files to be public
# AWS_QUERYSTRING_AUTH = False
# AWS_S3_OBJECT_PARAMETERS = {
    
# }

# AWS_S3_ENDPOINT_URL = f's3.{AWS_S3_REGION_NAME}.blackblazeb2.com'
# AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL', AWS_S3_ENDPOINT_URL)
# CLOUDINARY_STORAGE = {
#     'CLOUD_NAME': 'dzbkxbdxk',  # Your Cloudinary cloud name
#     'API_KEY': '644167324768948',  # Your API key
#     'API_SECRET': 'bkirfDoAEMbdxCZCLJMMKYd9P-0',  # Your API secret
# }

# CLOUDINARY_URL = 'cloudinary://644167324768948:bkirfDoAEMbdxCZCLJMMKYd9P-0@dzbkxbdxk'

# DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'


# Optionally configure media URL
# MEDIA_URL = 'https://res.cloudinary.com/dzbkxbdxk/image/upload/'

# Other settings (media)
# MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')
# Backblaze B2 Credentials
# B2_KEY_ID = '6cdad2abca8c'
# B2_APPLICATION_KEY = '005e4f4cf2228056568c458de991ff44b23da7df82'  # Corrected from screenshot
# B2_BUCKET_NAME = 'BlackBeetl'
# B2_BUCKET_URL = 's3.us-east-005.backblazeb2.com'

# # Django Storage Settings
# DEFAULT_FILE_STORAGE = 'apps.trades.BackblazeB2Storage.BackblazeB2Storage'

# # Media files configuration
# MEDIA_URL = f'https://{B2_BUCKET_URL}/{B2_BUCKET_NAME}/media/'
# MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# # S3-compatible settings for B2
# AWS_S3_REGION_NAME = 'us-east-005'
# AWS_ACCESS_KEY_ID = B2_KEY_ID  # Use B2 credentials
# AWS_SECRET_ACCESS_KEY = B2_APPLICATION_KEY  # Use B2 credentials
# AWS_S3_ENDPOINT_URL = f'https://{B2_BUCKET_URL}'  # Add this line
# AWS_STORAGE_BUCKET_NAME = B2_BUCKET_NAME
# AWS_S3_FILE_OVERWRITE = False
# AWS_DEFAULT_ACL = 'public-read'
# AWS_QUERYSTRING_AUTH = False
# AWS_S3_VERIFY = True






