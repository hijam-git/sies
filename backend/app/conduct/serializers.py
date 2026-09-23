"""Shape and validation for the conduct API (CLAUDE.md §4.3).

`branch` is never writable — `BranchScopedViewSet` stamps it — and every FK is
checked against the caller's own institution by `BranchSafeSerializer`, so a
template cannot be pointed at another institution's বিভাগ or class.
"""

from rest_framework import serializers

from core.serializers import BranchSafeSerializer
from academics.models import Section
from forms.models import Question

from .models import (ReportAnswer, ReportAssignment, ReportTemplate,
                     StudentReport)


class SheetQuestionSerializer(serializers.ModelSerializer):
    """A question from the bank, as the sheet reads it.

    Read-only here on purpose: questions are written on Settings → Questions,
    which is the editor they already had. Two screens that both create a
    question is two banks pretending to be one.
    """

    class Meta:
        model = Question
        fields = ['id', 'text', 'text_bn', 'type', 'options', 'is_required', 'order']
        read_only_fields = fields


class ReportTemplateSerializer(BranchSafeSerializer):
    items = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = ReportTemplate
        fields = ['id', 'name', 'name_bn', 'frequency', 'section', 'stream',
                  'academic_class', 'is_active', 'items', 'item_count',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'items', 'item_count', 'created_at', 'updated_at']

    def get_items(self, template):
        from .services import template_questions

        return SheetQuestionSerializer(template_questions(template), many=True).data

    def get_item_count(self, template):
        from .services import template_questions

        return len(template_questions(template))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        academic_class = attrs.get('academic_class',
                                   getattr(self.instance, 'academic_class', None))
        stream = attrs.get('stream', getattr(self.instance, 'stream', None))
        if academic_class is not None and stream is not None \
                and academic_class.stream_id != stream.pk:
            raise serializers.ValidationError({
                'stream': 'That class is not in this বিভাগ · ওই শ্রেণি এই বিভাগের নয়।',
            })
        return attrs


class TemplateQuestionsSerializer(serializers.Serializer):
    """The body of `POST /api/report-templates/<id>/questions/`.

    The whole list, in order — not add/remove calls. The setup screen holds the
    list, and two half-applied requests are how an ordering ends up with two
    questions claiming position three.
    """

    questions = serializers.ListField(child=serializers.IntegerField(),
                                      allow_empty=True)


class ReportAssignmentSerializer(BranchSafeSerializer):
    """Who is responsible for a template on a class."""

    teacher_name = serializers.CharField(source='teacher.name', read_only=True)
    class_name = serializers.CharField(source='academic_class.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True, default='')
    template_name = serializers.CharField(source='template.name', read_only=True)

    #: Declared rather than inferred, and `default=None` is the load-bearing
    #: part. `section` is in a UniqueConstraint, and DRF's matching validator
    #: demands every field of a uniqueness rule be present — so leaving it out
    #: was a 400 saying "this is required" about the field whose whole purpose
    #: is to be optional ("the whole class" is NULL).
    section = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(), required=False, allow_null=True, default=None,
    )

    class Meta:
        model = ReportAssignment
        fields = ['id', 'template', 'template_name', 'academic_class', 'class_name',
                  'section', 'section_name', 'teacher', 'teacher_name',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'teacher_name', 'class_name', 'section_name',
                            'template_name', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        section = attrs.get('section', getattr(self.instance, 'section', None))
        academic_class = attrs.get('academic_class',
                                   getattr(self.instance, 'academic_class', None))
        if section is not None and academic_class is not None \
                and section.academic_class_id != academic_class.pk:
            raise serializers.ValidationError({
                'section': 'That শাখা is not in this class · ওই শাখা এই শ্রেণির নয়।',
            })
        return attrs


class ReportAnswerSerializer(serializers.ModelSerializer):
    text = serializers.CharField(source='item.text', read_only=True)
    text_bn = serializers.CharField(source='item.text_bn', read_only=True)
    type = serializers.CharField(source='item.type', read_only=True)

    class Meta:
        model = ReportAnswer
        fields = ['id', 'item', 'text', 'text_bn', 'type', 'value']
        read_only_fields = fields


class StudentReportSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)
    filled_by_name = serializers.CharField(source='filled_by.name', read_only=True,
                                           default='')
    answers = ReportAnswerSerializer(many=True, read_only=True)

    class Meta:
        model = StudentReport
        fields = ['id', 'template', 'template_name', 'student', 'student_name',
                  'enrolment', 'period', 'status', 'remarks', 'filled_by',
                  'filled_by_name', 'filled_at', 'answers', 'created_at']
        # Only the remark is correctable here; the answers are written by the
        # sheet endpoint, which owns the rules about what a value may be.
        read_only_fields = ['id', 'template', 'student', 'enrolment', 'period',
                            'status', 'filled_by', 'filled_at', 'answers',
                            'created_at']


class SheetRowSerializer(serializers.Serializer):
    enrolment = serializers.IntegerField()
    answers = serializers.DictField(required=False, default=dict)
    remarks = serializers.CharField(required=False, allow_blank=True, default='')


class SaveSheetSerializer(serializers.Serializer):
    """The body of `POST /api/conduct/sheet/` — the dirty rows, not the grid.

    Sending only what changed is what keeps a class of sixty a small request on
    a phone, and the service is idempotent either way.
    """

    rows = SheetRowSerializer(many=True)

    def validate_rows(self, value):
        if not value:
            raise serializers.ValidationError(
                'Nothing to save · সংরক্ষণ করার মতো কিছু নেই।')
        return value


class MyDutiesQuerySerializer(serializers.Serializer):
    """`GET /api/conduct/my-duties/?date=` — which day's periods to report on.

    A date, not a period: the duties span templates of different frequencies,
    and only the server should turn one day into a week, a month or a term.
    """

    date = serializers.DateField(required=False)
