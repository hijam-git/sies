"""Academic operations that span more than one table (CLAUDE.md §4.3).

Two families live here:

* **Teacher scoping** (docs/08 D6) — `teacher_class_scope()` answers "which
  classes may this teacher reach", and it is the single definition of that
  question. `viewsets.TeacherScopedMixin` is the only thing that applies it to a
  request; nothing reconstructs the rule inline.
* **Number issuing** (CLAUDE.md §4.4) — admission numbers and rolls, gapless per
  branch and session, reserved under `SELECT … FOR UPDATE` inside the same
  transaction that writes the row they belong to.
"""

from django.db import transaction

from core.models import NumberSequence
from core.services import format_number, next_number

from .models import AcademicClass, Enrolment, EnrolmentStatus, Section, SubjectAssignment

# The Bangladeshi week, indexed the way `DayOfWeek` stores it: Saturday is 0.
# Python's `date.weekday()` puts Monday at 0, so the conversion is a rotation and
# this table is the one place that knows it.
_PY_WEEKDAY_TO_DAY_OF_WEEK = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 0, 6: 1}


def day_index(on_date):
    """A date's `ClassRoutine.day_of_week` value."""
    return _PY_WEEKDAY_TO_DAY_OF_WEEK[on_date.weekday()]


# ─────────────────────────────────────────────────────────────────────────────
# Teacher scoping — docs/08 D6
# ─────────────────────────────────────────────────────────────────────────────

def teacher_for_user(user):
    """The `Teacher` row behind this account, or None.

    Reached through the OneToOne rather than by matching phone numbers: an
    account and a profile are linked deliberately by an admin, and inferring the
    link from a shared phone would hand a teacher's scope to whoever an old
    number was recycled to.
    """
    if user is None or not user.is_authenticated:
        return None
    return getattr(user, 'teacher_profile', None)


def teacher_class_scope(teacher, session=None):
    """The `AcademicClass` ids this teacher may reach (docs/08 D6).

    The union of two things, and both halves matter:

    1. classes and sections they are **responsible** for —
       `AcademicClass.class_teacher` or `Section.in_charge`; and
    2. classes where they hold a **`SubjectAssignment`**.

    A permission answers *what verb*; this answers *which classes*. Without the
    second gate, granting a teacher `attendance.take` lets them mark every class
    in the institution and `marks.enter` lets them enter marks for subjects they
    do not teach — the normal consequence of role-only access control in a school
    system, not a theoretical risk.

    Returns a set of ids rather than a queryset: callers filter three different
    models by it, and a set is evaluated once instead of re-running the union as
    a subquery per call.
    """
    if teacher is None:
        return set()

    own_classes = AcademicClass.objects.filter(
        branch_id=teacher.branch_id, class_teacher=teacher,
    )
    in_charge_of = Section.objects.filter(
        branch_id=teacher.branch_id, in_charge=teacher,
    )
    assigned = SubjectAssignment.objects.filter(
        branch_id=teacher.branch_id, teacher=teacher, is_active=True,
    )

    if session is not None:
        # Scope is per session because AcademicClass is: a teacher who was class
        # teacher of Class 5 in 2026 must not still reach it in 2027, and the
        # 2026 record stays correct forever without a history table.
        own_classes = own_classes.filter(session=session)
        in_charge_of = in_charge_of.filter(academic_class__session=session)
        assigned = assigned.filter(session=session)

    return (
        set(own_classes.values_list('id', flat=True))
        | set(in_charge_of.values_list('academic_class_id', flat=True))
        | set(assigned.values_list('academic_class_id', flat=True))
    )


def teacher_subject_scope(teacher, session=None):
    """The `Subject` ids this teacher may enter marks for.

    Narrower than the class scope on purpose: being class teacher of Class 5
    means seeing its students and taking its daily attendance, not entering its
    mathematics marks (docs/08 D6, the action table).
    """
    if teacher is None:
        return set()

    assigned = SubjectAssignment.objects.filter(
        branch_id=teacher.branch_id, teacher=teacher, is_active=True,
    )
    if session is not None:
        assigned = assigned.filter(session=session)
    return set(assigned.values_list('subject_id', flat=True))


def teacher_scope_applies(user, branch):
    """Whether this request should be narrowed to the caller's own classes.

    Three conditions, all of which must hold:

    * the institution has the switch on — `restrict_teachers_to_assigned_classes`,
      default True. A small madrasah where three teachers cover everything turns
      it off, which is why it is a setting and not a hard rule;
    * the account is of `user_type` **teacher** — principals, accountants and the
      platform admin see the whole institution (D6); and
    * a `Teacher` profile actually exists behind the account. A teacher-typed
      account with no profile has no assignments to scope by, and the safe answer
      is the empty scope rather than the whole institution.

    A superuser is never scoped: `create_admin` makes the first account on a
    fresh install, before any teacher or class exists, and locking it out of its
    own database would make the install unrecoverable.
    """
    if user is None or not user.is_authenticated or getattr(user, 'is_superuser', False):
        return False
    if getattr(user, 'user_type', None) != 'teacher':
        return False
    # `restrict_teachers_to_assigned_classes` is read off the resolved branch.
    # A platform admin's ALL_BRANCHES sentinel is a string with no such
    # attribute — and they are not teacher-typed anyway, so this is belt and
    # braces rather than the real gate.
    return bool(getattr(branch, 'restrict_teachers_to_assigned_classes', False))


