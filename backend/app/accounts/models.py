"""User, Role and ActivityLog — docs/03 §1.

All three are **global**, not branch-scoped, and the global list is closed
(CLAUDE.md §4.1). `User` is global because a person is one person: a teacher
moving from Dhaka to Chittagong keeps their login and their history, and
duplicating them would fork their attendance and payroll records. `Role` is
global because a preset is platform vocabulary. `ActivityLog` carries a branch
but is not `BranchScopedModel` — a login by a platform admin belongs to no
institution, so the column has to be nullable, and `BranchScopedModel`'s is not.
"""

import logging

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from core.models import BaseModel

from .managers import UserManager
from .phone import INVALID_PHONE_MESSAGE, normalize_bd_phone

logger = logging.getLogger(__name__)


class Language(models.TextChoices):
    """UI and SMS language. Bangla is the default because most users read it."""

    BN = 'bn', 'বাংলা'
    EN = 'en', 'English'


class UserType(models.TextChoices):
    """What kind of person this account belongs to — docs/02 §1.

    Not a permission and not a role. It says which *surface* the account uses
    (staff dashboard vs `/api/me/`) and which profile row it is expected to
    have; what they may DO is `permissions` and `role`. Conflating the two is
    how a system ends up unable to express "a teacher who also collects fees".
    """

    PLATFORM_ADMIN = 'platform_admin', 'Platform Admin'
    PRINCIPAL = 'principal', 'Principal'
    ACCOUNTANT = 'accountant', 'Accountant'
    TEACHER = 'teacher', 'Teacher'
    EMPLOYEE = 'employee', 'Employee'
    STUDENT = 'student', 'Student'
    # Guardians cannot log in in V1 (docs/08 D4). The choice exists so the
    # switch is a settings change and not a migration on a table with rows.
    GUARDIAN = 'guardian', 'Guardian'


class Role(BaseModel):
    """A named permission preset — docs/02 §2, docs/03 §1.

    A role ticks a set of boxes; the boxes are what gets enforced. Changing a
    preset moves everyone still on it and leaves customised people alone
    (docs/02 §2.3), which is what an admin expects and why the matrix lives here
    rather than being copied onto each user at assignment time.
    """

    name = models.CharField(max_length=50, unique=True)
    name_bn = models.CharField(max_length=80, blank=True)

    # {"fees": ["view", "collect"], …}. JSON rather than a join table because it
    # is read whole, written whole, and never queried by its contents — a
    # RolePermission table would be three joins to answer one question.
    permission_matrix = models.JSONField(default=dict, blank=True)

    # System presets ship with the platform and cannot be deleted. An
    # institution that dislikes one deactivates it or edits its matrix; deleting
    # it would orphan every user pointing at it.
    is_system = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'role'
        verbose_name_plural = 'roles'

    def __str__(self):
        return self.name

    @property
    def permissions(self):
        """The preset flattened to `["fees.view", …]`, for the API."""
        from .permissions import flatten

        return sorted(flatten(self.permission_matrix))


