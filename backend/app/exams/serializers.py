"""Shape and validation for the exams API (CLAUDE.md §4.3).

`branch` is never writable anywhere in this module. `BranchScopedViewSet` stamps
it from `request.branch`, and leaving the field off every serializer is the
second of the two independent reasons a `branch` in a POST body does nothing.

The other rule carried here, the same one the students serializers carry: **a
scoped queryset controls what you can READ and stops nothing you WRITE.** Every
FK below is checked against the caller's own institution in a `validate_*`, or
the API would happily let a Dhaka clerk schedule a paper against Chittagong's
subject and file marks under it.
"""

from rest_framework import serializers

from core.middleware import get_branch

from .models import Exam, ExamClass, ExamSchedule, Mark


def request_branch_id(serializer):
    """The branch id this write belongs to, or None if it cannot be worked out.

    `get_branch()` and not `request.branch`: the latter is a `SimpleLazyObject`,
    so an `is None` check against it silently passes for everyone (CLAUDE.md
    §5). A platform admin's `?branch=` arrives as a string, which is why an id
    is returned rather than an object.
    """
    request = serializer.context.get('request')
    branch = get_branch(request) if request is not None else None

    if hasattr(branch, 'pk'):
        return branch.pk
    if isinstance(branch, str) and branch.isdigit():
        return int(branch)
    return getattr(serializer.instance, 'branch_id', None)


def check_same_branch(serializer, value, message):
    """Reject a related row belonging to another institution."""
    if value is None:
        return value
    branch_id = request_branch_id(serializer)
    if branch_id is not None and value.branch_id != branch_id:
        raise serializers.ValidationError(message)
    return value


class ExamSerializer(serializers.ModelSerializer):
    session_name = serializers.CharField(source='session.name', read_only=True)
    stream_name = serializers.CharField(source='stream.name', read_only=True)

    class Meta:
        model = Exam
        fields = [
            'id', 'session', 'session_name', 'stream', 'stream_name',
            'name', 'name_bn', 'exam_type', 'starts_on', 'ends_on',
            'status', 'published_by', 'published_at', 'created_at',
        ]
        # `status` is read-only on the CRUD endpoint on purpose: the only route
        # from marks_entry to published is `POST /exams/<id>/publish/`, which is
        # gated on `exams.publish`. A writable status field would let anyone
        # holding `exams.update` — every teacher who can create a test — publish
        # a result with a PATCH, which is the exact separation docs/02 §2.1
        # draws between the two checkboxes.
        read_only_fields = ['status', 'published_by', 'published_at', 'created_at']

    def validate_session(self, value):
        return check_same_branch(self, value, 'That session belongs to another institution.')

    def validate_stream(self, value):
        return check_same_branch(self, value, 'That stream belongs to another institution.')

    def validate(self, attrs):
        starts_on = attrs.get('starts_on', getattr(self.instance, 'starts_on', None))
        ends_on = attrs.get('ends_on', getattr(self.instance, 'ends_on', None))
        if starts_on and ends_on and ends_on < starts_on:
            raise serializers.ValidationError({
                'ends_on': 'The exam cannot end before it starts · '
                           'পরীক্ষা শুরুর আগে শেষ হতে পারে না।',
            })
        return attrs


class ExamClassSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source='academic_class.name', read_only=True)

    class Meta:
        model = ExamClass
        fields = ['id', 'exam', 'academic_class', 'class_name']

    def validate_exam(self, value):
        return check_same_branch(self, value, 'That exam belongs to another institution.')

    def validate_academic_class(self, value):
        return check_same_branch(self, value, 'That class belongs to another institution.')


class ExamScheduleSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    class_name = serializers.CharField(source='academic_class.name', read_only=True)

    class Meta:
        model = ExamSchedule
        fields = [
            'id', 'exam', 'academic_class', 'class_name', 'subject', 'subject_name',
            'date', 'start_time', 'end_time', 'full_marks', 'pass_marks',
            'room', 'invigilator',
        ]
        # Both are copied from the subject when the client leaves them out, so
        # the common case — "the annual is out of what the subject says" — is
        # one less thing to type on a grid of twelve papers.
        extra_kwargs = {
            'full_marks': {'required': False},
            'pass_marks': {'required': False},
        }

    def validate_exam(self, value):
        return check_same_branch(self, value, 'That exam belongs to another institution.')

    def validate_academic_class(self, value):
        return check_same_branch(self, value, 'That class belongs to another institution.')

    def validate_subject(self, value):
        return check_same_branch(self, value, 'That subject belongs to another institution.')

    def validate_invigilator(self, value):
        return check_same_branch(self, value, 'That teacher belongs to another institution.')

    def validate(self, attrs):
        subject = attrs.get('subject', getattr(self.instance, 'subject', None))
        if subject is not None:
            attrs.setdefault('full_marks', subject.full_marks)
            attrs.setdefault('pass_marks', subject.pass_marks)

        full = attrs.get('full_marks', getattr(self.instance, 'full_marks', None))
        pass_marks = attrs.get('pass_marks', getattr(self.instance, 'pass_marks', None))
        if full is not None and pass_marks is not None and pass_marks > full:
            raise serializers.ValidationError({
                'pass_marks': 'The pass mark cannot exceed the full mark · '
                              'পাস নম্বর পূর্ণমানের চেয়ে বেশি হতে পারে না।',
            })

        start = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end = attrs.get('end_time', getattr(self.instance, 'end_time', None))
        if start and end and end <= start:
            raise serializers.ValidationError({
                'end_time': 'The paper must end after it starts · '
                            'পরীক্ষা শুরুর পরে শেষ হতে হবে।',
            })
        return attrs


class MarkSerializer(serializers.ModelSerializer):
    """Read shape for a single mark.

    Writes go through `POST /api/exams/<id>/marks/`, not through this serializer:
    marks are entered as a grid and the grid has to be one transaction and one
    subject-scope check (`services.save_marks`). A per-row create endpoint would
    make the teacher-scope check something each row re-does, and something a
    bulk client could skip by posting rows one at a time.
    """

    student_name = serializers.CharField(source='student.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    total = serializers.DecimalField(source='total_obtained', max_digits=7,
                                     decimal_places=2, read_only=True)

    class Meta:
        model = Mark
        fields = [
            'id', 'exam', 'student', 'student_name', 'enrolment',
            'subject', 'subject_name', 'obtained', 'practical_obtained',
            'total', 'is_absent', 'entered_by', 'entered_at', 'is_active',
        ]
        read_only_fields = fields


class MarkRowSerializer(serializers.Serializer):
    """One cell of the entry grid."""

    enrolment = serializers.IntegerField()
    obtained = serializers.DecimalField(max_digits=6, decimal_places=2,
                                        required=False, allow_null=True)
    practical_obtained = serializers.DecimalField(max_digits=6, decimal_places=2,
                                                  required=False, allow_null=True)
    is_absent = serializers.BooleanField(required=False, default=False)


class MarksGridSerializer(serializers.Serializer):
    """The whole grid for one paper — what the marks-entry screen posts."""

    subject = serializers.IntegerField()
    rows = MarkRowSerializer(many=True)
