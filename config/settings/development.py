from .base import *

# ALLOWED_HOSTS = ['backend.blackbeetlescreen.com']






# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }
#postgresql://postgres:@roundhouse.proxy.rlwy.net:36356/railway
#postgresql://postgres:ZDlJpsEBJcUYNqgvVGLwKRrxiDkKqlUZ@monorail.proxy.rlwy.net:13906/railway

# postgresql://postgres:dokMzWIoIdTblnxAqKHlbZAaRxOTCrXg@roundhouse.proxy.rlwy.net:36356/railway
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'railway',                                      #################  this is for production################
#         'USER': 'postgres',
#         'PASSWORD': 'ZDlJpsEBJcUYNqgvVGLwKRrxiDkKqlUZ',
#         'HOST': 'monorail.proxy.rlwy.net',  
#         'PORT': '13906',
#         'CONN_MAX_AGE': 300,
#     }
# }


# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'railway',
#         'USER': 'postgres',
#         'PASSWORD': 'yEnxxNzptmKRPRsJKaUaaXXXlHiSlvdA',
#         'HOST': 'centerbeam.proxy.rlwy.net',  
#         'PORT': '39900',
#         'CONN_MAX_AGE': 300,
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'railway',
        'USER': 'postgres',
        'PASSWORD': 'nokbbbXgIDvLZYDXpOEnOpOblnuxibOu',
        'HOST': 'maglev.proxy.rlwy.net',  
        'PORT': '25499',
        'CONN_MAX_AGE': 300,
    }
}
"""
rajid db not to be used fo now
"""

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'railway',
#         'USER': 'postgres',
#         'PASSWORD': 'dokMzWIoIdTblnxAqKHlbZAaRxOTCrXg',
#         'HOST': 'roundhouse.proxy.rlwy.net',  
#         'PORT': '36356',
#         'CONN_MAX_AGE': 300,
#     }
# }



# CORS settings
CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8001",
    "http://127.0.0.1:3000",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["GET","POST","PUT","PATCH",  "DELETE","OPTIONS",]

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Celery settings
CELERY_BROKER_URL = 'redis://localhost:6379'
CELERY_RESULT_BACKEND = 'redis://localhost:6379'

# # Cache settings
# CACHES = {
#     'default': {
#         'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
#     }
# }

GEOIP_DB_PATH = os.path.join(BASE_DIR, 'geoip', 'GeoLite2-City.mmdb')

# Add Django Debug Toolbar
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}

WEBSOCKET_CONNECT_TIMEOUT = 20  # seconds
WEBSOCKET_DISCONNECT_TIMEOUT = 10  # seconds


# Basic SMTP Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # Or your SMTP server
EMAIL_PORT = 587  # Common ports: 587 (TLS) or 465 (SSL)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'vectorlab64@gmail.com'
EMAIL_HOST_PASSWORD = 'wbaahfnzdipvfwdm' 


REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0