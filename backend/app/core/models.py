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
