"""Celery entry points. Thin wrappers over `services.py` (CLAUDE.md §4.3).

Tasks take **ids, not model instances** — a Celery argument is JSON on a Redis
queue, and a model instance would arrive as a snapshot of a row that has since
changed. Here the row *is* the state, so the id is the only sane argument.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)

#: Two minutes, then four, then eight. A gateway is usually unreachable for
#: seconds, and a result SMS that lands a quarter of an hour late is still the
#: result; one that is retried every ten seconds against a provider refusing an
#: invalid number is a bill.
RETRY_BACKOFF = 120
MAX_RETRIES = 3


@shared_task(bind=True, max_retries=MAX_RETRIES, name='notifications.deliver_sms')
def deliver_sms(self, message_id):
    """Hand one outbox row to the gateway."""
    from django.conf import settings

    from .models import SmsMessage
    from .services import deliver

    # Tasks run eagerly under test (CELERY_TASK_ALWAYS_EAGER), and without this
    # every test that publishes an exam would call a real gateway. The tests
    # that care assert on the outbox rows, which are written synchronously.
    if getattr(settings, 'TESTING', False):
        logger.debug('SMS %s not delivered: running under test', message_id)
        return 'testing'

    message = SmsMessage.objects.filter(pk=message_id).select_related('branch').first()
    if message is None:
        # The row was deleted between queueing and delivery. Nothing to send and
        # nothing to retry — a retry loop against a missing row is the classic
        # way a queue fills up with work that can never succeed.
        logger.warning('SMS %s vanished before delivery', message_id)
        return 'missing'

    if deliver(message):
        return 'sent'

    # The row already records the provider's code and message; the retry is for
    # the transient half of the failures. When the retries run out the row stays
    # FAILED, which is what the outbox screen shows and what a resend reads.
    try:
        raise self.retry(countdown=RETRY_BACKOFF * (2 ** self.request.retries))
    except self.MaxRetriesExceededError:
        logger.error('SMS %s failed after %d attempts: %s %s', message_id,
                     message.attempts, message.provider_code, message.provider_message)
        return 'failed'
