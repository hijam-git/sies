"""Shape and validation for the forms API (CLAUDE.md §4.3).

`branch` is never writable; `BranchScopedViewSet` stamps it from
`request.branch`.

The one thing worth reading here is `validate_blocks`: the model validates on
`save()` so no code path can bypass it, and the serializer validates again so
the *editor* gets a 400 naming the bad block instead of a 500 from a model-level
`ValidationError` escaping through DRF. Two checks, one implementation — both
call `blocks.validate_blocks`.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.middleware import get_branch

from .blocks import validate_blocks
from .models import (AdmissionAnswer, FormTemplate, MAPPED_FIELDS, PrintedForm,
                     Question)
from .placeholders import PLACEHOLDER_GROUPS


def request_branch_id(serializer):
    """The branch id this write belongs to — `get_branch()`, never
    `request.branch`, which is a `SimpleLazyObject` (CLAUDE.md §5)."""
    request = serializer.context.get('request')
    branch = get_branch(request) if request is not None else None
    if hasattr(branch, 'pk'):
        return branch.pk
    if isinstance(branch, str) and branch.isdigit():
        return int(branch)
    return getattr(serializer.instance, 'branch_id', None)


def check_same_branch(serializer, value, message):
    if value is None:
        return value
    branch_id = request_branch_id(serializer)
    if branch_id is not None and value.branch_id != branch_id:
        raise serializers.ValidationError(message)
    return value


class FormTemplateSerializer(serializers.ModelSerializer):
    # Served alongside the template so the block editor's placeholder picker is
    # generated from the same closed set the validator enforces. One source of
    # truth, not two copies that agree until the day they do not.
    placeholder_groups = serializers.SerializerMethodField()

    class Meta:
        model = FormTemplate
        fields = [
            'id', 'name', 'name_bn', 'form_type', 'blocks', 'paper', 'margins',
            'is_default', 'is_active', 'placeholder_groups', 'created_at',
        ]
        read_only_fields = ['created_at']

    def get_placeholder_groups(self, _obj):
        return PLACEHOLDER_GROUPS

    def validate_blocks(self, value):
        try:
            return validate_blocks(value)
        except DjangoValidationError as error:
            # Re-raised as a DRF error so the editor gets a 400 with the message
            # naming the offending block, rather than a 500 from a Django
            # ValidationError escaping the serializer.
            raise serializers.ValidationError(error.messages)


class QuestionSerializer(serializers.ModelSerializer):
    mappable_fields = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'id', 'template', 'section', 'text', 'text_bn', 'type', 'options',
            'is_required', 'print_style', 'answer_lines', 'maps_to', 'order',
            'is_active', 'mappable_fields',
        ]

    def get_mappable_fields(self, _obj):
        return sorted(MAPPED_FIELDS)

    def validate_template(self, value):
        return check_same_branch(self, value, 'That template belongs to another institution.')

    def validate_maps_to(self, value):
        if value and value not in MAPPED_FIELDS:
            raise serializers.ValidationError(
                'Not a bindable student field · এটি শিক্ষার্থীর কোনো ফিল্ড নয়।'
            )
        return value

    def validate(self, attrs):
        question_type = attrs.get('type', getattr(self.instance, 'type', None))
        options = attrs.get('options', getattr(self.instance, 'options', None))
        if question_type in ('single_choice', 'multi_choice') and not options:
            raise serializers.ValidationError({
                'options': 'A choice question needs options · বাছাইয়ের প্রশ্নে বিকল্প দিতে হবে।',
            })
        return attrs


class AdmissionAnswerSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.text_bn', read_only=True)

    class Meta:
        model = AdmissionAnswer
        fields = ['id', 'admission', 'question', 'question_text', 'value', 'answered_at']
        # Answers are written through `services.save_answers`, which is where
        # the maps_to rule lives (§5.2). A writable serializer here would be a
        # second path that could store an answer for a mapped question — the
        # exact duplication the rule exists to prevent.
        read_only_fields = fields


class PrintedFormSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrintedForm
        fields = [
            'id', 'admission', 'template', 'form_no', 'printed_by', 'printed_at',
            'reprint_count',
        ]
        # `snapshot` is deliberately absent from the list shape: it is a whole
        # document, and a hundred of them in one page of results is a megabyte
        # nobody asked for. The reprint endpoint renders it.
        read_only_fields = fields


class AnswersSerializer(serializers.Serializer):
    """`{"answers": {"<question id>": <value>}}` — the data-entry screen's POST."""

    answers = serializers.DictField()

    def validate_answers(self, value):
        cleaned = {}
        for key, answer in value.items():
            try:
                cleaned[int(key)] = answer
            except (TypeError, ValueError):
                raise serializers.ValidationError(f'{key!r} is not a question id.')
        return cleaned
