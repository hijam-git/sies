"""The one branch check every write needs (CLAUDE.md §5).

A branch-scoped queryset decides what a caller can **read**. Nothing about a
plain `PrimaryKeyRelatedField` stops them **writing** a pointer at somebody
else's row: `POST /api/fees/` naming another institution's student creates an
invoice in my branch against their child, and `collect/` then takes money on it
and posts the income. The row was never readable; it did not need to be.

`students` and `academics` each grew their own version of this check, field by
field, and the modules that did not grow one — fees, finance, staff — were open.
So it is written once here, and applied to whole serializers rather than to
remembered fields: `BranchSafeSerializer` walks everything `validate()` is
handed and rejects any related object whose `branch_id` is not the caller's.
A field added later is covered by default, which is the property the per-field
version could never have.
"""

from django.db.models import Model
from rest_framework import serializers

from .middleware import get_branch

FOREIGN = 'That belongs to another institution · এটি অন্য প্রতিষ্ঠানের।'


def request_branch_id(serializer):
    """The institution this write belongs to, or None if it cannot be told.

    `get_branch()` and never `request.branch`: the latter is a `SimpleLazyObject`
    and an `is None` check against it passes for everyone (CLAUDE.md §5).

    A platform admin's `?branch=` arrives as a **string**, which is the trap the
    earlier per-module copies fell into — `getattr(branch, 'pk', None)` returned
    None for `'5'`, the guard decided it could not tell, and every FK went
    unchecked for exactly the account that can reach every institution.
    """
    request = serializer.context.get('request')
    branch = get_branch(request) if request is not None else None

    if hasattr(branch, 'pk'):
        return branch.pk
    if isinstance(branch, str) and branch.isdigit():
        return int(branch)
    # ALL_BRANCHES, or a scope that cannot be resolved: fall back to the row
    # being edited, so a platform admin patching an existing row is still
    # checked against *that row's* institution rather than against nothing.
    return getattr(serializer.instance, 'branch_id', None)


def check_same_branch(serializer, value, message=FOREIGN):
    """Reject a single related row belonging to another institution."""
    if value is None:
        return value
    branch_id = request_branch_id(serializer)
    if branch_id is not None and getattr(value, 'branch_id', branch_id) != branch_id:
        raise serializers.ValidationError(message)
    return value


def foreign_fields(serializer, attrs, branch_id=None):
    """The names in `attrs` pointing at another institution's rows.

    Handles the many-to-many case too (`Teacher.streams`), which arrives as a
    list of model instances.
    """
    if branch_id is None:
        branch_id = request_branch_id(serializer)
    if branch_id is None:
        return []

    def foreign(row):
        # `branch_id` missing means a global table — `User`, `Branch`, `Role`
        # (CLAUDE.md §4.1) — and those are checked where the rule is specific,
        # not here. A NULL branch is likewise not another institution's.
        related = getattr(row, 'branch_id', None)
        return related is not None and related != branch_id

    wrong = []
    for name, value in attrs.items():
        if isinstance(value, Model):
            if foreign(value):
                wrong.append(name)
        elif isinstance(value, (list, tuple)):
            if any(isinstance(row, Model) and foreign(row) for row in value):
                wrong.append(name)
    return wrong


class BranchSafeSerializer(serializers.ModelSerializer):
    """A `ModelSerializer` no write can point out of its own institution.

    Inherit it instead of `ModelSerializer` anywhere a branch-scoped model is
    written. Subclasses overriding `validate()` must call `super().validate()` —
    the same contract DRF already asks for.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        wrong = foreign_fields(self, attrs)
        if wrong:
            raise serializers.ValidationError({field: FOREIGN for field in wrong})
        return attrs