class User(AbstractBaseUser, PermissionsMixin):
    """An account. The login is an 11-digit phone number and nothing else.

    `USERNAME_FIELD = 'phone'`, globally unique, canonicalised on save. There is
    no username column and no email login: CLAUDE.md §1 forbids OAuth, and email
    is optional here precisely so it can never quietly become a second
    credential with weaker uniqueness.
    """

    phone = models.CharField(
        max_length=11,
        unique=True,
        # Belt and braces with `normalize_bd_phone`: `save()` canonicalises, and
        # this catches anything written by a data migration or a fixture that
        # bypassed it. The database column is 11 chars, so a non-canonical value
        # cannot fit anyway — the validator makes the failure a sentence instead
        # of a truncation error.
        validators=[RegexValidator(r'^01[3-9]\d{8}$', INVALID_PHONE_MESSAGE)],
        db_index=True,
        help_text='Canonical 01XXXXXXXXX. +88 and dashed forms are accepted and normalised.',
    )

    # One name field, not first/last: Bangladeshi names do not split reliably,
    # and a system that insists produces "Md." in the first-name column
    # (docs/03 §1).
    name = models.CharField(max_length=120)
    name_bn = models.CharField(max_length=120, blank=True)

    # Not unique, and never a credential. Several teachers at one institution
    # legitimately share the office address, and a unique index here would make
    # the second account impossible to create for a reason nobody could see.
    email = models.EmailField(blank=True)

    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.EMPLOYEE,
        db_index=True,
    )

    # NULL means the platform admin, who sees every institution (docs/01 §5.2).
    # PROTECT because deleting an institution while its staff accounts point at
    # it must fail loudly — those accounts own fee receipts and attendance rows.
    branch = models.ForeignKey(
        'branches.Branch',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='users',
        help_text='NULL means a platform admin who sees every institution.',
    )

    # SET_NULL, not PROTECT: deleting a role must not be blocked by, or delete,
    # the people holding it. They fall through to an empty permission set, which
    # is the safe direction — they lose access rather than keeping a preset that
    # no longer exists.
    role = models.ForeignKey(
        Role,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='users',
    )

    # The per-person list of "resource.action" strings. **Empty means fall back
    # to the role preset** (docs/02 §2.3); a non-empty list is the whole truth
    # for this person and is never merged with the preset. `effective_permissions`
    # in permissions.py is the only thing that should read this field.
    #
    # The name does not clash with PermissionsMixin, which defines only
    # `is_superuser`, `groups` and `user_permissions` — checked deliberately,
    # because docs/03 §1 names this field `permissions` and a silent shadow here
    # would break Django's own auth machinery.
    permissions = models.JSONField(default=list, blank=True)

    photo = models.ImageField(upload_to='users/photos/', blank=True, null=True)

    language = models.CharField(max_length=2, choices=Language.choices, default=Language.BN)

    # Deactivation, not deletion, is how someone leaves: their receipts and
    # attendance rows point at them. `effective_permissions` returns an empty set
    # for an inactive user, so switching this off revokes access immediately even
    # if their role still grants everything (docs/WORKLOG F1).
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False,
        help_text='Can sign in to the Django admin. Unrelated to institution staff.',
    )

    # Recorded on every successful login. "Who logged in from where" is the first
    # question asked after a disputed change, and the ActivityLog row carries the
    # same value per event; this column is the cheap "most recent" answer.
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    # True on admin-created accounts: the principal typed a password out loud to
    # hand it over, so it must not stay the password.
    must_change_password = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'phone'
    # `name` only. Adding more here makes `createsuperuser` a longer interview on
    # a server someone is SSH'd into at midnight, and every other field has a
    # sensible default.
    REQUIRED_FIELDS = ['name']

    class Meta:
        ordering = ['name', 'phone']
        verbose_name = 'user'
        verbose_name_plural = 'users'
        indexes = [
            # The two list screens: an institution's staff, and everyone of one
            # kind within it.
            models.Index(fields=['branch', 'is_active'], name='user_branch_active_idx'),
            models.Index(fields=['branch', 'user_type'], name='user_branch_type_idx'),
        ]
        constraints = [
            # A platform admin has no branch; everyone else must have one. Both
            # halves matter: a branch user with a NULL branch would read as a
            # platform admin and see every institution, and a platform_admin
            # pinned to one branch would be scoped to it by the middleware and
            # quietly stop being a platform admin.
            models.CheckConstraint(
                condition=(
                    models.Q(user_type='platform_admin', branch__isnull=True)
                    | (~models.Q(user_type='platform_admin') & models.Q(branch__isnull=False))
                ),
                name='user_platform_admin_has_no_branch',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.phone})'

    def clean(self):
        """Canonicalise before Django's own validation looks at the field."""
        super().clean()
        self.phone = normalize_bd_phone(self.phone)
        if not self.phone:
            raise ValidationError({'phone': INVALID_PHONE_MESSAGE})

    def save(self, *args, **kwargs):
        """Normalise the phone on every write.

        Every path into this table goes through `save()` — the manager, the
        admin, the API, a management command, a shell session — so this is the
        one place that can guarantee the stored value is canonical. Doing it in
        the serializer instead would leave `create_admin` and the Django admin
        writing a form the login screen cannot match.
        """
        canonical = normalize_bd_phone(self.phone)
        if not canonical:
            raise ValidationError({'phone': INVALID_PHONE_MESSAGE})
        self.phone = canonical

        # Kept in step with the branch rule the CheckConstraint enforces, so a
        # user_type change through the admin does not fail at the database with
        # a message nobody can read.
        if self.user_type == UserType.PLATFORM_ADMIN:
            self.branch = None

        super().save(*args, **kwargs)

    @property
    def is_platform_admin(self):
        """Sees every institution (docs/01 §5.2)."""
        return self.branch_id is None

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.name.split(' ')[0] if self.name else self.phone

    @property
    def effective_permissions(self):
        """The permission strings this account actually holds. docs/02 §2.3."""
        from .permissions import effective_permissions

        return sorted(effective_permissions(self))

    def has_resource_permission(self, resource, action):
        from .permissions import has_permission

        return has_permission(self, resource, action)


