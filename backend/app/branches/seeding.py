"""Branch seeding — what makes a new institution usable on day one.

Decision 1 of the "smart" list (docs/00 §2). `seed_branch()` reads the branch's
`institution_type` and creates everything that institution needs before anyone
can do any work: its streams now, its fee and finance heads when those apps land
in Phase 5.

Two properties this function must keep, because the deploy scripts and the
onboarding flow both rely on them:

**Idempotent.** `scripts/fresh_deploy.sh` runs `seed_categories` on every fresh
deploy and people re-run it by hand. Running it twice must be a no-op, not a
duplicate set — which is why every row is matched on its natural key
(`branch` + `code`) and only *missing* rows are created. An institution that
renamed its stream to হাফজ keeps that name across a re-seed; only genuinely new
rows appear.

**One transaction.** A half-seeded branch is worse than an unseeded one: a
Stream picker with two of three entries looks correct and is not. Either the
whole set exists or the branch creation rolls back with it.

It is called from `services.create_branch()` and **not** from a `post_save`
signal, deliberately (CLAUDE.md §4.3): a signal fires during fixture loads and
test setup, so every `loaddata` would seed a branch that already has its rows.
"""

import logging

from django.db import transaction

from .models import Stream
from .seed_data import STREAM_SEEDS

logger = logging.getLogger(__name__)


@transaction.atomic
def seed_branch(branch):
    """Create everything a new institution needs. Safe to run again.

    Returns a `{what: how_many_created}` dict so the management command can say
    what it actually did rather than "done" — on a re-run every count is 0, and
    that is the useful output.
    """
    created = {'streams': seed_streams(branch)}

    # ── Phase 5 plugs in here ────────────────────────────────────────────────
    # `fees` and `finance` do not exist yet, so their tables cannot be written.
    # The *data* already does exist, in seed_data.py, because docs/03 §7–§8
    # specifies it and it belongs with the institution rather than with whoever
    # writes those apps months from now.
    #
    # When fees/FeeCategory and finance/{Income,Expense}Category land, add:
    #
    #     created['fee_categories'] = seed_fee_categories(branch)
    #     created['income_categories'] = seed_income_categories(branch)
    #     created['expense_categories'] = seed_expense_categories(branch)
    #
    # each one a get_or_create loop over FEE_CATEGORY_SEEDS /
    # INCOME_CATEGORY_SEEDS / EXPENSE_CATEGORY_SEEDS matched on
    # (branch, code) — the same shape as seed_streams below, for the same
    # idempotency reason. INCOME_CATEGORY_SEEDS carries a `fee_category` code
    # rather than an id, so income seeding resolves it against the fee categories
    # created immediately above and must run after them.
    #
    # Import those models *inside* the seeding function, not at module level:
    # branches must not import fees (CLAUDE.md §2 — the dependency runs the other
    # way, fees → branches), and a module-level import would invert it.
    # ─────────────────────────────────────────────────────────────────────────

    logger.info('Seeded branch %s (%s): %s', branch.code, branch.institution_type, created)
    return created


def seed_streams(branch):
    """The institution's study sectors, per docs/00 §1's table.

    An unknown `institution_type` seeds nothing rather than raising: a branch
    with no streams is usable — its admin adds its own — while a branch that
    could not be created at all is not.
    """
    definitions = STREAM_SEEDS.get(branch.institution_type, [])
    created = 0

    for definition in definitions:
        # get_or_create on (branch, code), which is exactly the unique
        # constraint, so a concurrent second seed loses the race at the database
        # rather than writing a duplicate.
        #
        # `defaults` means an institution that renamed হিফজ to হাফজ, or reordered
        # its pickers, keeps those edits when this runs again. Seeding fills
        # gaps; it never overwrites what the institution decided.
        _, was_created = Stream.objects.get_or_create(
            branch=branch,
            code=definition['code'],
            defaults={
                'name': definition['name'],
                'name_bn': definition['name_bn'],
                'order': definition['order'],
                'is_active': True,
            },
        )
        created += int(was_created)

    return created
