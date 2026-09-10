# Importing the Celery app here is what makes @shared_task in every other app
# bind to it. Without this line those tasks register against a default app that
# has none of our settings — they queue to the wrong broker, silently.
from .celery import app as celery_app

__all__ = ('celery_app',)
