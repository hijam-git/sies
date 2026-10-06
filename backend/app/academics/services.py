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

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max

from core.models import NumberSequence
from core.services import format_number, next_number

from .models import (AcademicClass, ClassRoutine, Enrolment, EnrolmentStatus,
                     Section, SubjectAssignment)

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


def routine_access_key(routine):
    """The `SubjectAssignment` a routine cell stands for, as a lookup dict.

    None for a cell that grants nothing — one switched off with `is_active`, or
    (defensively) one missing its teacher or subject. A dict rather than a
    tuple because both callers feed it straight into an ORM filter.
    """
    if (routine is None or not routine.is_active
            or routine.teacher_id is None or routine.subject_id is None):
        return None
    return {
        'branch_id': routine.branch_id,
        'session_id': routine.session_id,
        'teacher_id': routine.teacher_id,
        'subject_id': routine.subject_id,
        'academic_class_id': routine.academic_class_id,
        'section_id': routine.section_id,
    }


def grant_from_routine(routine):
    """Make sure a routine placement carries its own access grant.

    Putting a teacher in a routine cell and *then* being told they cannot open
    the register is the system knowing two things and believing the wrong one.
    A SubjectAssignment is what a teacher's reach is built from (D6), so the
    timetable creates it — the routine is the only screen where an admin says
    who teaches what (D6, 2026-10 update).

    Idempotent, and never widens beyond what the cell already says: same
    session, same class, same section, same subject, same teacher. A row that
    an earlier removal deactivated is switched back on rather than duplicated,
    which the unique constraint would refuse anyway.
    """
    key = routine_access_key(routine)
    if key is None:
        return None

    assignment, created = SubjectAssignment.objects.get_or_create(
        **key, defaults={'is_active': True},
    )
    if not created and not assignment.is_active:
        assignment.is_active = True
        assignment.save(update_fields=['is_active', 'updated_at'])
    return assignment


def revoke_if_uncovered(key):
    """Deactivate the assignment *key* names, unless a routine cell still needs it.

    "Still needs it" is any other **active** routine cell with the same session,
    teacher, subject, class and section — a teacher who takes Arabic in Class 5
    on Saturday and Monday keeps the subject when Monday's cell is deleted.

    Deactivated, never deleted. Nothing references a `SubjectAssignment` — marks
    record who entered them on the `Mark` row itself — but the row is the record
    that this teacher taught this subject this session, and a deactivated row is
    reactivated by `grant_from_routine` when the cell comes back.
    """
    if key is None:
        return 0
    if ClassRoutine.objects.filter(is_active=True, **key).exists():
        return 0
    return SubjectAssignment.objects.filter(is_active=True, **key).update(is_active=False)


@transaction.atomic
def sync_routine_access(*, previous_key, routine=None):
    """Keep `SubjectAssignment` in step with one routine cell's write.

    *previous_key* is `routine_access_key()` of the cell **before** the write
    (None for a create); *routine* is the cell after it (None for a delete). The
    write itself must already be saved, or the cell would count as still
    covering its own old key.

    The routine is the source of truth for subject access (D6, 2026-10 update):
    placing a teacher grants, moving or removing the last cell that places them
    there revokes. Class responsibility — `class_teacher`, `in_charge` — is set on
    the class and section forms and is never touched here.
    """
    granted = grant_from_routine(routine) if routine is not None else None
    if previous_key is not None and previous_key != routine_access_key(routine):
        revoke_if_uncovered(previous_key)
    return granted


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


def roll_scope(*, branch, session, academic_class, section=None):
    """Every enrolment that shares one roll series with the given place.

    The series is per (session, class, section) — exactly what `Enrolment`'s two
    unique constraints enforce, split on whether the student is in a section. A
    class without sections numbers 1, 2, 3 across the whole class; a class with
    them numbers each section from 1. `section=None` filters to IS NULL, which is
    the second constraint's half.

    Each argument may be a model or a primary key. Inactive enrolments are
    included on purpose: a student who left still holds their roll in the
    database, and the constraint counts them.
    """
    return Enrolment.objects.filter(
        branch_id=getattr(branch, 'pk', branch),
        session_id=getattr(session, 'pk', session),
        academic_class_id=getattr(academic_class, 'pk', academic_class),
        section_id=getattr(section, 'pk', section),
    )


