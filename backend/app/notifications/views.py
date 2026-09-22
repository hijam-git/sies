"""The notifications API (CLAUDE.md §5).

Two endpoint families, both branch-scoped and both under the `settings`
resource — writing the wording an institution sends to four hundred guardians,
and reading what was sent, are the same kind of act as setting the fine rule.

The send itself is **not** here: it hangs off the exam, at
`POST /api/exams/<id>/send-results-sms/`, because it costs `exams.publish` —
the permission a principal holds and a teacher does not. Releasing a result to
a screen and releasing it to a handset are one decision.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import HasResourcePermission
from accounts.services import ActivityLogMixin
from core.viewsets import BranchScopedReadOnlyViewSet, BranchScopedViewSet

from .models import NotificationTemplate, SmsMessage
from .serializers import NotificationTemplateSerializer, SmsMessageSerializer
from .services import DEFAULT_BODIES, PLACEHOLDERS


class NotificationTemplateViewSet(ActivityLogMixin, BranchScopedViewSet):
    """The institution's wording, per event and language."""

    queryset = NotificationTemplate.objects.select_related('branch').all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'settings'
    # The catalogue gives `settings` view/update and nothing else (docs/02
    # §2.1), so every write maps onto `update` — there is no `settings.create`
    # to fall back to, and an unmapped POST would resolve to one and 403 for
    # everybody. Writing the wording IS changing a setting.
    permission_action_map = {
        'create': 'update',
        'update': 'update',
        'partial_update': 'update',
        'destroy': 'update',
        'placeholders': 'view',
    }
    activity_model = 'NotificationTemplate'
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'channel', 'language', 'is_active']
    ordering_fields = ['event', 'language', 'created_at']

    @action(detail=False, methods=['get'])
    def placeholders(self, request):
        """What a template writer may use, and the default wording.

        Served rather than documented, so the screen cannot drift from the
        renderer: both read `services.PLACEHOLDERS` and `DEFAULT_BODIES`.
        """
        return Response({
            'placeholders': {
                event: [{'name': name, 'label': label} for name, label in fields]
                for event, fields in PLACEHOLDERS.items()
            },
            'defaults': [
                {'event': event, 'language': language, 'body': body}
                for (event, language), body in DEFAULT_BODIES.items()
            ],
        })


class SmsMessageViewSet(BranchScopedReadOnlyViewSet):
    """The outbox — what was sent, to whom, and what the gateway said.

    Read-only, and not only because nothing should edit it: this is the table
    that answers a guardian who says the result never arrived, and a record
    that can be edited answers nothing.
    """

    queryset = SmsMessage.objects.select_related('branch', 'student').all()
    serializer_class = SmsMessageSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'settings'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event', 'status', 'student', 'reference']
    search_fields = ['to_phone', 'recipient_label', 'body']
    ordering_fields = ['created_at', 'sent_at', 'status']
