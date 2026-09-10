"""Business logic for students and admissions — all of it in transactions.

`admit_student()` is the centrepiece (docs/02 §4.1). One click, several
consequences, all or nothing:

    Application → Student → Enrolment → Guardian → application marked admitted

If any one of those fails, none of them happened. That is not a nicety: an
institution that ends up with a Student who has no Enrolment has a child who is
on the roll, owes no fees, appears in no register, and is discovered in March.

Nothing here is a signal (CLAUDE.md §4.3). A signal fires during `loaddata` and
during test setup, and one that allocates a student ID burns numbers out of a
series that is supposed to be gapless.
"""

import inspect
from datetime import date

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from accounts.models import ActivityAction
from accounts.phone import normalize_bd_phone
from accounts.services import CodedError, Duplicate, log_activity

from core.models import NumberSequence
from core.services import format_number, next_number
from .models import (Admission, AdmissionStatus, Guardian, GuardianRelation,
                     Student, StudentGuardian, StudentStatus)

# ─────────────────────────────────────────────────────────────────────────────
# Number series (CLAUDE.md §4.4)
# ─────────────────────────────────────────────────────────────────────────────

#: The institution-wide student ID series. One scope for the whole platform,
#: because `Student.student_id` is globally unique (docs/03 §4): a per-branch
#: counter would issue SIES-000001 twice on two institutions' opening day.
STUDENT_ID_SCOPE = 'student_id'
STUDENT_ID_PREFIX = 'SIES'


def allocate_student_id():
    """`SIES-000123` — permanent, never reused.

    Six digits because the series is platform-wide and outlives any one
    institution; five would need widening at a hundred thousand students, and
    widening a number people have written on paper is not a migration.
    """
    _n, padded = next_number(branch=None, kind=NumberSequence.Kind.STUDENT, width=6)
    return format_number(prefix=STUDENT_ID_PREFIX, branch=None, number_padded=padded)


def allocate_application_no(branch, session):
    """`APP-DHK-2026-00041` — gapless within (branch, session).

    The session is part of the scope and not just of the string: application 41
    of 2026 and application 41 of 2027 are different applicants, and restarting
    the count each year is what makes the number short enough to say out loud.
    """
    _n, serial = next_number(branch=branch, kind=NumberSequence.Kind.APPLICATION, scope=str(session.pk))
    return f'APP-{branch.code}-{session.name}-{serial}'


# ─────────────────────────────────────────────────────────────────────────────
# The enrolment hand-off
#
# Roll and admission-number allocation belong to `academics` — it owns Enrolment
# and the per-(branch, session) admission-number series — and reimplementing
# either here would give the institution two counters for one number.
#
# Named in settings rather than imported at module scope for the reason
# `core.permissions` names its resolver there (docs/WORKLOG F19): this app must
# import cleanly before `academics` exists, and a test needs to be able to pin a
# stub without building a class, a section and a session first.
# ─────────────────────────────────────────────────────────────────────────────

ENROLMENT_SERVICE_SETTING = 'SIES_ENROLMENT_SERVICE'
DEFAULT_ENROLMENT_SERVICE = 'academics.services.enrol_student'


def enrolment_service():
    """The callable that writes an `academics.Enrolment` and numbers it."""
    dotted = getattr(settings, ENROLMENT_SERVICE_SETTING, DEFAULT_ENROLMENT_SERVICE)
    if callable(dotted):
        return dotted
    try:
        return import_string(dotted)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f'{ENROLMENT_SERVICE_SETTING} names {dotted}, which cannot be imported. '
            'Admission cannot allocate a roll without it.'
        ) from exc


def _call_enrolment_service(**kwargs):
    """Call it with the arguments it actually accepts.

    `academics` is written alongside this app, so its signature is a contract
    across a boundary rather than a local detail. The three arguments without
    which an enrolment has no meaning are always passed, and a mismatch there is
    a loud TypeError as it should be. The optional extras are filtered, so this
    app gaining a flag does not break admission until `academics` catches up.
    """
    service = enrolment_service()
    required = {k: kwargs.pop(k) for k in ('student', 'session', 'academic_class')}

    try:
        parameters = inspect.signature(service).parameters
    except (TypeError, ValueError):
        # A callable with no introspectable signature — a C function or a mock.
        # Pass everything and let it complain if it cannot cope.
        return service(**required, **kwargs)

    takes_anything = any(p.kind is inspect.Parameter.VAR_KEYWORD
                         for p in parameters.values())
    extras = kwargs if takes_anything else {
        k: v for k, v in kwargs.items() if k in parameters
    }
    return service(**required, **extras)


