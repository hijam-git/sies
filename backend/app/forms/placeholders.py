"""The closed placeholder set, and the resolver behind it (docs/07 §4).

A prose block is template text with `{{group.name}}` holes in it:

    বিনীত নিবেদন এই যে, আমি {{student.name_bn}} ইবনে/বিনতে {{guardian.father_name_bn}}
    ইলমে দ্বীন শিক্ষার উদ্দেশ্যে আপনার মাদরাসার সকল নিয়ম কানুন মেনে ভর্তি হতে ইচ্ছুক।

**The set is closed, and an unknown name is a validation error when the TEMPLATE
IS SAVED — never a silent blank at print time.** That is the whole design of
this module. The alternative fails in the worst possible place: a typo like
`{{student.namebn}}` renders as an empty rule, which looks *exactly* like a
deliberate blank, so nobody notices until a stack of two hundred forms has been
printed with the applicant's name missing and the season is over.

Resolution is deliberately total: every known name resolves to a string, and an
absent value resolves to `''` rather than raising. That is what makes one
template serve both outputs (§7) — blank mode is simply the filled renderer with
an empty context, so the two can never drift.
"""

import re

from django.core.exceptions import ValidationError

# `{{ name }}` with optional inner whitespace. Deliberately not a general
# template language: a form is a document, and letting an editor write logic
# into one means the printed page can differ from the preview.
PLACEHOLDER_RE = re.compile(r'\{\{\s*([a-z_]+\.[a-z_]+)\s*\}\}')

# docs/07 §4, exactly — the table the editor's picker is generated from, so the
# offered list and the validated list cannot drift.
PLACEHOLDER_GROUPS = {
    'Institution · প্রতিষ্ঠান': [
        'branch.name', 'branch.name_bn', 'branch.name_ar', 'branch.address_bn',
        'branch.established_year', 'branch.head_title',
    ],
    'Form · ফরম': [
        'form.form_no', 'form.date', 'form.admission_no', 'form.session',
        'form.is_residential', 'form.is_new_student',
    ],
    'Student · শিক্ষার্থী': [
        'student.name', 'student.name_bn', 'student.dob', 'student.gender',
        'student.mobile', 'student.photo', 'student.birth_certificate_no',
    ],
    'Guardian · অভিভাবক': [
        'guardian.father_name_bn', 'guardian.mother_name_bn', 'guardian.phone',
        'guardian.occupation', 'guardian.nid',
    ],
    'Address · ঠিকানা': [
        'address.village', 'address.post_office', 'address.upazila',
        'address.district',
    ],
    'Academic · শিক্ষা': [
        'class.name_bn', 'class.applied_for', 'previous.institution',
        'previous.class',
    ],
}

KNOWN_PLACEHOLDERS = {name for names in PLACEHOLDER_GROUPS.values() for name in names}


def placeholders_in(text):
    """Every placeholder name appearing in *text*, in order of appearance."""
    return PLACEHOLDER_RE.findall(text or '')


