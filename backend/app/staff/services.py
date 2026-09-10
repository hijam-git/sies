"""Number issuing and staff creation (CLAUDE.md §4.3, §4.4).

The counter lives here rather than in each app that needs a number, because
"gapless and never issued twice" is one rule with one implementation. `academics`
imports `next_number` from this module for admission numbers and rolls; nothing
here imports `academics`, which keeps the dependency one-way (docs/06 §2).
"""

from django.db import transaction

from core.models import NumberSequence
from core.services import format_number, next_number
from .models import Employee, Teacher




@transaction.atomic
def generate_teacher_id(branch):
    """`TCH-DHK-0042` — gapless for the life of the institution.

    Not reset per session: a teacher id follows the person for as long as they
    work here, and re-using 0042 for a new teacher five years later would make
    two people's records indistinguishable on a printed attendance sheet.
    """
    _, padded = next_number(
        branch=branch, kind=NumberSequence.Kind.TEACHER, scope='', width=4,
    )
    return format_number(prefix='TCH', branch=branch, number_padded=padded)


@transaction.atomic
def generate_employee_id(branch):
    """`EMP-DHK-0018` — same rule as a teacher id."""
    _, padded = next_number(
        branch=branch, kind=NumberSequence.Kind.EMPLOYEE, scope='', width=4,
    )
    return format_number(prefix='EMP', branch=branch, number_padded=padded)


@transaction.atomic
def create_teacher(*, branch, streams=None, created_by=None, **fields):
    """A teacher, with an id issued in the same transaction.

    Two tables (`Teacher` and the counter) and an M2M, so it is a service and not
    a serializer's `create()` (CLAUDE.md §4.3). The id is issued here rather than
    accepted from the client: a client-chosen id is a client-chosen collision.
    """
    fields.setdefault('teacher_id', generate_teacher_id(branch))
    teacher = Teacher.objects.create(
        branch=branch, created_by=created_by, updated_by=created_by, **fields,
    )
    if streams:
        teacher.streams.set(streams)
    return teacher


@transaction.atomic
def create_employee(*, branch, created_by=None, **fields):
    """An employee, with an id issued in the same transaction."""
    fields.setdefault('employee_id', generate_employee_id(branch))
    return Employee.objects.create(
        branch=branch, created_by=created_by, updated_by=created_by, **fields,
    )


@transaction.atomic
def close_employment(person, *, on_date, status, updated_by=None):
    """Retire a Teacher or Employee row without deleting anything.

    A person leaving is not a delete: their attendance, payroll and — for a
    teacher — the routine and marks they entered all point at this row, and
    `PROTECT` would refuse the delete anyway. Setting `leaving_date` and clearing
    `is_active` keeps the history addressable and takes them out of every picker.

    Works on either model because both carry these fields from `PersonProfile`,
    which is the practical payoff of D5's abstract base.
    """
    person.leaving_date = on_date
    person.employment_status = status
    person.is_active = False
    person.updated_by = updated_by
    person.save(update_fields=[
        'leaving_date', 'employment_status', 'is_active', 'updated_by', 'updated_at',
    ])
    return person
