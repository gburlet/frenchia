"""Django settings for Frenchia. Everything configurable comes from environment variables."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "backend"]),
    DJANGO_CSRF_TRUSTED_ORIGINS=(
        list,
        ["http://localhost:5173", "http://127.0.0.1:5173"],
    ),
    DJANGO_LOG_LEVEL=(str, "INFO"),
)

SECRET_KEY: str = env("DJANGO_SECRET_KEY")
DEBUG: bool = env("DJANGO_DEBUG")
ALLOWED_HOSTS: list[str] = env("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS: list[str] = env("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "django_tasks_db",
    "accounts",
    "inference",
    "curriculum",
    "authoring",
    "exercises",
    "progress",
    "tutor",
    "verbs",
    "vocabulary",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-ca"
TIME_ZONE = "America/Edmonton"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Cookies: the SPA reads the CSRF cookie and echoes it in X-CSRFToken.
CSRF_COOKIE_NAME = "csrftoken"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

_renderers = ["rest_framework.renderers.JSONRenderer"]
if DEBUG:
    _renderers.append("rest_framework.renderers.BrowsableAPIRenderer")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": _renderers,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Frenchia API",
    "DESCRIPTION": "Local-first French learning app.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": [],
}

# Native inference services (see inference/providers.py). MODE=fake swaps in deterministic
# stand-ins for tests and for working without the LLM/TTS running.
INFERENCE = {
    "MODE": env("INFERENCE_MODE", default="live"),
    "LLM_BASE_URL": env("INFERENCE_LLM_BASE_URL", default="http://host.docker.internal:11435/v1"),
    "LLM_MODEL": env("INFERENCE_LLM_MODEL", default="gemma4:12b-it-qat"),
    "LLM_TIMEOUT_S": env.float("INFERENCE_LLM_TIMEOUT_S", default=120.0),
    "TTS_BASE_URL": env("INFERENCE_TTS_BASE_URL", default="http://host.docker.internal:8791"),
    "TTS_MODEL": env("INFERENCE_TTS_MODEL", default="mlx-community/Kokoro-82M-bf16"),
    "TTS_VOICE": env("INFERENCE_TTS_VOICE", default="ff_siwis"),
    "TTS_TIMEOUT_S": env.float("INFERENCE_TTS_TIMEOUT_S", default=60.0),
}
# Which LLM writes learning content (lessons, verb/vocabulary banks, review extras): "local"
# uses the LLM above; "remote" an OpenAI-compatible server (e.g. the Alliance's gpt-oss-120b).
# Grading and the tutor always use the local LLM. With a remote author, drafts that pass the
# deterministic checks are published without the external (Haiku) proof-read.
AUTHORING = {
    "LLM": env("AUTHORING_LLM", default="local"),
    "BASE_URL": env("AUTHORING_LLM_BASE_URL", default=""),
    "MODEL": env("AUTHORING_LLM_MODEL", default="gpt-oss-120b"),
    "API_KEY": env("AUTHORING_LLM_API_KEY", default=""),
    "REASONING_EFFORT": env("AUTHORING_LLM_REASONING_EFFORT", default="low"),
    "TIMEOUT_S": env.float("AUTHORING_LLM_TIMEOUT_S", default=300.0),
    # Reasoning models spend output tokens on hidden reasoning; added to each request's max.
    "REASONING_TOKENS": env.int("AUTHORING_LLM_REASONING_TOKENS", default=4000),
    "EXTERNAL_REVIEW": env.bool(
        "AUTHORING_EXTERNAL_REVIEW", default=env("AUTHORING_LLM", default="local") == "local"
    ),
}

# Version-controlled learning content (mounted at /content in Docker)
CONTENT_DIR = Path(env("CONTENT_DIR", default=str(BASE_DIR.parent / "content")))

AUDIO_CACHE_DIR = Path(env("AUDIO_CACHE_DIR", default=str(BASE_DIR / "var" / "audio")))

TASKS = {
    "default": {
        "BACKEND": "django_tasks_db.DatabaseBackend",
        "QUEUES": ["default", "practice"],
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "{asctime} {levelname:<8} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "console",
        },
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL")},
    # One line per inference call is logged by the providers; httpx's own lines are noise.
    "loggers": {"httpx": {"level": "WARNING"}, "httpcore": {"level": "WARNING"}},
}
