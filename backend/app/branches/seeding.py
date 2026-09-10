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
from .seed_data import (EXPENSE_CATEGORY_SEEDS, FEE_CATEGORY_SEEDS,
                        INCOME_CATEGORY_SEEDS, STREAM_SEEDS)

logger = logging.getLogger(__name__)


@transaction.atomic

def _app_installed(label):
    """True when `label` is in INSTALLED_APPS.

    A phase writes an app before it is wired in, and during that window seeding
    would raise `RuntimeError: Model class ... isn't in an application in
    INSTALLED_APPS` from deep inside Django's registry — a failure that says
    nothing about the actual situation. An institution with streams but no fee
    categories yet is a normal intermediate state; a create_branch() that cannot
    run at all is not.
    """
    from django.apps import apps as django_apps
    return django_apps.is_installed(label)


def seed_branch(branch):
    """Create everything a new institution needs. Safe to run again.

    Returns a `{what: how_many_created}` dict so the management command can say
    what it actually did rather than "done" — on a re-run every count is 0, and
    that is the useful output.
    """
    created = {'streams': seed_streams(branch)}

    # The fee heads first: INCOME_CATEGORY_SEEDS names a FeeCategory *code*, and
    # income seeding resolves it against the rows created immediately above.
    #
    # Skipped, not attempted, when the app is not installed yet. A phase writes
    # an app before it is wired in, and during that window this raised
    # RuntimeError from deep inside Django's app registry — a message about
    # app_labels that says nothing about the actual situation. An institution
    # with streams but no fee heads yet is a normal intermediate state; a
    # create_branch() that cannot run at all is not.
    if _app_installed('fees'):
        created['fee_categories'] = seed_fee_categories(branch)
    else:
        logger.info('fees is not installed — skipping its categories for %s', branch.code)

    if _app_installed('finance'):
        created['income_categories'] = seed_income_categories(branch)
        created['expense_categories'] = seed_expense_categories(branch)
    else:
        logger.info('finance is not installed — skipping its categories for %s', branch.code)

    if _app_installed('forms'):
        from forms.seeding import seed_form_templates
        # MERGED, not assigned: seed_form_templates returns its own
        # {templates, questions} dict, and nesting it here made
        # sum(created.values()) add an int to a dict in seed_categories.
        created.update(seed_form_templates(branch))
    else:
        logger.info('forms is not installed — skipping its templates for %s', branch.code)

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


def seed_fee_categories(branch):
    """The eleven heads of docs/03 §7, from FEE_CATEGORY_SEEDS.

    The models are imported **inside** the function, not at module level:
    `branches` must not import `fees` (CLAUDE.md §2 — the dependency runs the
    other way, fees → branches), and a module-level import would invert it and
    turn a one-way arrow into a cycle the next person has to work around.

    `applies_to` is not in the seed rows because it is a *fees* concept: the
    seeds are institution data this app owns, and `SEEDED_APPLIES_TO` is the
    fees app's own statement about which of its heads are hostel- or
    transport-only. Keeping them apart is what lets docs/03 §7's table stay
    readable as a table.
    """
    from fees.models import SEEDED_APPLIES_TO, FeeCategory, default_applies_to

    created = 0
    for definition in FEE_CATEGORY_SEEDS:
        code = definition['code']
        # get_or_create on (branch, code) — exactly the unique constraint, so a
        # concurrent second seed loses the race at the database rather than
        # writing a duplicate. `defaults` means an institution that renamed
        # 'Monthly Fee' to 'বেতন' keeps that edit when this runs again: seeding
        # fills gaps, it never overwrites what the institution decided.
        _, was_created = FeeCategory.objects.get_or_create(
            branch=branch,
            code=code,
            defaults={
                'name': definition['name'],
                'name_bn': definition['name_bn'],
                'note': definition['note'],
                'note_bn': definition['note_bn'],
                'recurrence': definition['recurrence'],
                'is_refundable': definition['is_refundable'],
                'is_mandatory': definition['is_mandatory'],
                'is_system': definition['is_system'],
                'display_order': definition['display_order'],
                'applies_to': SEEDED_APPLIES_TO.get(code, default_applies_to()),
                'is_active': True,
            },
        )
        created += int(was_created)

    return created


def seed_income_categories(branch):
    """The income heads, each linked to the fee category that posts into it.

    **Must run after `seed_fee_categories`.** `INCOME_CATEGORY_SEEDS` carries a
    fee-category *code* rather than an id, and that link is what lets a
    collection write its own income row (docs/03 §8) — an income head seeded
    before its fee category would silently get a null link and every receipt
    under it would land in the catch-all.
    """
    from fees.models import FeeCategory
    from finance.models import IncomeCategory

    fee_categories = {
        category.code: category
        for category in FeeCategory.objects.filter(branch=branch)
    }
    created = 0

    for definition in INCOME_CATEGORY_SEEDS:
        fee_code = definition.get('fee_category')
        _, was_created = IncomeCategory.objects.get_or_create(
            branch=branch,
            code=definition['code'],
            defaults={
                'name': definition['name'],
                'name_bn': definition['name_bn'],
                'note': definition['note'],
                'note_bn': definition['note_bn'],
                'display_order': definition['display_order'],
                'fee_category': fee_categories.get(fee_code) if fee_code else None,
                'is_system': True,
                'is_active': True,
            },
        )
        created += int(was_created)

    return created


def seed_expense_categories(branch):
    """The expense heads of docs/03 §8. No fee link — expenses have no receipts."""
    from finance.models import ExpenseCategory

    created = 0
    for definition in EXPENSE_CATEGORY_SEEDS:
        _, was_created = ExpenseCategory.objects.get_or_create(
            branch=branch,
            code=definition['code'],
            defaults={
                'name': definition['name'],
                'name_bn': definition['name_bn'],
                'note': definition['note'],
                'note_bn': definition['note_bn'],
                'display_order': definition['display_order'],
                'is_system': True,
                'is_active': True,
            },
        )
        created += int(was_created)

    return created
