"""Shape and validation for the accounts API.

Nothing here writes beyond the obvious (CLAUDE.md §4.3): the permission change,
the password change and the login all go through `services.py`, because each has
an audit entry that has to be written with it.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import ActivityLog, Role, User, UserType
from .permissions import (PERMISSION_CATALOG, PLATFORM_ROLE_NAMES, ROLE_NAMES_BN,
                          ROLE_PRESETS, VALID_PERMISSIONS, clean_permissions,
                          effective_permissions, preset_for)
from .phone import INVALID_PHONE_MESSAGE, normalize_bd_phone


class PhoneField(serializers.CharField):
    """A phone that is canonical by the time anything else sees it.

    Normalising in the field rather than in each serializer means the uniqueness
    check downstream compares canonical against canonical — otherwise
    `+8801712345678` passes the "already taken" test against a stored
    `01712345678` and fails at the database instead, as a 500.
    """

    default_error_messages = {'invalid': INVALID_PHONE_MESSAGE}

    def to_internal_value(self, data):
        raw = super().to_internal_value(data)
        canonical = normalize_bd_phone(raw)
        if not canonical:
            self.fail('invalid')
        return canonical


class LoginSerializer(serializers.Serializer):
    """Phone + password. Nothing else is ever a credential (CLAUDE.md §1).

    `phone` is a plain CharField here, not `PhoneField`: a badly formatted number
    must answer with the `invalid_phone` code (docs/WORKLOG F15), and a field
    error would arrive as `validation_error` instead. `login_user` decides.
    """

    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Your current password is not correct.')
        return value

    def validate_new_password(self, value):
        # Django's own validators (length, common passwords, all-numeric), so the
        # rules match what `createsuperuser` and the admin already enforce and
        # there is only one place to raise the bar.
        try:
            validate_password(value, self.context['request'].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class RoleSerializer(serializers.ModelSerializer):
    """A preset. `permissions` is the flattened matrix, for the checkbox screen."""

    permissions = serializers.SerializerMethodField()
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Role
        fields = ['id', 'name', 'name_bn', 'permission_matrix', 'permissions',
                  'is_system', 'is_active', 'user_count', 'created_at', 'updated_at']
        read_only_fields = ['is_system', 'created_at', 'updated_at']

    def get_permissions(self, obj):
        return obj.permissions

    def validate_permission_matrix(self, value):
        """Drop anything the catalogue does not describe.

        A matrix is stored as `{resource: [actions]}` but validated as flat
        strings, so one list — `VALID_PERMISSIONS` — is the only definition of
        what is real. An unknown action silently kept here would show as ticked
        on the role screen and grant nothing.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError('Expected an object of resource → actions.')

        cleaned = {}
        for resource, actions in value.items():
            if not isinstance(actions, (list, tuple)):
                raise serializers.ValidationError(
                    {resource: 'Expected a list of actions.'})
            kept = [a for a in actions
                    if isinstance(a, str) and f'{resource}.{a}' in VALID_PERMISSIONS]
            if kept:
                cleaned[resource] = sorted(set(kept))
        return cleaned

    def update(self, instance, validated_data):
        # A system preset's NAME is what code and seeds refer to; its matrix is
        # the institution's to adjust. Letting the name change would leave
        # `seed_roles` creating a second copy on the next deploy.
        if instance.is_system:
            validated_data.pop('name', None)
        return super().update(instance, validated_data)



