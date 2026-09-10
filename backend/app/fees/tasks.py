"""Celery entry points. Thin wrappers over `services.py` (CLAUDE.md §4.3).

Nothing decides anything here. Each task resolves its arguments, calls one
service and returns what it did, so the same operation is testable without a
broker and runnable from a management command — which is how `dev.sh` and the
`generate_monthly_fees` command exercise it.

Tasks take **ids, not model instances**. A Celery argument is JSON on a Redis
queue; a model instance would either fail to serialise or, with a pickle
serialiser, arrive as a snapshot of a row that has since changed.
"""

import logging

from celery import shared_task

from .services import accrue_fines, generate_monthly_fees, mark_overdue

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CELERY_BEAT_SCHEDULE — for the coordinator to paste into core/settings.py
#
# This file does not edit settings (that is the coordinator's, so the schedule
# for every app lands in one reviewable place). Paste the three entries below
# into the empty `CELERY_BEAT_SCHEDULE = {}` at core/settings.py:401, and add
# `from celery.schedules import crontab` at the top of that block.
#
#     CELERY_BEAT_SCHEDULE = {
#         # docs/06 #9 — nobody clicks "raise this month's fees". 00:15 rather
#         # than midnight so the run is not competing with the nightly backup,
#         # and because a month boundary at exactly 00:00 is where clock skew
#         # between the worker and the database shows up as the wrong period.
#         'fees.generate-monthly': {
#             'task': 'fees.generate_monthly_fees',
#             'schedule': crontab(minute=15, hour=0, day_of_month=1),
#         },
#         # Nightly, after midnight, before anyone opens the dues screen. The
#         # fine is RECOMPUTED from the day count rather than incremented, so a
#         # double run on one night is a no-op (services.accrue_fines).
#         'fees.accrue-fines': {
#             'task': 'fees.accrue_fines',
#             'schedule': crontab(minute=30, hour=0),
#         },
#         # A branch with no fine policy never passes through accrue_fines, so
#         # without this its invoices would sit at `unpaid` forever and its dues
#         # screen would show nothing as late.
#         'fees.mark-overdue': {
#             'task': 'fees.mark_overdue',
#             'schedule': crontab(minute=40, hour=0),
#         },
#     }
#
# CELERY_TASK_ROUTES, if the coordinator is splitting queues: these three belong
# on the default queue. Monthly generation is the longest job in the system —
# one insert per student per monthly category — and it is also the one that must
# not be starved by short interactive tasks, so it wants its own worker rather
# than its own queue only if the institution grows past a few thousand students.
# ─────────────────────────────────────────────────────────────────────────────


@shared_task(name='fees.generate_monthly_fees')
def generate_monthly_fees_task(branch_id=None, period=None):
    """The 1st-of-month job (docs/06 #9). Safe to retry — see `raise_fee()`."""
    branch = _branch(branch_id)
    result = generate_monthly_fees(branch=branch, period=period)
    logger.info('fees.generate_monthly_fees(branch=%s, period=%s) -> %s',
                branch_id, period, result)
    return result


@shared_task(name='fees.accrue_fines')
def accrue_fines_task(branch_id=None):
    """Nightly late fines, from `Branch.fine_rule`. Capped, and it stops when paid."""
    branch = _branch(branch_id)
    result = accrue_fines(branch=branch)
    logger.info('fees.accrue_fines(branch=%s) -> %s', branch_id, result)
    return result


@shared_task(name='fees.mark_overdue')
def mark_overdue_task(branch_id=None):
    """Move past-due invoices to `overdue` where no fine policy is configured."""
    branch = _branch(branch_id)
    updated = mark_overdue(branch=branch)
    logger.info('fees.mark_overdue(branch=%s) -> %s', branch_id, updated)
    return {'updated': updated}


def _branch(branch_id):
    """Resolve the id, or None for "every active institution".

    A missing branch raises rather than silently running the job across the
    whole platform: "generate fees for branch 9" and "generate fees for
    everyone" must never be one typo apart.
    """
    if branch_id is None:
        return None

    from branches.models import Branch

    return Branch.objects.get(pk=branch_id)
