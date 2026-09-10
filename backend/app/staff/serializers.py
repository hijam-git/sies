"""Shape and validation for the staff API (CLAUDE.md §4.3, §5).

`branch` is never writable here — `BranchScopedViewSet` stamps it from
`request.branch`, and leaving it off the serializer is the second of the two
independent reasons a `branch` in a POST body does nothing (docs/02 §3).

`teacher_id` and `employee_id` are read-only for the same class of reason: they
are issued by `services.next_number()` under a row lock, and a client-chosen id
is a client-chosen collision.
"""

from rest_framework import serializers

from branches.models import Stream
from core.middleware import get_branch

from .models import Employee, Teacher, TeacherQualification

# The `PersonProfile` fields, listed once. Both concrete serializers splice this
# in, so a field added to the abstract base cannot appear on one API and not the
# other — which is the drift D5's abstract base exists to prevent.
PERSON_FIELDS = [
    'user',
    'name', 'name_bn', 'photo',
    'dob', 'gender', 'nid', 'blood_group',
    'phone', 'alt_phone', 'email',
    'village', 'post_office', 'upazila', 'district', 'address',
    'designation', 'joining_date', 'leaving_date', 'employment_status',
    'basic_salary', 'allowances', 'deductions',
    'bank_account', 'mobile_banking',
    'emergency_contact_name', 'emergency_contact_phone',
    'is_active',
]


class PersonProfileSerializerMixin:
    """Validation both staff models need, written once."""

    def validate_user(self, value):
        """A login must belong to this institution.

        Nothing else stops it: `user` is a plain FK to a global table, so without
        this a Dhaka admin could attach a Chittagong account to a Dhaka teacher
        and hand them a login into someone else's institution.
        """
        if value is None:
            return value

        branch = get_branch(self.context['request'])
        branch_id = getattr(branch, 'pk', None)
        if branch_id is None and self.instance is not None:
            branch_id = self.instance.branch_id
        if branch_id is None:
            return value

        if value.branch_id is not None and value.branch_id != branch_id:
            raise serializers.ValidationError(
                'That account belongs to another institution · '
                'ওই অ্যাকাউন্ট অন্য প্রতিষ্ঠানের।'
            )
        return value

    def validate(self, attrs):
        """Leaving cannot precede joining.

        Checked here rather than as a `CheckConstraint`, because both dates are
        nullable and the interesting failure is a typo on a form — which deserves
        a field error, not an integrity error the form cannot attach to an input.
        """
        joining = attrs.get('joining_date', getattr(self.instance, 'joining_date', None))
        leaving = attrs.get('leaving_date', getattr(self.instance, 'leaving_date', None))
        if joining and leaving and leaving < joining:
            raise serializers.ValidationError({
                'leaving_date': 'Leaving cannot be before joining · '
                                'প্রস্থানের তারিখ যোগদানের আগে হতে পারে না।',
            })
        return attrs


class TeacherQualificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherQualification
        fields = ['id', 'teacher', 'degree', 'institution', 'year', 'result',
                  'certificate', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_teacher(self, value):
        branch = get_branch(self.context['request'])
        branch_id = getattr(branch, 'pk', None)
        if branch_id is not None and value.branch_id != branch_id:
            # A 400 rather than a 404: the caller named a teacher, and the honest
            # answer is that this teacher is not theirs to write against. The row
            # itself was never exposed — the teacher list is branch-scoped.
            raise serializers.ValidationError(
                'That teacher belongs to another institution · '
                'ওই শিক্ষক অন্য প্রতিষ্ঠানের।'
            )
        return value


class TeacherSerializer(PersonProfileSerializerMixin, serializers.ModelSerializer):
    """A teacher and everything the staff screens render for one."""

    # Writable as a list of ids, validated against the caller's own branch below.
    # A scoped queryset controls what you can *read*; nothing else would stop a
    # teacher being attached to another institution's stream.
    streams = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Stream.objects.all(), required=False,
    )
    qualifications = TeacherQualificationSerializer(many=True, read_only=True)
    employment_status_display = serializers.CharField(
        source='get_employment_status_display', read_only=True,
    )
    gross_salary = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True,
    )

    class Meta:
        model = Teacher
        fields = [
            'id', 'teacher_id',
            *PERSON_FIELDS,
            'streams', 'is_class_teacher', 'specialization', 'max_weekly_periods',
            'employment_status_display', 'gross_salary', 'qualifications',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'teacher_id', 'created_at', 'updated_at']

    def validate_streams(self, value):
        branch = get_branch(self.context['request'])
        branch_id = getattr(branch, 'pk', None)
        if branch_id is None and self.instance is not None:
            branch_id = self.instance.branch_id
        if branch_id is None:
            return value

        foreign = [stream for stream in value if stream.branch_id != branch_id]
        if foreign:
            raise serializers.ValidationError(
                'Those streams belong to another institution · '
                'ওই শাখাগুলো অন্য প্রতিষ্ঠানের।'
            )
        return value


class EmployeeSerializer(PersonProfileSerializerMixin, serializers.ModelSerializer):
    employment_status_display = serializers.CharField(
        source='get_employment_status_display', read_only=True,
    )
    gross_salary = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True,
    )

    class Meta:
        model = Employee
        fields = [
            'id', 'employee_id',
            *PERSON_FIELDS,
            'department', 'duty_shift',
            'employment_status_display', 'gross_salary',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'employee_id', 'created_at', 'updated_at']