# ─────────────────────────────────────────────────────────────────────────────
# Guardians
# ─────────────────────────────────────────────────────────────────────────────

def link_guardian(*, student, name, phone, relation=GuardianRelation.FATHER,
                  is_primary=True, defaults=None):
    """Attach a guardian to a student, reusing the sibling's row if there is one.

    The match is on (branch, canonical phone) and nothing else. Not on name: the
    same man is written গোলাম রসুল on one form and Golam Rasul on the next, and
    matching on that would create a second guardian for every sibling — which is
    the exact duplication this table exists to prevent. The phone is the SMS
    destination, so it is also the identity that matters operationally.

    An existing guardian is **not** overwritten from the new form. The row on
    file was typed by someone looking at the older child's paperwork; the correct
    place to change an occupation is the guardian screen, not a side effect of
    admitting a second child.
    """
    canonical = normalize_bd_phone(phone) or (phone or '').strip()
    if not canonical:
        raise CodedError(
            'A guardian mobile number is required · অভিভাবকের মোবাইল নম্বর দিতে হবে।',
            'invalid_phone',
        )

    guardian = Guardian.objects.filter(branch=student.branch, phone=canonical).first()
    if guardian is None:
        guardian = Guardian.objects.create(
            branch=student.branch,
            name=name,
            phone=canonical,
            relation=relation,
            **(defaults or {}),
        )

    link, created = StudentGuardian.objects.get_or_create(
        student=student,
        guardian=guardian,
        defaults={'branch': student.branch, 'is_primary': is_primary},
    )

    if is_primary and not link.is_primary:
        # One primary per student is a database constraint, so the old one has to
        # step down in the same transaction or the insert is rejected.
        StudentGuardian.objects.filter(student=student, is_primary=True).exclude(
            pk=link.pk,
        ).update(is_primary=False)
        link.is_primary = True
        link.save(update_fields=['is_primary', 'updated_at'])

    return guardian, link


# ─────────────────────────────────────────────────────────────────────────────
# Applications
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_application(*, branch, session, actor=None, request=None, **fields):
    """Capture an application and give it its gapless number.

    Atomic with the allocation, and that is the whole reason this is a service:
    a number handed out and then not used by a failed insert leaves a hole in a
    series whose only promise is that it has none.
    """
    application = Admission.objects.create(
        branch=branch,
        session=session,
        application_no=allocate_application_no(branch, session),
        created_by=actor if getattr(actor, 'is_authenticated', False) else None,
        **fields,
    )

    log_activity(
        action=ActivityAction.CREATE,
        user=actor, request=request, branch=branch, obj=application,
        model='Admission',
        summary=f'Application {application.application_no} received',
        summary_bn=f'{application.application_no} নম্বর আবেদন গৃহীত হয়েছে',
        atomic=True,
    )
    return application


# The statuses an application may be admitted from. `pending` is included on
# purpose: a small madrasah admits over the counter with no interview step, and
# forcing it through `accepted` first would be ceremony the clerk works around.
ADMITTABLE_STATUSES = {
    AdmissionStatus.PENDING,
    AdmissionStatus.INTERVIEW,
    AdmissionStatus.ACCEPTED,
}