# ─────────────────────────────────────────────────────────────────────────────
# Numbers — CLAUDE.md §4.4
# ─────────────────────────────────────────────────────────────────────────────

def next_admission_number(*, branch, session):
    """`ADM-DHK-2026-00417` — gapless per branch and session.

    Must be called inside an outer `transaction.atomic()`; `enrol_student()`
    below is the supported caller. The counter resets per session because that is
    what makes the number readable — "the 417th admission of 2026" — and the year
    in the string is what keeps 2027's 417 from colliding with it.
    """
    _, padded = next_number(
        branch=branch,
        kind=NumberSequence.Kind.ADMISSION,
        scope=str(session.pk),
        width=5,
    )
    return format_number(
        prefix='ADM', branch=branch, number_padded=padded,
        year=session.starts_on.year,
    )


def next_roll(*, branch, session, academic_class, section=None):
    """The next roll in this class/section, for this session.

    Per (session, class, section), which is what `Enrolment`'s unique constraint
    enforces — so a roll issued here and a roll typed in by an admin cannot
    collide silently; the second one fails at the database.
    """
    scope = f'{session.pk}:{academic_class.pk}:{section.pk if section else 0}'
    number, _ = next_number(
        branch=branch, kind=NumberSequence.Kind.ROLL, scope=scope, width=3,
    )
    return number


@transaction.atomic
def enrol_student(*, branch, student, session, academic_class, enrolled_on,
                  section=None, roll=None, admission_number=None,
                  is_hostel=False, is_transport=False, created_by=None):
    """Put a student into a class for a session, with a roll and an admission number.

    One transaction for all three writes (two counter rows and the enrolment).
    That is what makes the numbers gapless: a reserved number whose enrolment
    then failed to save would leave a hole, and the counter and the row commit or
    roll back together.

    `roll` and `admission_number` may be supplied — an institution importing last
    year's register on paper has its own numbers and they must be preserved
    exactly. Only the generated path touches the counter, so importing does not
    advance it past numbers that were never issued here.
    """
    if admission_number is None:
        admission_number = next_admission_number(branch=branch, session=session)
    if roll is None:
        roll = next_roll(
            branch=branch, session=session,
            academic_class=academic_class, section=section,
        )

    return Enrolment.objects.create(
        branch=branch,
        student=student,
        session=session,
        academic_class=academic_class,
        section=section,
        roll=roll,
        admission_number=admission_number,
        status=EnrolmentStatus.ACTIVE,
        enrolled_on=enrolled_on,
        is_hostel=is_hostel,
        is_transport=is_transport,
        created_by=created_by,
        updated_by=created_by,
    )


@transaction.atomic
def close_enrolment(enrolment, *, on_date, status, updated_by=None):
    """End an enrolment without deleting it.

    Fees, marks and a year of attendance point at this row, and `PROTECT` would
    refuse the delete anyway. Setting `left_on` and clearing `is_active` keeps the
    history addressable and takes the student out of every class roster.
    """
    enrolment.left_on = on_date
    enrolment.status = status
    enrolment.is_active = False
    enrolment.updated_by = updated_by
    enrolment.save(update_fields=[
        'left_on', 'status', 'is_active', 'updated_by', 'updated_at',
    ])
    return enrolment


@transaction.atomic
def promote_enrolment(enrolment, *, to_class, session, enrolled_on,
                      section=None, updated_by=None):
    """Move a student into the next class for a new session.

    A new `Enrolment` row, never an edit of the old one: the old row is the
    student's 2026 record and every fee and mark under it must keep pointing at
    the class they were actually in.

    The new row gets a **new** admission number, because the number is per
    (branch, session) by docs/03 §3 and unique per branch — carrying the old one
    forward would break that constraint on the second promotion. The permanent,
    institution-wide identifier for the person is `Student.student_id`, which is
    what a testimonial quotes.
    """
    close_enrolment(
        enrolment, on_date=enrolled_on,
        status=EnrolmentStatus.PROMOTED, updated_by=updated_by,
    )
    return enrol_student(
        branch=enrolment.branch,
        student=enrolment.student,
        session=session,
        academic_class=to_class,
        section=section,
        enrolled_on=enrolled_on,
        is_hostel=enrolment.is_hostel,
        is_transport=enrolment.is_transport,
        created_by=updated_by,
    )
