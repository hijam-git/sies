"""Shape and validation for the attendance API (CLAUDE.md §4.3).

These serializers validate the *payload*; they do not decide what may be marked.
That decision is `services.is_markable()` and it is re-made inside the
transaction, because a serializer runs before the branch's settings are even
read and a check that lives here would be a check the bulk endpoint could be
talked past.

Note what is **not** writable anywhere below: `branch`, `taken_by`, `taken_at`
and `enrolment`. The first is stamped from `request.branch` (CLAUDE.md §1), the
next two from `request.user` per cell, and the last from the register's own
enrolment rows. A client that sends any of them is ignored, which is the only
safe reading of "who marked my son absent".
"""

from rest_framework import serializers

from .models import (AttendanceSource, AttendanceStatus, ClassAttendance,
                     DailyAttendance)


class CellSerializer(serializers.Serializer):
    """One dirty cell of the grid — `{student, date, status}`.

    `student` is a plain integer and not a `PrimaryKeyRelatedField`: a queryset
    field would issue one SELECT per cell, and the grid posts up to 1,800 of
    them. The id is resolved once against the register's own enrolments in
    `services.save_register()`, where an id that is not in this class is a
    `skipped` entry rather than a 400 that loses the other 1,799 cells.
    """

    student = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=AttendanceStatus.choices)
    remarks = serializers.CharField(max_length=200, required=False,
                                    allow_blank=True, default='')
    in_time = serializers.TimeField(required=False, allow_null=True)
    out_time = serializers.TimeField(required=False, allow_null=True)


class RegisterQuerySerializer(serializers.Serializer):
    """`?class=&section=&month=2026-03` — the grid's own query string.

    Validated as a serializer rather than read off `request.GET` by hand so a
    missing `month` is the project's one error shape and not a `KeyError`.
    """

    # `class` is a Python keyword, so the field is declared through the field
    # map. The query parameter has to stay `class` — it is docs/02 §5.1's
    # contract and it is what the SPA sends.
    section = serializers.IntegerField(required=False, allow_null=True)
    month = serializers.CharField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class'] = serializers.IntegerField()


class RegisterBulkSerializer(serializers.Serializer):
    """`POST /api/attendance/register/bulk/`.

    `month` is required and is not decoration: it bounds the save. A payload
    whose cells wander outside the month the teacher had open is a client bug or
    a probe, and either way those cells belong in `skipped` rather than in the
    register.
    """

    section = serializers.IntegerField(required=False, allow_null=True)
    month = serializers.CharField()
    cells = CellSerializer(many=True, allow_empty=True)
    # `web` unless the mobile client says otherwise (docs/03 §6). Not trusted for
    # anything but reporting — it changes no rule, so a client lying about it
    # gains nothing.
    source = serializers.ChoiceField(choices=AttendanceSource.choices,
                                     required=False, default=AttendanceSource.WEB)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class'] = serializers.IntegerField()


class ClassRosterQuerySerializer(serializers.Serializer):
    """`GET /api/attendance/class/?class=&section=&period=&date=`.

    Separate from the save serializer below rather than making `cells` optional
    on it: a write payload whose only mandatory list is optional is a write that
    silently succeeds having done nothing, and the roster read has no cells to
    send by definition.
    """

    section = serializers.IntegerField(required=False, allow_null=True)
    period = serializers.IntegerField()
    date = serializers.DateField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class'] = serializers.IntegerField()


class ClassAttendanceSaveSerializer(serializers.Serializer):
    """`POST /api/attendance/class/` — one period's roster (docs/08 D7)."""

    section = serializers.IntegerField(required=False, allow_null=True)
    subject = serializers.IntegerField(required=False, allow_null=True)
    period = serializers.IntegerField()
    date = serializers.DateField()
    cells = CellSerializer(many=True, allow_empty=True)
    source = serializers.ChoiceField(choices=AttendanceSource.choices,
                                     required=False, default=AttendanceSource.WEB)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class'] = serializers.IntegerField()


class MyDaySerializer(serializers.Serializer):
    """`GET /api/attendance/my-day/?date=` — the board's only parameter."""

    date = serializers.DateField(required=False)


class DailyAttendanceSerializer(serializers.ModelSerializer):
    """A single row, for the daily register tab and for debugging.

    Read-mostly: the grid writes through `register/bulk/`, which is the only
    path that gets the transaction and the markability rules. This exists so one
    row can be *read* with its person resolved, without the caller having to
    know which of the three FKs is set.
    """

    person_name = serializers.SerializerMethodField()
    taken_by_name = serializers.CharField(source='taken_by.name', read_only=True,
                                          default='')

    class Meta:
        model = DailyAttendance
        fields = [
            'id', 'date', 'person_type', 'student', 'teacher', 'employee',
            'person_name', 'enrolment', 'status', 'in_time', 'out_time',
            'remarks', 'taken_by', 'taken_by_name', 'taken_at', 'source',
            'created_at', 'updated_at',
        ]
        # `branch` is absent from `fields` entirely, not merely read-only: a
        # field that is not declared cannot be written even by a subclass that
        # forgets why (CLAUDE.md §1).
        read_only_fields = ['taken_by', 'taken_at', 'created_at', 'updated_at']

    def get_person_name(self, obj):
        person = obj.person
        return person.name if person is not None else ''


class ClassAttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    period_name = serializers.CharField(source='period.name', read_only=True)
    taken_by_name = serializers.CharField(source='taken_by.name', read_only=True,
                                          default='')

    class Meta:
        model = ClassAttendance
        fields = [
            'id', 'date', 'academic_class', 'section', 'subject', 'period',
            'period_name', 'student', 'student_name', 'enrolment', 'status',
            'remarks', 'taken_by', 'taken_by_name', 'taken_at', 'source',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['taken_by', 'taken_at', 'created_at', 'updated_at']