@transaction.atomic
def admit_student(application, *, academic_class=None, section=None, roll=None,
                  stream=None, admitted_on=None, actor=None, request=None,
                  student_fields=None, guardian_fields=None,
                  is_hostel=False, is_transport=False):
    """Turn an accepted application into a Student with an Enrolment.

    Returns `(student, enrolment)`.

    Everything below happens inside one transaction, or none of it does:

      1. the Student, with a freshly allocated permanent `student_id`
      2. the `academics.Enrolment` — class, section, session — numbered by
         `academics`' own service, which owns the roll and admission-number series
      3. the Guardian, reusing a sibling's row when the phone already exists
      4. the application marked `admitted` and pointed at the student
      5. the activity log entry

    Step 5 is `atomic=True`, unlike ordinary CRUD logging: "who admitted this
    student, and when" is the question the log exists to answer for a record that
    then generates fees for years. An admission with no audit row is not an
    acceptable outcome; failing and being retried is.
    """
    if application.status not in ADMITTABLE_STATUSES:
        raise CodedError(
            f'This application is already {application.get_status_display()} · '
            f'এই আবেদনটি ইতিমধ্যে প্রক্রিয়া করা হয়েছে।',
            'invalid_status',
        )
    if application.student_id is not None:
        raise Duplicate(
            'This application has already been admitted · '
            'এই আবেদন থেকে ইতিমধ্যে ভর্তি সম্পন্ন হয়েছে।'
        )

    academic_class = academic_class or application.academic_class
    stream = stream or application.stream
    admitted_on = admitted_on or date.today()
    fields = dict(student_fields or {})

    # 1 ── the person
    student = Student.objects.create(
        branch=application.branch,
        student_id=allocate_student_id(),
        stream=stream,
        name=fields.pop('name', application.applicant_name),
        name_bn=fields.pop('name_bn', application.applicant_name_bn),
        date_of_birth=fields.pop('date_of_birth', application.dob),
        gender=fields.pop('gender', application.gender),
        # Copied box for box from the application, which is why both carry the
        # four structured address fields (docs/07 §4).
        village=fields.pop('village', application.village),
        post_office=fields.pop('post_office', application.post_office),
        upazila=fields.pop('upazila', application.upazila),
        district=fields.pop('district', application.district),
        present_address=fields.pop('present_address', application.address),
        previous_institution=fields.pop('previous_institution',
                                        application.previous_institution),
        previous_class=fields.pop('previous_class', application.previous_class),
        admitted_on=admitted_on,
        status=StudentStatus.ACTIVE,
        created_by=actor if getattr(actor, 'is_authenticated', False) else None,
        **fields,
    )

    # The photo is a file, not a value: assigning the field copies the reference
    # so both rows point at one stored file rather than duplicating the upload.
    if application.photo:
        student.photo = application.photo
        student.save(update_fields=['photo', 'updated_at'])

    # 2 ── the enrolment. Roll and admission number come from academics.
    enrolment = _call_enrolment_service(
        student=student,
        session=application.session,
        academic_class=academic_class,
        section=section,
        roll=roll,
        branch=application.branch,
        enrolled_on=admitted_on,
        is_hostel=is_hostel,
        is_transport=is_transport,
        created_by=actor if getattr(actor, 'is_authenticated', False) else None,
    )

    # 3 ── the guardian, shared with any sibling already on the roll
    link_guardian(
        student=student,
        name=application.guardian_name,
        phone=application.guardian_phone,
        is_primary=True,
        defaults=guardian_fields or {},
    )

    # 4 ── close the application
    application.student = student
    application.status = AdmissionStatus.ADMITTED
    application.processed_by = actor if getattr(actor, 'is_authenticated', False) else None
    application.processed_at = timezone.now()
    application.save(update_fields=['student', 'status', 'processed_by',
                                    'processed_at', 'updated_at'])

    # ── Phase 5 hook — fee invoices ─────────────────────────────────────────
    # docs/02 §4.1: the Admission Fee and the Session Fee are raised here, in
    # THIS transaction, so a student never exists without the invoices that
    # admitting them creates. The call belongs at exactly this point — after the
    # enrolment, which is what says which class's fee structure applies:
    #
    #     from fees.services import raise_admission_fees
    #     raise_admission_fees(enrolment=enrolment, actor=actor)
    #
    # Deliberately not stubbed with a no-op function: an empty implementation
    # would let Phase 5 land without anyone noticing the call site was never
    # wired up. `fees` does not exist yet (CLAUDE.md §8.1 — do not build ahead).

    # 5 ── the audit trail
    log_activity(
        action=ActivityAction.CREATE,
        user=actor, request=request, branch=application.branch, obj=student,
        model='Student',
        summary=(f'Admitted {student.name} ({student.student_id}) '
                 f'from application {application.application_no}'),
        summary_bn=f'{student.name} ({student.student_id}) ভর্তি করা হয়েছে',
        after={
            'student_id': student.student_id,
            'application_no': application.application_no,
            'session': str(application.session),
            'academic_class': str(academic_class),
        },
        atomic=True,
    )

    return student, enrolment


