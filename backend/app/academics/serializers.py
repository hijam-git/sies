"""Shape and validation for the academics API (CLAUDE.md §4.3, §5).

`branch` is never writable — `BranchScopedViewSet` stamps it from
`request.branch`, and leaving it off every serializer here is the second
independent reason a `branch` in a POST body does nothing (docs/02 §3).

The recurring validation in this module is **"that row belongs to another
institution"**. A branch-scoped queryset controls what a caller can *read*;
nothing about a plain FK stops them *writing* a pointer at somebody else's class.
`_reject_foreign()` is that check, written once.
"""

from rest_framework import serializers

from core.middleware import get_branch

from .models import (AcademicClass, ClassRoutine, Enrolment, Period, Section,
                     Subject, SubjectAssignment)


def _request_branch_id(serializer):
    """The institution this write belongs to, or None if it cannot be told.

    None only happens for a platform admin who gave no `?branch=` on a create —
    and `BranchScopedMixin.perform_create` answers that with a 400 before any of
    this matters.
    """
    branch = get_branch(serializer.context['request'])
    branch_id = getattr(branch, 'pk', None)
    if branch_id is None and serializer.instance is not None:
        branch_id = serializer.instance.branch_id
    return branch_id


def _reject_foreign(serializer, **rows):
    """Raise if any named row belongs to a different institution."""
    branch_id = _request_branch_id(serializer)
    if branch_id is None:
        return

    wrong = [
        field for field, row in rows.items()
        if row is not None and row.branch_id != branch_id
    ]
    if wrong:
        raise serializers.ValidationError({
            field: 'That belongs to another institution · এটি অন্য প্রতিষ্ঠানের।'
            for field in wrong
        })


