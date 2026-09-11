"""Split the `finance` permission into `income` and `expenses`.

Every stored `finance.<action>` becomes both `income.<action>` and
`expenses.<action>`, on users' explicit lists and on roles' matrices. Nobody
gains or loses access in this migration: someone who could do a thing to "income
& expense" can still do it to each. Separating the two for a particular person
is then an admin's deliberate act on the permission screen.

Without it, `effective_permissions()` would intersect the stale strings away and
every accountant would silently lose the ledger on deploy — the most dangerous
kind of permission change, because nobody decided it.

The helpers are module-level and pure so the tests can call them directly.
"""

from django.db import migrations

SIDES = ('income', 'expenses')


def split_permissions(permissions):
    """`['finance.view', 'fees.view']` → `['expenses.view', 'fees.view', 'income.view']`."""
    if not isinstance(permissions, list):
        return permissions
    out = set()
    for permission in permissions:
        if isinstance(permission, str) and permission.startswith('finance.'):
            action = permission.split('.', 1)[1]
            out.update(f'{side}.{action}' for side in SIDES)
        else:
            out.add(permission)
    return sorted(out, key=str)


def split_matrix(matrix):
    """`{'finance': ['view']}` → `{'income': ['view'], 'expenses': ['view']}`."""
    if not isinstance(matrix, dict) or 'finance' not in matrix:
        return matrix
    out = {key: value for key, value in matrix.items() if key != 'finance'}
    actions = matrix['finance']
    for side in SIDES:
        existing = out.get(side) or []
        if actions == '*' or existing == '*':
            out[side] = '*'
        else:
            out[side] = sorted(set(existing) | set(actions or []))
    return out


def merge_permissions(permissions):
    """The reverse: both sides holding an action becomes `finance.<action>`."""
    if not isinstance(permissions, list):
        return permissions
    held = set(permissions)
    out = {p for p in held if not (isinstance(p, str) and p.split('.', 1)[0] in SIDES)}
    for permission in held:
        if isinstance(permission, str) and permission.startswith('income.'):
            action = permission.split('.', 1)[1]
            if f'expenses.{action}' in held:
                out.add(f'finance.{action}')
    return sorted(out, key=str)


def merge_matrix(matrix):
    if not isinstance(matrix, dict) or not any(side in matrix for side in SIDES):
        return matrix
    out = {key: value for key, value in matrix.items() if key not in SIDES}
    income = set(matrix.get('income') or [])
    expenses = set(matrix.get('expenses') or [])
    both = sorted(income & expenses)
    if both:
        out['finance'] = both
    return out


def _apply(apps, permissions_fn, matrix_fn):
    User = apps.get_model('accounts', 'User')
    Role = apps.get_model('accounts', 'Role')

    for user in User.objects.exclude(permissions=[]).only('pk', 'permissions'):
        changed = permissions_fn(user.permissions)
        if changed != user.permissions:
            user.permissions = changed
            user.save(update_fields=['permissions'])

    for role in Role.objects.only('pk', 'permission_matrix'):
        changed = matrix_fn(role.permission_matrix)
        if changed != role.permission_matrix:
            role.permission_matrix = changed
            role.save(update_fields=['permission_matrix'])


def forwards(apps, schema_editor):
    _apply(apps, split_permissions, split_matrix)


def backwards(apps, schema_editor):
    _apply(apps, merge_permissions, merge_matrix)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