@transaction.atomic
def readmit_student(student, *, session, academic_class, section=None, roll=None,
                    enrolled_on=None, actor=None, request=None,
                    is_hostel=False, is_transport=False):
    """Re-admission into the next session — a new Enrolment, never a new Student.

    docs/02 §4.1, and the reason Enrolment is its own table: a student's identity
    is stable and their class is not. Writing a second Student here would give
    the same child two permanent IDs, split their fee history down the middle,
    and make the brief's "admission history" a guess.
    """
    enrolment = _call_enrolment_service(
        student=student,
        session=session,
        academic_class=academic_class,
        section=section,
        roll=roll,
        branch=student.branch,
        enrolled_on=enrolled_on or date.today(),
        is_hostel=is_hostel,
        is_transport=is_transport,
        created_by=actor if getattr(actor, 'is_authenticated', False) else None,
    )

    if student.status != StudentStatus.ACTIVE:
        # A student who left and came back is active again. Their `admitted_on`
        # is untouched: it records the first admission and nothing else.
        student.status = StudentStatus.ACTIVE
        student.save(update_fields=['status', 'updated_at'])

    log_activity(
        action=ActivityAction.CREATE,
        user=actor, request=request, branch=student.branch, obj=student,
        model='Enrolment',
        summary=f'Re-admitted {student.name} into {academic_class} for {session}',
        summary_bn=f'{student.name}-কে নতুন শিক্ষাবর্ষে ভর্তি করা হয়েছে',
        atomic=True,
    )
    return enrolment


# ─────────────────────────────────────────────────────────────────────────────
# The optional student login (docs/08 D4)
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def enable_student_login(student, *, phone=None, password=None, actor=None, request=None):
    """Give this student an account, or link the one they already have.

    An action on the record, never a step in admission: most young students have
    no phone, and requiring one would mean inventing numbers to get a child onto
    the roll.

    Returns the `User`. The caller is responsible for telling the student the
    password — this does not send it anywhere, because V1 has no SMS gateway
    wired and a password in an activity log is a password everyone can read.
    """
    from accounts.models import User, UserType

    canonical = normalize_bd_phone(phone or student.phone)
    if not canonical:
        raise CodedError(
            'A valid 11-digit mobile number is needed for a login · '
            'লগইনের জন্য সঠিক ১১ সংখ্যার মোবাইল নম্বর দরকার।',
            'invalid_phone',
        )

    if student.user_id is not None:
        return student.user

    existing = User.objects.filter(phone=canonical).first()
    if existing is not None:
        # A phone is globally unique and already identifies somebody. Silently
        # attaching this student to that account would hand them whatever else it
        # can reach — an elder sibling's record, or a teacher's.
        raise Duplicate(
            'That mobile number already has an account · '
            'এই মোবাইল নম্বরে ইতিমধ্যে একটি অ্যাকাউন্ট আছে।'
        )

    user = User.objects.create_user(
        phone=canonical,
        password=password,
        name=student.name,
        name_bn=student.name_bn,
        branch=student.branch,
        user_type=UserType.STUDENT,
        # No password given means one is set by the admin later; either way the
        # student must choose their own before the account is useful.
        must_change_password=True,
    )

    student.user = user
    if not student.phone:
        student.phone = canonical
    student.save(update_fields=['user', 'phone', 'updated_at'])

    log_activity(
        action=ActivityAction.UPDATE,
        user=actor, request=request, branch=student.branch, obj=student,
        model='Student',
        summary=f'Enabled login for {student.name} ({canonical})',
        summary_bn=f'{student.name}-এর জন্য লগইন চালু করা হয়েছে',
        atomic=True,
    )
    return user
