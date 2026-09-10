"""Seeding a new institution's form templates (docs/07 §10).

Called from `branches.services.create_branch()` — **never from a signal**
(CLAUDE.md §4.3): `post_save` fires during `loaddata` and test setup, so every
fixture load would re-seed a branch that already has its rows.

`branches` cannot import this module at module level, because the dependency
runs the other way (`forms` → `branches`, docs/06 §2). The call site imports it
inside the function, the same way the fee and finance seeds are described in
`branches/seeding.py`. The one line to add there is:

    from forms.seeding import seed_form_templates
    created['form_templates'] = seed_form_templates(branch)

Two properties this must keep, exactly as branch seeding keeps them:

**Idempotent.** Matched on the natural key `(branch, form_type, name)`, only
missing rows created. An institution that rewrote its pledges keeps them across
a re-seed; only genuinely new rows appear.

**One transaction.** A half-seeded template — blocks written, questions missing
— renders a form with a silently empty question section, which looks correct and
is not.
"""

import logging

from django.db import transaction

from .models import FormTemplate, Question
from .seed_data import FORM_TEMPLATE_SEEDS, QUESTION_SEEDS

logger = logging.getLogger(__name__)


@transaction.atomic
def seed_form_templates(branch):
    """Create this institution's default form templates and questions.

    Returns `{'form_templates': n, 'questions': n}` so the management command can
    say what it actually did — on a re-run every count is 0, and that is the
    useful output.

    An institution type with no seed data creates nothing rather than raising: a
    school printing no form is usable and can be given its own template, while a
    school printing a madrasah's letter under its name is not.
    """
    templates_created = 0
    default_template = None

    for definition in FORM_TEMPLATE_SEEDS.get(branch.institution_type, []):
        template, was_created = FormTemplate.objects.get_or_create(
            branch=branch,
            form_type=definition['form_type'],
            name=definition['name'],
            defaults={
                'name_bn': definition['name_bn'],
                'blocks': definition['blocks'],
                'paper': definition['paper'],
                'margins': definition['margins'],
                'is_default': definition['is_default'],
                'is_active': True,
            },
        )
        templates_created += int(was_created)
        if definition['form_type'] == 'admission':
            default_template = template

    questions_created = 0
    for definition in QUESTION_SEEDS.get(branch.institution_type, []):
        # Matched on the printed Bangla text, which is the question's natural
        # key on a form: an institution that reworded it has a different
        # question, and re-seeding must not resurrect the old wording next to
        # the new one.
        _question, was_created = Question.objects.get_or_create(
            branch=branch,
            section=definition['section'],
            text_bn=definition['text_bn'],
            defaults={
                'template': default_template,
                'text': definition['text'],
                'type': definition['type'],
                'print_style': definition['print_style'],
                'maps_to': definition.get('maps_to', ''),
                'order': definition['order'],
                'is_active': True,
            },
        )
        questions_created += int(was_created)

    created = {'form_templates': templates_created, 'questions': questions_created}
    logger.info('Seeded forms for branch %s: %s', branch.code, created)
    return created
