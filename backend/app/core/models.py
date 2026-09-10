"""The two abstract bases every model in this project inherits (CLAUDE.md §4.1).

A model is either `BranchScopedModel` or explicitly global, and it says so in its
base class. The global list is closed — Branch, User, Role, ActivityLog — and a
new model that is neither is a review failure (docs/01 §5.3).

Money never appears on a base class, but the rule belongs where the model
conventions live: money is `DecimalField(max_digits=12, decimal_places=2)`.
Never `FloatField`, never Python `float`. A binary float cannot represent 0.10,
so a ledger built on one drifts by paisa per row and stops reconciling — and the
first person to notice is a guardian holding a receipt.
"""

from django.conf import settings
from django.db import models

from .managers import BranchScopedManager


class TimeStampedModel(models.Model):
    """Timestamps only — for rows nobody edits by hand.

    ActivityLog is the case this exists for: append-only, written by services
    rather than by a person, so `created_by`/`updated_by` would be dead columns
    (it stores its own `user`). Everything a human creates or edits uses
    `BaseModel` instead.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        # Newest first. Meta.ordering is mandatory on every model (CLAUDE.md
        # §4.2): without it, pagination is nondeterministic and page 2 can repeat
        # a row from page 1. Subclasses override it; none may drop it.
        ordering = ['-created_at']


class BaseModel(TimeStampedModel):
    """Timestamps plus who did it."""

    # SET_NULL, not CASCADE: these are audit references. A staff member who
    # leaves and whose account is deleted must not take the fee receipts and
    # attendance records they entered with them (CLAUDE.md §4.2).
    #
    # related_name='+' because nothing ever asks "what did this user create"
    # across every table at once — that question is ActivityLog's job, and a
    # reverse accessor per model would be dozens of relations nobody uses.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    class Meta(TimeStampedModel.Meta):
        abstract = True


class BranchScopedModel(BaseModel):
    """Everything that belongs to one institution.

    The FK is not nullable. A row with no branch is a row no scoped queryset can
    reach and no institution owns; making it impossible to write is cheaper than
    finding it later.
    """

    # PROTECT, deliberately and permanently. A branch is pointed at by every fee,
    # payment, mark and attendance row it has. Deleting one must fail loudly —
    # CASCADE here would erase an institution's entire financial and academic
    # history from a single admin click. Closing an institution is
    # `is_active=False`, not a delete.
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='%(class)s_set',
    )

    objects = BranchScopedManager()

    class Meta(BaseModel.Meta):
        abstract = True


class NumberSequence(BaseModel):
    """The counter row behind every human-quoted number (CLAUDE.md §4.4).

    Admission numbers, rolls, staff ids, student ids — and later receipt and
    voucher numbers — are sequential, gapless and read out loud across a
    counter. They are issued by incrementing a row here under
    `SELECT … FOR UPDATE`, never by `max(existing) + 1`, which double-issues the
    moment two clerks act in the same second. An admission desk on the first day
    of a session creates exactly that situation.

    It lives in `core` rather than in whichever app happened to need it first:
    four apps issue numbers, and `core` is the only one all of them already
    depend on (docs/06 §2). Three parallel implementations of this table
    appeared during Phase 2 — worklog F23 — which is what a piece of shared
    infrastructure living in a domain app leads to.

    **`branch` is nullable, and the two cases are different on purpose:**

    - `branch` set — per-institution. Receipts, admission numbers and rolls
      belong to one institution and must run 1..n *within it*. A shared counter
      would let Dhaka issuing 412 push Chittagong to 413, and neither set of
      books would read as a sequence.
    - `branch` NULL — platform-wide. `Student.student_id` (`SIES-000123`) is the
      permanent identifier for a person and is globally unique, so a student who
      moves between institutions on this platform keeps it (docs/03 §4).
    """

    class Kind(models.TextChoices):
        ADMISSION = 'admission', 'Admission number · ভর্তি নম্বর'
        ROLL = 'roll', 'Roll · রোল'
        TEACHER = 'teacher', 'Teacher id · শিক্ষক আইডি'
        EMPLOYEE = 'employee', 'Employee id · কর্মচারী আইডি'
        STUDENT = 'student', 'Student id · শিক্ষার্থী আইডি'
        APPLICATION = 'application', 'Application number · আবেদন নম্বর'

    # PROTECT: deleting an institution while its counter still exists would let
    # a fresh counter restart at 1 and re-issue numbers already printed on
    # documents people are holding.
    branch = models.ForeignKey(
        'branches.Branch', null=True, blank=True,
        on_delete=models.PROTECT, related_name='number_sequences',
        help_text='NULL means the counter is platform-wide, not per institution.',
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # The sub-key the counter resets on: a session id for admission numbers,
    # `<class>:<section>` for rolls, empty for one that runs for the life of the
    # institution. A string, so a new kind of number needs no migration.
    scope = models.CharField(max_length=60, blank=True, default='')
    last_number = models.PositiveIntegerField(default=0)

    class Meta(BaseModel.Meta):
        ordering = ['branch', 'kind', 'scope']
        verbose_name = 'number sequence · ক্রমিক নম্বর'
        verbose_name_plural = 'number sequences · ক্রমিক নম্বরসমূহ'
        constraints = [
            # The counter IS the uniqueness guarantee, so exactly one row may
            # exist per counter. Two rows would issue every number twice and the
            # duplicate would surface on a printed receipt.
            #
            # Two constraints, not one, because Postgres treats NULLs as
            # distinct: a single UniqueConstraint over a nullable column would
            # happily allow two platform-wide student-id counters.
            models.UniqueConstraint(
                fields=['branch', 'kind', 'scope'],
                condition=models.Q(branch__isnull=False),
                name='numberseq_unique_per_branch',
            ),
            models.UniqueConstraint(
                fields=['kind', 'scope'],
                condition=models.Q(branch__isnull=True),
                name='numberseq_unique_platform_wide',
            ),
        ]

    def __str__(self):
        where = self.branch_id or 'platform'
        return f'{where}/{self.kind}/{self.scope or "-"} @ {self.last_number}'
