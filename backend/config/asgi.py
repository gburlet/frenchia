"""ASGI entrypoint. In DEBUG, static files (e.g. Django Admin CSS) are served directly."""

import os
from collections.abc import Callable
from typing import Any

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from django.conf import settings  # noqa: E402

if settings.DEBUG:
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

    application: Callable[..., Any] = ASGIStaticFilesHandler(django_asgi_app)
else:
    application = django_asgi_app
