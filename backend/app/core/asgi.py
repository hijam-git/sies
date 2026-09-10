"""ASGI entry point.

Nothing serves the project this way today — production runs gunicorn/WSGI, and
docs/08 D8 decided the live activity feed polls rather than using WebSockets, so
there is no ASGI server and no Channels layer to deploy. This exists so that
decision can be revisited without a scaffolding step.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

application = get_asgi_application()
