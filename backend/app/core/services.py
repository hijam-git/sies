"""Shared services. Infrastructure every app may call, owned by none of them.

`core` is imported by everything and imports nothing back (docs/06 §2), so this
is the only safe home for behaviour more than one domain app needs.
"""

from django.db import IntegrityError, transaction

from .models import NumberSequence


def next_number(*, branch, kind, scope='', width=5):
    """Reserve and return the next integer for this counter, and its padded form.

    Returns `(number, padded)` — `(417, '00417')`.
    Pass `branch=None` for a platform-wide counter (see `NumberSequence`).

    **Must be called inside an outer `transaction.atomic()`**, and every caller
    does. The row lock taken here is released at commit; a caller that reserved
    a number and then failed to write the row it belongs to would leave a gap,
    and gapless is the whole requirement. Reserving inside the same transaction
    that writes the record makes the two succeed or fail together.

    `get_or_create` followed by a locking re-read, rather than one
    `select_for_update`: the very first number a branch issues has no row to
    lock yet, and two clerks hitting that at once both find nothing. The unique
    constraint decides between them and the loser re-reads.
    """
    lookup = {'branch': branch, 'kind': kind, 'scope': scope or ''}

    # The create needs its OWN atomic block, and this is not a nicety. On
    # Postgres an IntegrityError marks the enclosing transaction as broken, so
    # catching it here without a savepoint would leave the caller's whole
    # admission unable to commit — two clerks starting on the same morning would
    # fail each other's work. The nested block is the savepoint that contains it.
    try:
        with transaction.atomic():
            NumberSequence.objects.get_or_create(**lookup, defaults={'last_number': 0})
    except IntegrityError:
        # Lost the create race. The winner's row exists now, which is all this
        # call needed; the lock below serialises us behind them.
        pass

    # SELECT … FOR UPDATE. Every other transaction wanting this counter blocks
    # here until we commit, so two concurrent admissions are handed 417 and 418
    # rather than 417 twice (CLAUDE.md §4.4 — never `max() + 1`).
    row = NumberSequence.objects.select_for_update().get(**lookup)
    row.last_number += 1
    row.save(update_fields=['last_number', 'updated_at'])

    return row.last_number, str(row.last_number).zfill(width)


def format_number(*, prefix, branch, number_padded, year=None):
    """`ADM-DHK-2026-00417` · `TCH-DHK-0042` · `SIES-000123`.

    The branch code sits in the middle because it is the part a person reads out
    to say which institution issued the document. The year appears only where
    the counter actually resets yearly, so its presence in the string means
    something rather than being decoration.

    `branch=None` yields the platform-wide form, `SIES-000123`, with no
    institution segment — that number belongs to the person, not to a branch.
    """
    parts = [prefix]
    if branch is not None:
        parts.append(branch.code)
    if year is not None:
        parts.append(str(year))
    parts.append(number_padded)
    return '-'.join(parts)