def validate_text(text, *, where=''):
    """Raise if *text* uses a placeholder outside the closed set.

    The message names the offender and the nearest legal alternatives, because
    the person who hits this is an office administrator editing a pledge, not a
    developer reading a traceback.
    """
    unknown = [name for name in placeholders_in(text) if name not in KNOWN_PLACEHOLDERS]
    if not unknown:
        return

    location = f'{where}: ' if where else ''
    raise ValidationError(
        f'{location}unknown placeholder(s) {", ".join(sorted(set(unknown)))} · '
        f'অজানা প্লেসহোল্ডার। '
        f'Allowed: {", ".join(sorted(KNOWN_PLACEHOLDERS))}'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Resolving a context
# ─────────────────────────────────────────────────────────────────────────────

def _text(value):
    """A printable string for anything a model field can hold.

    None and empty become `''`, which the renderer prints as a blank rule. Dates
    are ISO because a form is a legal-ish document and `05/06/2026` is ambiguous
    between two countries reading the same page.
    """
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'হ্যাঁ' if value else 'না'
    return str(value)


def build_context(*, branch=None, admission=None, student=None, printed_form=None,
                  extra=None):
    """The flat `{'student.name_bn': 'রহিম'}` dict the renderer resolves against.

    Reads the **admission** first and the linked **student** second, and that
    order is deliberate: the form is filled in *before* a Student row exists
    (docs/02 §4.1 — most applications are never admitted), so the application is
    the authoritative source for a form printed at application time. Once the
    student exists, their corrected record wins for the fields they carry, which
    is what a form printed after admission should show.

    Every known name is present in the result, even when empty, so the renderer
    never has to distinguish "no such field" from "not filled in" — the first is
    already impossible by the time we get here (validation on save), and the
    second is exactly what prints as a rule.
    """
    student = student or getattr(admission, 'student', None)
    context = {name: '' for name in KNOWN_PLACEHOLDERS}

    if branch is None:
        branch = getattr(admission, 'branch', None) or getattr(student, 'branch', None)

    if branch is not None:
        context.update({
            'branch.name': _text(branch.name),
            'branch.name_bn': _text(branch.name_bn),
            'branch.name_ar': _text(branch.name_ar),
            'branch.address_bn': _text(branch.address_bn or branch.address),
            'branch.established_year': _text(branch.established_year),
            # Not a Branch column: what the head of an institution is called
            # differs by institution type (মুহতামিম in a madrasah, প্রধান শিক্ষক in
            # a school) and it is the *title* the letter is addressed to, not the
            # person. Overridable per template through `extra`.
            'branch.head_title': _head_title(branch),
        })

    if admission is not None:
        context.update({
            'form.admission_no': _text(admission.application_no),
            'form.session': _text(getattr(admission.session, 'name', '')),
            'student.name': _text(admission.applicant_name),
            'student.name_bn': _text(admission.applicant_name_bn),
            'student.dob': _text(admission.dob),
            'student.gender': _text(admission.get_gender_display()),
            'student.mobile': _text(admission.guardian_phone),
            'guardian.father_name_bn': _text(admission.guardian_name),
            'guardian.phone': _text(admission.guardian_phone),
            'address.village': _text(admission.village),
            'address.post_office': _text(admission.post_office),
            'address.upazila': _text(admission.upazila),
            'address.district': _text(admission.district),
            'class.applied_for': _text(getattr(admission.academic_class, 'name_bn', '')
                                       or getattr(admission.academic_class, 'name', '')),
            'previous.institution': _text(admission.previous_institution),
            'previous.class': _text(admission.previous_class),
        })

    if student is not None:
        # Only the fields the student record actually owns. A blank on the
        # student must not wipe out what the application said — the application
        # is what the guardian wrote and signed.
        for name, value in [
            ('student.name', student.name),
            ('student.name_bn', student.name_bn),
            ('student.dob', student.date_of_birth),
            ('student.gender', student.get_gender_display()),
            ('student.mobile', student.phone),
            ('student.photo', getattr(student.photo, 'url', '') if student.photo else ''),
            ('student.birth_certificate_no', student.birth_certificate_no),
            ('address.village', student.village),
            ('address.post_office', student.post_office),
            ('address.upazila', student.upazila),
            ('address.district', student.district),
            ('previous.institution', student.previous_institution),
            ('previous.class', student.previous_class),
        ]:
            if value:
                context[name] = _text(value)

        guardian = student.primary_guardian
        if guardian is not None:
            context['guardian.father_name_bn'] = _text(guardian.name_bn or guardian.name)
            context['guardian.phone'] = _text(guardian.phone)
            context['guardian.occupation'] = _text(guardian.occupation)
            context['guardian.nid'] = _text(guardian.nid)

    if printed_form is not None:
        context['form.form_no'] = _text(printed_form.form_no)
        context['form.date'] = _text(
            printed_form.printed_at.date() if printed_form.printed_at else '',
        )

    if extra:
        context.update({key: _text(value) for key, value in extra.items()
                        if key in KNOWN_PLACEHOLDERS})

    return context


def _head_title(branch):
    """What the application letter addresses. docs/08 D1: nothing is hard-coded
    to a madrasah, so this switches on `institution_type`."""
    return {
        'madrasah': 'মুহতামিম',
        'school': 'প্রধান শিক্ষক',
        'college': 'অধ্যক্ষ',
    }.get(getattr(branch, 'institution_type', ''), 'প্রধান')


def resolve(text, context):
    """Substitute placeholders in *text* from *context*.

    Returns `(parts)` — a list of `('text', str)` and `('value', name, value)`
    tuples — rather than a finished string, because the renderer prints a
    resolved value **underlined, sitting on a rule** and an unresolved one as an
    empty rule of the same width (§4). A plain string substitution would lose
    the distinction that makes a printed form still read as a form.
    """
    parts = []
    position = 0
    for match in PLACEHOLDER_RE.finditer(text or ''):
        if match.start() > position:
            parts.append(('text', text[position:match.start()]))
        name = match.group(1)
        parts.append(('value', name, context.get(name, '')))
        position = match.end()
    if position < len(text or ''):
        parts.append(('text', text[position:]))
    return parts