class AcademicClassSerializer(serializers.ModelSerializer):
    section_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = AcademicClass
        fields = ['id', 'stream', 'session', 'name', 'name_bn', 'year',
                  'level_order', 'capacity', 'class_teacher', 'monthly_fee',
                  'is_active', 'section_count', 'created_at', 'updated_at']
        # `year` is denormalised from the session by `AcademicClass.save()`, so
        # it is a read-only mirror rather than a second thing to keep in step.
        read_only_fields = ['id', 'year', 'created_at', 'updated_at']

    def validate(self, attrs):
        _reject_foreign(
            self,
            stream=attrs.get('stream'),
            session=attrs.get('session'),
            class_teacher=attrs.get('class_teacher'),
        )
        return attrs


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'academic_class', 'name', 'name_bn', 'capacity', 'room',
                  'in_charge', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        _reject_foreign(
            self,
            academic_class=attrs.get('academic_class'),
            in_charge=attrs.get('in_charge'),
        )
        return attrs


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'stream', 'academic_class', 'name', 'name_bn', 'code',
                  'full_marks', 'pass_marks', 'is_optional', 'has_practical',
                  'practical_marks', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        _reject_foreign(
            self,
            stream=attrs.get('stream'),
            academic_class=attrs.get('academic_class'),
        )

        full = attrs.get('full_marks', getattr(self.instance, 'full_marks', 100))
        passing = attrs.get('pass_marks', getattr(self.instance, 'pass_marks', 33))
        if passing > full:
            # `Meta.constraints` is the real guarantee; repeating it here turns an
            # integrity error into a 400 the form can attach to an input.
            raise serializers.ValidationError({
                'pass_marks': 'The pass mark cannot exceed the full mark · '
                              'পাস নম্বর পূর্ণমানের বেশি হতে পারে না।',
            })
        return attrs


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields = ['id', 'stream', 'name', 'name_bn', 'order', 'start_time',
                  'end_time', 'is_break', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        _reject_foreign(self, stream=attrs.get('stream'))

        start = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end = attrs.get('end_time', getattr(self.instance, 'end_time', None))
        if start and end and end <= start:
            raise serializers.ValidationError({
                'end_time': 'A period must end after it starts · '
                            'ঘণ্টা শুরুর পরে শেষ হতে হবে।',
            })
        return attrs


class ClassRoutineSerializer(serializers.ModelSerializer):
    """One cell of the weekly timetable.

    The two clash checks below duplicate `ClassRoutine`'s unique constraints on
    purpose. The database is the guarantee — it has to be, because the bulk
    import path does not come through here — but a routine editor needs to be
    told *which* teacher is already busy at that hour, and an IntegrityError
    cannot say that.
    """

    teacher_name = serializers.CharField(source='teacher.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    period_name = serializers.CharField(source='period.name', read_only=True)
    # The Bangla labels and the class/section names ride along because the
    # screens that draw a cell — the admin grid and a teacher's own week — have
    # only the row, and joining four lookup lists client-side to render "Class 5
    # · A" is four extra requests for names the join already had.
    class_name = serializers.CharField(source='academic_class.name', read_only=True)
    class_name_bn = serializers.CharField(source='academic_class.name_bn', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    subject_name_bn = serializers.CharField(source='subject.name_bn', read_only=True)
    period_name_bn = serializers.CharField(source='period.name_bn', read_only=True)
    period_order = serializers.IntegerField(source='period.order', read_only=True)
    is_break = serializers.BooleanField(source='period.is_break', read_only=True)
    start_time = serializers.TimeField(source='period.start_time', read_only=True)
    end_time = serializers.TimeField(source='period.end_time', read_only=True)
    day_display = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = ClassRoutine
        fields = ['id', 'session', 'academic_class', 'section', 'subject',
                  'teacher', 'period', 'day_of_week', 'room', 'is_active',
                  'teacher_name', 'subject_name', 'period_name',
                  'class_name', 'class_name_bn', 'section_name',
                  'subject_name_bn', 'period_name_bn', 'period_order',
                  'is_break', 'start_time', 'end_time', 'day_display',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        def current(field):
            return attrs.get(field, getattr(self.instance, field, None))

        session = current('session')
        academic_class = current('academic_class')
        section = current('section')
        subject = current('subject')
        teacher = current('teacher')
        period = current('period')
        day = current('day_of_week')

        _reject_foreign(
            self, session=session, academic_class=academic_class,
            section=section, subject=subject, teacher=teacher, period=period,
        )

        if subject is not None and academic_class is not None \
                and subject.academic_class_id != academic_class.pk:
            raise serializers.ValidationError({
                'subject': 'That subject is not taught in this class · '
                           'ওই বিষয়টি এই শ্রেণির নয়।',
            })

        if section is not None and academic_class is not None \
                and section.academic_class_id != academic_class.pk:
            raise serializers.ValidationError({
                'section': 'That section belongs to another class · '
                           'ওই শাখা অন্য শ্রেণির।',
            })

        siblings = ClassRoutine.objects.filter(session=session, day_of_week=day,
                                               period=period)
        if self.instance is not None:
            siblings = siblings.exclude(pk=self.instance.pk)

        busy = siblings.filter(teacher=teacher).select_related('academic_class').first()
        if busy is not None:
            raise serializers.ValidationError({
                'teacher': (
                    f'{busy.teacher.name} already teaches {busy.academic_class.name} '
                    f'in this period · এই ঘণ্টায় শিক্ষক অন্য ক্লাসে আছেন।'
                ),
            })

        if siblings.filter(academic_class=academic_class, section=section).exists():
            raise serializers.ValidationError({
                'period': 'This class already has a subject in this period · '
                          'এই ঘণ্টায় শ্রেণিটির অন্য বিষয় আছে।',
            })

        return attrs


class EnrolmentSerializer(serializers.ModelSerializer):
    """A student in a class for a session.

    `roll` and `admission_number` are read-only: both are issued by
    `services.enrol_student()` under a row lock, and a client-chosen number is a
    client-chosen collision (CLAUDE.md §4.4). Correcting one is a deliberate
    operation, not a PATCH on the register.
    """

    student_name = serializers.CharField(source='student.name', read_only=True)
    class_name = serializers.CharField(source='academic_class.name', read_only=True)

    class Meta:
        model = Enrolment
        fields = ['id', 'student', 'session', 'academic_class', 'section',
                  'roll', 'admission_number', 'status', 'enrolled_on', 'left_on',
                  'is_hostel', 'is_transport', 'is_active',
                  'student_name', 'class_name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'roll', 'admission_number', 'created_at', 'updated_at']

    def validate(self, attrs):
        section = attrs.get('section')
        academic_class = attrs.get('academic_class',
                                   getattr(self.instance, 'academic_class', None))
        _reject_foreign(
            self,
            student=attrs.get('student'),
            session=attrs.get('session'),
            academic_class=attrs.get('academic_class'),
            section=section,
        )
        if section is not None and academic_class is not None \
                and section.academic_class_id != academic_class.pk:
            raise serializers.ValidationError({
                'section': 'That section belongs to another class · '
                           'ওই শাখা অন্য শ্রেণির।',
            })
        return attrs


class SubjectAssignmentSerializer(serializers.ModelSerializer):
    """Which teacher teaches which subject to which class — and therefore what
    that teacher can reach (docs/08 D6).

    The cross-branch and cross-session checks below are named in D6 as
    requirements, and they matter more here than on an ordinary table: this row
    is an access grant, so a mis-pointed one widens somebody's reach.
    """

    teacher_name = serializers.CharField(source='teacher.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = SubjectAssignment
        fields = ['id', 'session', 'teacher', 'subject', 'academic_class',
                  'section', 'is_active', 'teacher_name', 'subject_name',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        def current(field):
            return attrs.get(field, getattr(self.instance, field, None))

        session = current('session')
        academic_class = current('academic_class')
        section = current('section')
        subject = current('subject')

        _reject_foreign(
            self, session=session, teacher=current('teacher'),
            subject=subject, academic_class=academic_class, section=section,
        )

        if academic_class is not None and session is not None \
                and academic_class.session_id != session.pk:
            raise serializers.ValidationError({
                'academic_class': 'That class belongs to another session · '
                                  'ওই শ্রেণি অন্য শিক্ষাবর্ষের।',
            })

        if subject is not None and academic_class is not None \
                and subject.academic_class_id != academic_class.pk:
            raise serializers.ValidationError({
                'subject': 'That subject is not taught in this class · '
                           'ওই বিষয়টি এই শ্রেণির নয়।',
            })

        if section is not None and academic_class is not None \
                and section.academic_class_id != academic_class.pk:
            raise serializers.ValidationError({
                'section': 'That section belongs to another class · '
                           'ওই শাখা অন্য শ্রেণির।',
            })

        return attrs
