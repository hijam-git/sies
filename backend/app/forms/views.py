"""The forms API (docs/07 §8, §9).

    GET  /api/admissions/<id>/form/?template=&mode=filled|blank   → HTML
    POST /api/admissions/<id>/answers/                            → save answers
    /api/form-templates/   /api/questions/   /api/printed-forms/

The form endpoint returns an **HTML document**, not JSON. The SPA opens it and
calls `window.print()` (§8) — the page *is* the deliverable, and wrapping it in
a JSON envelope would only mean the client has to unwrap and inject it, which
loses the browser's own print preview.

Templates and questions sit under the `settings` resource, which is where
docs/02 §2.1 puts form templates; printed forms sit under `documents`, with the
certificates and student files they belong beside.
"""

from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasResourcePermission, has_permission
from accounts.services import ActivityLogMixin
from core.middleware import get_branch
from core.viewsets import BranchScopedReadOnlyViewSet, BranchScopedViewSet
from students.models import Admission

from .models import AdmissionAnswer, FormTemplate, PrintedForm, Question
from .serializers import (AdmissionAnswerSerializer, AnswersSerializer,
                          FormTemplateSerializer, PrintedFormSerializer,
                          QuestionSerializer)
from .services import preview_template, print_form, reprint, save_answers


class FormTemplateViewSet(ActivityLogMixin, BranchScopedViewSet):
    """The block editor's CRUD, plus a preview."""

    queryset = FormTemplate.objects.all()
    serializer_class = FormTemplateSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'settings'
    # The `settings` resource has only `view` and `update` (docs/02 §2.1):
    # editing an institution's form templates IS changing its settings, and a
    # separate create/delete checkbox would be a distinction nobody administering
    # a madrasah would draw. So create and delete both resolve to `update`.
    permission_action_map = {
        'preview': 'view', 'create': 'update', 'destroy': 'update',
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['form_type', 'is_active', 'is_default']
    search_fields = ['name', 'name_bn']
    activity_model = 'FormTemplate'

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """`GET /api/form-templates/<id>/preview/?mode=blank|filled`.

        The editor's live A4 preview beside the block list (§9). No admission
        behind it, so `filled` here still renders empty rules — the preview
        shows the *layout*, and the data comes from whichever applicant it is
        printed for.
        """
        template = self.get_object()
        html = preview_template(template, mode=request.GET.get('mode', 'blank'))
        return HttpResponse(html, content_type='text/html; charset=utf-8')


class QuestionViewSet(ActivityLogMixin, BranchScopedViewSet):
    """The question bank, per section (§9)."""

    queryset = Question.objects.select_related('template')
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'settings'
    permission_action_map = {'create': 'update', 'destroy': 'update'}
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['template', 'section', 'type', 'is_active']
    search_fields = ['text', 'text_bn']
    ordering_fields = ['order', 'section']
    activity_model = 'Question'


class AdmissionAnswerViewSet(BranchScopedReadOnlyViewSet):
    """Answers, read-only.

    Writing goes through `POST /api/admissions/<id>/answers/`, which is where
    the `maps_to` rule is applied (§5.2). A writable endpoint here would be a
    second path able to store an answer for a mapped question.
    """

    queryset = AdmissionAnswer.objects.select_related('question')
    serializer_class = AdmissionAnswerSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'admissions'
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['admission', 'question']


class PrintedFormViewSet(BranchScopedReadOnlyViewSet):
    """Every form that was printed, reprintable from its snapshot (§9)."""

    queryset = PrintedForm.objects.select_related('admission', 'template')
    serializer_class = PrintedFormSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'documents'
    permission_action_map = {'reprint': 'view'}
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['admission', 'template']
    ordering_fields = ['printed_at', 'form_no']

    @action(detail=True, methods=['get'])
    def reprint(self, request, pk=None):
        """`GET /api/printed-forms/<id>/reprint/` — the snapshot, re-rendered.

        From the snapshot and never from the record: a student whose name was
        corrected last year still has a signed form on file with the old
        spelling, and the reprint has to match the paper in the file.
        """
        printed = self.get_object()
        html = reprint(printed, actor=request.user, request=request)
        return HttpResponse(html, content_type='text/html; charset=utf-8')


class AdmissionScopedView(APIView):
    """Shared lookup for the two `/admissions/<id>/…` endpoints.

    The admission is fetched through the branch-scoped manager, so another
    institution's application is **404, not 403** (CLAUDE.md §5) — the same
    answer this URL gives for an id that does not exist.
    """

    permission_classes = [IsAuthenticated, HasResourcePermission]

    def get_admission(self, request, pk):
        admission = (
            Admission.objects.for_branch(get_branch(request))
            .select_related('branch', 'session', 'academic_class', 'student')
            .filter(pk=pk)
            .first()
        )
        if admission is None:
            raise NotFound('No such application · এমন কোনো আবেদন নেই।')
        return admission


class AdmissionFormView(AdmissionScopedView):
    """`GET /api/admissions/<id>/form/?template=<id>&mode=filled|blank`.

    Returns a print-ready HTML document. `blank` renders the same template with
    an empty context — every placeholder becomes a rule — which is the stack a
    madrasah prints in bulk at admission season (§7). Because it is the same
    template, the blank stack and the filled copy can never drift.
    """

    permission_resource = 'documents'

    def get(self, request, pk):
        admission = self.get_admission(request, pk)

        # `mode=filled` **writes**: `print_form` allocates a form number under a
        # lock and inserts a `PrintedForm`. A plain `APIView` has no `action`, so
        # `HasResourcePermission` priced this GET at `documents.view` — a
        # read-only account could loop the URL and exhaust the institution's
        # numbered series. Blank mode records nothing and stays a read.
        if request.GET.get('mode') != 'blank' and not has_permission(
            request.user, 'documents', 'upload',
        ):
            raise PermissionDenied(
                'Printing a filled form issues a form number · '
                'পূরণ করা ফরম ছাপলে ফরম নম্বর ইস্যু হয়।'
            )

        template = None
        requested = request.GET.get('template')
        if requested:
            template = FormTemplate.objects.filter(
                pk=requested, branch_id=admission.branch_id,
            ).first()
            if template is None:
                raise NotFound('No such form template · এমন কোনো ফরম টেমপ্লেট নেই।')

        mode = 'blank' if request.GET.get('mode') == 'blank' else 'filled'
        html, _printed = print_form(
            admission=admission, template=template, mode=mode,
            actor=request.user, request=request,
        )
        return HttpResponse(html, content_type='text/html; charset=utf-8')


class AdmissionAnswersView(AdmissionScopedView):
    """`GET|POST /api/admissions/<id>/answers/` — the data-entry screen.

    POST goes through `services.save_answers`, which applies §5.2: a mapped
    question writes the student field and stores no answer.
    """

    permission_resource = 'admissions'

    def get(self, request, pk):
        admission = self.get_admission(request, pk)
        answers = AdmissionAnswer.objects.filter(admission=admission)
        return Response(AdmissionAnswerSerializer(answers, many=True).data)

    def post(self, request, pk):
        admission = self.get_admission(request, pk)
        body = AnswersSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = save_answers(
            admission=admission, answers=body.validated_data['answers'],
            actor=request.user, request=request,
        )
        return Response(result)