class ActivityAction(models.TextChoices):
    """What happened. docs/03 §1 plus the money and academic verbs of docs/08 D8.

    `login_failed` is here and `login` is not enough on its own: a run of failed
    attempts against one phone is the only signal this system has that someone is
    guessing a counter clerk's password, and it has to be visible in the same
    feed as everything else.
    """

    CREATE = 'create', 'Created'
    UPDATE = 'update', 'Updated'
    DELETE = 'delete', 'Deleted'
    LOGIN = 'login', 'Logged in'
    LOGIN_FAILED = 'login_failed', 'Failed login'
    COLLECT = 'collect', 'Collected payment'
    WAIVE = 'waive', 'Waived fee'
    PUBLISH = 'publish', 'Published results'
    TAKE_ATTENDANCE = 'take_attendance', 'Took attendance'


class ActivityLog(models.Model):
    """Append-only audit trail — docs/03 §1, docs/08 D8.

    Written by services, **never by signals**: a signal fires during a fixture
    load and during `loaddata`, so a log written from one records events that
    never happened and, worse, records them as nobody (CLAUDE.md §4.3).

    Not a `BaseModel`: `updated_at`, `created_by` and `updated_by` would all be
    dead columns on a table that is never edited and stores its own `user`.

    Powers the platform admin's live feed, polled on a cursor every five seconds
    (docs/08 D8), which is why `id` is the ordering rather than `created_at`:
    two rows written in the same millisecond must still have a strict order, or
    the cursor either skips one or returns it twice forever.
    """

    # SET_NULL: an account can be removed; what it did must not vanish with it.
    # `user_label` keeps the name readable afterwards.
    user = models.ForeignKey(
        'accounts.User',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='activity_logs',
    )
    # Denormalised on purpose. A log row whose user is gone still has to say who
    # it was, and a failed login has no user row at all — only a number that was
    # typed.
    user_label = models.CharField(max_length=160, blank=True)

    # Nullable because a platform-level event (a login by the operator, an
    # institution being created) belongs to no institution. PROTECT for the same
    # reason as everywhere else: deleting an institution must fail loudly rather
    # than silently erase its history.
    branch = models.ForeignKey(
        'branches.Branch',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='activity_logs',
    )

    action = models.CharField(max_length=20, choices=ActivityAction.choices, db_index=True)

    # Strings, not a ContentType FK. The row must survive the model being renamed
    # or removed, and a GenericForeignKey would make the feed query a join per
    # row for a value that is only ever displayed.
    model = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    object_label = models.CharField(max_length=200, blank=True)

    summary = models.CharField(max_length=255, blank=True)
    summary_bn = models.CharField(max_length=255, blank=True)

    # The permission-change case is what these are for: "who gave the office
    # assistant access to the accounts" must have an answer (docs/02 §2.3).
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)

    class Meta:
        ordering = ['-id']
        verbose_name = 'activity log entry'
        verbose_name_plural = 'activity log'
        indexes = [
            models.Index(fields=['-created_at'], name='activity_created_desc_idx'),
            models.Index(fields=['branch', '-created_at'], name='activity_branch_created_idx'),
            models.Index(fields=['user', '-created_at'], name='activity_user_created_idx'),
            # "Everything that ever happened to this fee" — the reason an admin
            # opens the log in the first place.
            models.Index(fields=['model', 'object_id'], name='activity_object_idx'),
        ]

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.user_label} {self.action} {self.model}'

    def save(self, *args, **kwargs):
        """Insert only. An existing row can never be changed.

        A tamper-proof trail is the entire value of this table: if the person who
        deleted a payment can also edit the line that says so, the line proves
        nothing. Enforced here rather than only by a database grant because the
        application connects as the owner and would otherwise be allowed.
        """
        if self.pk is not None:
            raise ValidationError('ActivityLog is append-only; an entry cannot be changed.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Never. Pruning old rows is a deliberate, separate operation.

        `queryset.delete()` bypasses this — Django's bulk delete does not call
        the model method — which is exactly the seam a retention job would use,
        and it has to be written on purpose rather than reached by accident from
        a viewset. `ActivityLogViewSet` is read-only for the same reason.
        """
        raise ValidationError('ActivityLog is append-only; an entry cannot be deleted.')