def next_roll(*, branch, session, academic_class, section=None):
    """The next free roll in this class/section, for this session.

    Per (session, class, section), which is what `Enrolment`'s unique constraint
    enforces. Usually that is simply the counter's next number — but a roll can
    also arrive from outside the counter: typed in at admission, imported from
    last year's paper register, or changed afterwards with `change_roll()`. A
    counter that did not know about those would hand out a roll somebody
    already holds, and the admission would die at the database as a 500.

    So the number is checked against the class before it is returned, under the
    counter's own row lock, and skipped if taken. On a collision the counter
    jumps straight past the highest roll in the class rather than probing one
    number at a time — an imported class of sixty is one extra query, not sixty.
    """
    scope = f'{session.pk}:{academic_class.pk}:{section.pk if section else 0}'
    taken = roll_scope(branch=branch, session=session,
                       academic_class=academic_class, section=section)
    while True:
        number, _ = next_number(
            branch=branch, kind=NumberSequence.Kind.ROLL, scope=scope, width=3,
        )
        if not taken.filter(roll=number).exists():
            return number
        highest = taken.aggregate(highest=Max('roll'))['highest'] or 0
        if highest > number:
            # Still inside `next_number`'s lock: this transaction holds the
            # counter row until it commits, so nobody is issued a number
            # between this jump and the next reservation.
            NumberSequence.objects.filter(
                branch=branch, kind=NumberSequence.Kind.ROLL, scope=scope,
            ).update(last_number=highest)


class RollTaken(Exception):
    """The roll asked for already belongs to another student in the class.

    Carries the holder so the screen can name them and offer the swap — "roll 3
    belongs to Bilal — swap?" is a question an office clerk can answer; "that
    would duplicate something" is not.
    """

    def __init__(self, holder):
        super().__init__(f'Roll {holder.roll} is taken')
        self.holder = holder


#: The value a row parks on during a swap. Never issued: `next_roll()` starts
#: at 1 and `change_roll()` refuses anything below 1, while the column is a
#: PositiveIntegerField, so 0 is still legal to the database for the instant
#: it is held.
_SWAP_PARKING_ROLL = 0


@transaction.atomic
def change_roll(enrolment, *, roll, swap=False, updated_by=None):
    """Give *enrolment* a new roll within its own class (and section).

    Returns `(enrolment, swapped_with)` — `swapped_with` is the other student's
    enrolment when a swap happened, else None.

    * **The series is the class.** Only rows sharing this enrolment's
      (session, class, section) are read or written, so "roll 3" here means
      roll 3 *in this class*. Class Two's roll 3 is a different number.
    * **Taken, without `swap`:** raises `RollTaken` naming the holder, and
      nothing is written.
    * **Taken, with `swap`:** the two students exchange rolls in one
      transaction. Three writes through a parking value, because the unique
      constraints are checked per statement and are not deferrable — a direct
      exchange would collide with itself halfway through.

    Every enrolment in the series is locked with `SELECT … FOR UPDATE`, in
    primary-key order, before anything is decided. Locking the whole series
    rather than two rows is what makes two clerks renumbering the same class at
    once safe: they queue, instead of each swapping against a holder the other
    has already moved — and the fixed order means they queue rather than
    deadlock.
    """
    try:
        roll = int(roll)
    except (TypeError, ValueError):
        roll = 0
    if roll < 1:
        raise ValidationError({
            'roll': 'A roll is a whole number from 1 · রোল ১ বা তার বেশি হতে হবে।',
        })

    series = roll_scope(
        branch=enrolment.branch_id, session=enrolment.session_id,
        academic_class=enrolment.academic_class_id, section=enrolment.section_id,
    )
    locked = {row.pk: row for row in series.select_for_update().order_by('pk')}
    enrolment = locked[enrolment.pk]

    if enrolment.roll == roll:
        return enrolment, None

    holder = next((row for row in locked.values()
                   if row.roll == roll and row.pk != enrolment.pk), None)

    if holder is None:
        try:
            # A savepoint, so a collision with a row inserted after the lock
            # was taken — an admission allocating that very number — becomes
            # a named answer rather than a broken transaction and a 500.
            with transaction.atomic():
                _set_roll(enrolment, roll, updated_by)
        except IntegrityError:
            holder = series.filter(roll=roll).exclude(pk=enrolment.pk).first()
            if holder is None:
                raise
            raise RollTaken(holder)
        return enrolment, None

    if not swap:
        raise RollTaken(holder)

    previous = enrolment.roll
    _set_roll(enrolment, _SWAP_PARKING_ROLL, updated_by)
    _set_roll(holder, previous, updated_by)
    _set_roll(enrolment, roll, updated_by)
    return enrolment, holder


def _set_roll(enrolment, roll, updated_by):
    enrolment.roll = roll
    enrolment.updated_by = updated_by
    enrolment.save(update_fields=['roll', 'updated_by', 'updated_at'])


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
