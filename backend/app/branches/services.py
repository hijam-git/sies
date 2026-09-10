"""Multi-step operations on an institution (CLAUDE.md §4.3).

Two things live here because both span more than one table and must not half
happen: creating an institution, and moving which session is current.
"""

from django.db import transaction

from .models import Branch, Session
from .seeding import seed_branch


@transaction.atomic
def create_branch(*, created_by=None, **fields):
    """Create an institution and everything it needs to be usable.

    docs/08 D1 consequence 2: onboarding an institution is a first-class flow —
    *one screen, one transaction* — not an admin task followed by a checklist
    somebody has to remember. A branch that exists but has no streams cannot
    take a single admission, so the two happen together or neither does.

    Seeding is called from here rather than from a `post_save` signal on purpose
    (CLAUDE.md §4.3). A signal fires during `loaddata` and test setup, where the
    rows already exist in the fixture; the seed would then run against every
    branch anyone ever loads.
    """
    branch = Branch.objects.create(created_by=created_by, updated_by=created_by, **fields)
    seed_branch(branch)
    return branch


@transaction.atomic
def set_current_session(session):
    """Make *session* the current one, and no other for its streams.

    docs/03 §2 requires *at most one current session per (branch, stream)*, and
    that cannot be a database constraint: the pair spans the `Session.streams`
    join table, and neither `UniqueConstraint` nor `CheckConstraint` can reach
    through a many-to-many. So it is enforced here, and this is the only
    supported way to raise the flag.

    The rule is per stream rather than per branch because a madrasah may run the
    Hijri year for its qaumi stream and the Gregorian for its general one — two
    sessions current at once, legitimately, as long as they do not overlap on a
    stream.

    A session with no streams is treated as covering the whole institution:
    that is what "this session applies to everything" means, and it clears every
    other current session in the branch.
    """
    stream_ids = list(session.streams.values_list('id', flat=True))

    clashing = Session.objects.filter(
        branch=session.branch, is_current=True,
    ).exclude(pk=session.pk)

    if stream_ids:
        # Only sessions that share at least one stream. `.distinct()` because a
        # join across the M2M repeats a session once per shared stream.
        clashing = clashing.filter(streams__in=stream_ids).distinct()

    # An UPDATE over the ids rather than over the joined queryset: Postgres
    # refuses an UPDATE whose queryset carries a join, and materialising the ids
    # first keeps this one statement inside the transaction.
    Session.objects.filter(pk__in=list(clashing.values_list('pk', flat=True))).update(
        is_current=False,
    )

    session.is_current = True
    session.save(update_fields=['is_current', 'updated_at'])

    # The branch's default for new records follows the session that was just
    # made current — otherwise an admin opening 2027 would still be admitting
    # students into 2026, and would not find out until the fee report.
    branch = session.branch
    if branch.current_session_id != session.pk:
        branch.current_session = session
        branch.save(update_fields=['current_session', 'updated_at'])

    return session
