"""ASGI entrypoint. In DEBUG, static files (e.g. Django Admin CSS) are served directly."""

import os
import threading
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


def _warm_content() -> None:
    """Parse the reference data and banks now, not on the first learner request (~2 s)."""
    from curriculum import content

    try:
        content.reference()
        content.banks()
    except Exception:  # a broken content file surfaces on the request that needs it
        pass


threading.Thread(target=_warm_content, daemon=True, name="content-warmup").start()