class UserSerializer(serializers.ModelSerializer):
    """The staff account list and detail.

    `permissions` on the model is the raw explicit list; `effective_permissions`
    is what is enforced. Both are exposed, because the permission screen needs to
    distinguish "customised" from "on their role's preset" — that is the whole
    difference docs/02 §2.3 turns on, and a single merged field would hide it.
    """

    phone = PhoneField(max_length=20)
    password = serializers.CharField(write_only=True, required=False,
                                     trim_whitespace=False, allow_blank=False)
    effective_permissions = serializers.SerializerMethodField()
    has_teacher_profile = serializers.SerializerMethodField()
    role_name = serializers.CharField(source='role.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'phone', 'name', 'name_bn', 'email', 'user_type',
            'branch', 'branch_name', 'role', 'role_name',
            'permissions', 'effective_permissions', 'has_teacher_profile',
            'photo', 'language', 'is_active', 'must_change_password',
            'password', 'last_login', 'created_at', 'updated_at',
        ]
        read_only_fields = ['last_login', 'created_at', 'updated_at']
        # Never accepted from the client, even by a platform admin. The branch is
        # stamped server-side from `request.branch` (CLAUDE.md §1) — a branch id
        # in a POST body must not be able to write an account into an institution
        # the caller cannot read.
        extra_kwargs = {'branch': {'read_only': True}}

    def get_effective_permissions(self, obj):
        return sorted(effective_permissions(obj))

    def validate_permissions(self, value):
        return clean_permissions(value)

    def validate_phone(self, value):
        """Canonical-vs-canonical uniqueness, with the row's own value excluded."""
        qs = User.objects.filter(phone=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('This number already has an account.')
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def get_has_teacher_profile(self, obj):
        # A teacher-typed login sees only the classes of the Teacher record it
        # is linked to (academics.services.teacher_scope_applies). Unlinked, that
        # is no classes: it can add a student and never list one. The accounts
        # screen flags it instead of leaving it to be discovered.
        return hasattr(obj, 'teacher_profile')

    def validate(self, attrs):
        user_type = attrs.get('user_type', getattr(self.instance, 'user_type', None))
        role = attrs['role'] if 'role' in attrs else getattr(self.instance, 'role', None)
        if (role is not None and role.name in PLATFORM_ROLE_NAMES
                and user_type != UserType.PLATFORM_ADMIN):
            raise serializers.ValidationError({
                'role': (f'"{role.name}" is for accounts that work across every '
                         'institution. Choose user type Platform admin, or a role '
                         'for one institution such as Principal · '
                         'এই ভূমিকা সব প্রতিষ্ঠানের অ্যাকাউন্টের জন্য; '
                         'এক প্রতিষ্ঠানের জন্য যেমন অধ্যক্ষ বেছে নিন।'),
            })
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        # An account made by an admin has a password somebody said out loud in
        # order to hand it over, so it must not stay the password.
        validated_data.setdefault('must_change_password', True)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            # No usable password: the admin creates the account now and sets the
            # password when the person is in front of them. `set_unusable_password`
            # means no string can ever authenticate against it in the meantime.
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
            instance.must_change_password = True
        instance.save()
        return instance


class UserPermissionsSerializer(serializers.Serializer):
    """The body of `POST /api/accounts/users/<id>/permissions/`.

    A list, always — including the empty list, which is not "no change" but
    "put them back on their role's preset" (docs/02 §2.3).
    """

    permissions = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=True,
    )


class ActivityLogSerializer(serializers.ModelSerializer):
    """Read-only. The table is append-only and the viewset offers no writes."""

    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = ActivityLog
        fields = ['id', 'user', 'user_label', 'branch', 'branch_name', 'action',
                  'model', 'object_id', 'object_label', 'summary', 'summary_bn',
                  'before', 'after', 'ip', 'user_agent', 'created_at']
        read_only_fields = fields


def permission_catalog_payload():
    """What `GET /api/accounts/permission-catalog/` returns.

    The catalogue AND the presets, in one response, so the SPA's checkbox screen
    is generated from the backend and cannot drift from what is enforced
    (docs/02 §2). Two round trips would let a client cache one and not the other.
    """
    return {
        'resources': PERMISSION_CATALOG,
        'presets': [
            {
                'name': name,
                'name_bn': ROLE_NAMES_BN.get(name, ''),
                'permissions': preset_for(name),
            }
            for name in ROLE_PRESETS
        ],
    }
