import logging
import os

from celery import Celery

logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('sies')

# Every CELERY_* name in settings.py, minus the prefix. Keeping the config in
# Django settings rather than here means the worker, beat and the web process
# cannot disagree about the broker.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Finds tasks.py in each installed app. An app added to INSTALLED_APPS therefore
# needs no registration step here — which matters because the phases add apps one
# at a time.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Proves the worker is consuming: `celery -A core call core.celery.debug_task`."""
    logger.debug('Celery debug_task request: %r', self.request)
