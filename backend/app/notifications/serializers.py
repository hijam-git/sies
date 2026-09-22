"""Shape and validation for the notifications API (CLAUDE.md §4.3).

`branch` is never writable — `BranchScopedViewSet` stamps it from
`request.branch` — and the outbox is read-only through the API in every field:
a message's status is what the gateway said, and a client that could set it to
`sent` could make the audit trail agree with itself about a message that never
went anywhere.
"""

from rest_framework import serializers

from core.serializers import BranchSafeSerializer

from .models import NotificationTemplate, SmsMessage
from .parts import sms_cost


class NotificationTemplateSerializer(BranchSafeSerializer):
    """The institution's own wording for one event."""

    #: What this template would cost to send, as typed. Served with every read
    #: so the template screen can say "2 SMS per student" while somebody is
    #: writing it — Bengali crosses from one part to two at 70 characters, and
    #: the writer cannot be expected to know that.
    cost = serializers.SerializerMethodField()

    class Meta:
        model = NotificationTemplate
        fields = ['id', 'event', 'channel', 'language', 'body', 'is_active',
                  'cost', 'created_at', 'updated_at']
        read_only_fields = ['id', 'cost', 'created_at', 'updated_at']

    def get_cost(self, template):
        return sms_cost(template.body)

    def validate_body(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError(
                'The message cannot be empty · বার্তা খালি রাখা যাবে না।')
        return value


class SmsMessageSerializer(serializers.ModelSerializer):
    """One outbox row, as the log screen reads it."""

    student_name = serializers.CharField(source='student.name', read_only=True, default='')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    event_display = serializers.CharField(source='get_event_display', read_only=True)

    class Meta:
        model = SmsMessage
        fields = ['id', 'event', 'event_display', 'reference', 'student', 'student_name',
                  'recipient_label', 'to_phone', 'body', 'parts', 'status',
                  'status_display', 'skip_reason', 'provider', 'provider_code',
                  'provider_message', 'sent_at', 'attempts', 'created_at']
        # Every field. The outbox is a record of what happened, and the only
        # thing that may write to it is the sending service.
        read_only_fields = fields


class SendResultSmsSerializer(serializers.Serializer):
    """The body of `POST /api/exams/<id>/send-results-sms/`.

    `academic_class` is optional: a principal sends one class at a time on
    results day, and the whole exam when the last class is entered.
    """

    academic_class = serializers.IntegerField(required=False, allow_null=True)
