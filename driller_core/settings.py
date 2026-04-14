from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name, "True" if default else "False").strip().lower()
    return value in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "unsafe-local-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ENVIRONMENT = env("ENVIRONMENT", "development").strip().lower()
IS_DEVELOPMENT = ENVIRONMENT in {"development", "dev", "local"}
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "driller_core.apps.accounts.apps.AccountsConfig",
    "driller_core.apps.fieldlogs.apps.FieldLogsConfig",
    "driller_core.apps.network.apps.NetworkConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "driller_core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "driller_core.wsgi.application"
ASGI_APPLICATION = "driller_core.asgi.application"

if env("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER", ""),
            "PASSWORD": env("POSTGRES_PASSWORD", ""),
            "HOST": env("POSTGRES_HOST", "db"),
            "PORT": env("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Chicago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.UserAccount"

CORE_DISPLAY_NAME = env("CORE_DISPLAY_NAME", "Driller Core")
COMPANY_DISPLAY_NAME = env("COMPANY_DISPLAY_NAME", "Sunrise GEO")
PLATFORM_NAME = env("PLATFORM_NAME", "Driller Network")
DRILLER_CORE_INTERNAL_SHARED_SECRET = env("DRILLER_CORE_INTERNAL_SHARED_SECRET", "")
DRILLER_ACCESS_TOKEN_TTL_SECONDS = int(
    env("DRILLER_ACCESS_TOKEN_TTL_SECONDS", "2592000" if IS_DEVELOPMENT else "28800")
    or ("2592000" if IS_DEVELOPMENT else "28800")
)
DRILLER_ACCESS_TOKEN_SALT = env("DRILLER_ACCESS_TOKEN_SALT", "driller-core.driller-access")

if IS_DEVELOPMENT:
    SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days
    SESSION_SAVE_EVERY_REQUEST = True
    SESSION_EXPIRE_AT_BROWSER_CLOSE = False
