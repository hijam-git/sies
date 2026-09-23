"""The observation API (CLAUDE.md §5).

Three gates, the same three the marks grid has:

1. **branch** — `BranchScopedViewSet`; another institution's template is 404.
2. **permission** — the `conduct` resource. `take` is what a teacher holds;
   writing the template itself is `settings.update`, because deciding what the
   institution observes is not the same act as observing it.
3. **assignment** — docs/08 D6. A teacher fills their own classes, and
   `TeacherScopedMixin`'s scope is reused rather than reimplemented here.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import AcademicClass, Section
from academics.services import (teacher_class_scope, teacher_for_user,
                                teacher_scope_applies)
from accounts.permissions import HasResourcePermission
from accounts.services import ActivityAction, ActivityLogMixin, log_activity
from core.middleware import get_branch
from core.viewsets import BranchScopedViewSet
from students.models import Student

from .models import ReportAssignment, ReportTemplate, StudentReport
from .serializers import (ReportAssignmentSerializer, ReportTemplateSerializer,
                          SaveSheetSerializer, StudentReportSerializer,
                          TemplateQuestionsSerializer)
from .services import (parse_period, save_sheet, set_template_questions,
                       sheet, student_history, templates_for)


def scoped_class(request, class_id):
    """The class, if this caller may reach it. Otherwise 404, never 403.

    Both gates in one place: the branch-scoped queryset removes another
    institution's classes, and D6 removes the ones this teacher is not assigned
    to. Neither answer tells the caller the class exists (CLAUDE.md §5).
    """
    academic_class = (AcademicClass.objects
                      .for_branch(get_branch(request))
                      .filter(pk=class_id)
                      .select_related('stream')
                      .first())
    if academic_class is None:
        raise NotFound('No such class in this institution · এই প্রতিষ্ঠানে এমন শ্রেণি নেই।')

    branch = get_branch(request)
    if teacher_scope_applies(request.user, branch):
        teacher = teacher_for_user(request.user)
        scope = teacher_class_scope(teacher) if teacher is not None else set()
        if academic_class.pk not in scope:
            raise NotFound('No such class in this institution · এই প্রতিষ্ঠানে এমন শ্রেণি নেই।')
    return academic_class


class ReportTemplateViewSet(ActivityLogMixin, BranchScopedViewSet):
    """What the institution observes.

    `settings`, not `conduct`: a teacher fills the sheet; deciding what is on it
    is the office's act, and the catalogue already calls that settings.
    """

    queryset = ReportTemplate.objects.select_related('stream', 'academic_class')
    serializer_class = ReportTemplateSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'settings'
    # `settings` has view/update and nothing else (docs/02 §2.1), so every write
    # maps onto update — there is no `settings.create` to fall back to.
    permission_action_map = {'create': 'update', 'update': 'update',
                             'partial_update': 'update', 'destroy': 'update'}
    activity_model = 'ReportTemplate'
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['frequency', 'stream', 'academic_class', 'is_active']
    ordering_fields = ['name', 'created_at']

    @action(detail=True, methods=['post'])
    def questions(self, request, pk=None):
        """`POST /api/report-templates/<id>/questions/` — what this one asks.

        `{"questions": [12, 9, 30]}` — the whole list, in the order it is asked,
        replacing whatever was there. An empty list puts the template back on
        its section, which is the quick path: most institutions want the whole
        section and should not have to tick it.

        This is what lets a daily sheet of three questions and a monthly review
        of twelve share নামাজ from one bank rather than keeping two copies of
        it that drift apart.
        """
        template = self.get_object()
        body = TemplateQuestionsSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        count = set_template_questions(template, body.validated_data['questions'])
        log_activity(
            action=ActivityAction.UPDATE, user=request.user, request=request,
            branch=template.branch, obj=template, model='ReportTemplate',
            summary=f'Set {count} questions on {template.name}',
            summary_bn=f'{template.name} — {count}টি প্রশ্ন নির্ধারণ করা হয়েছে',
            after={'questions': body.validated_data['questions']}, atomic=False,
        )
        return Response(ReportTemplateSerializer(
            template, context={'request': request}).data)


class ReportAssignmentViewSet(ActivityLogMixin, BranchScopedViewSet):
    """Who is responsible for which sheet.

    Writing it is `settings.update` — handing out responsibility is the office's
    act — while any holder of `conduct.view` may read it, because "who is meant
    to be filling this" is a question a teacher and a principal both ask.

    It directs and chases; it does not fence anybody out (see the model).
    """

    queryset = ReportAssignment.objects.select_related(
        'template', 'academic_class', 'section', 'teacher')
    serializer_class = ReportAssignmentSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'conduct'
    permission_action_map = {'list': 'view', 'retrieve': 'view'}
    activity_model = 'ReportAssignment'
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['template', 'academic_class', 'section', 'teacher']
    ordering_fields = ['template', 'academic_class', 'created_at']

    def get_permissions(self):
        # Reading is `conduct.view`; changing who is responsible is a setting.
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            self.permission_resource = 'conduct'
        else:
            self.permission_resource = 'settings'
            self.permission_action_map = {
                'create': 'update', 'update': 'update',
                'partial_update': 'update', 'destroy': 'update',
            }
        return super().get_permissions()


class ConductSheetView(APIView):
    """`GET|POST /api/conduct/sheet/` — the grid a teacher fills.

    GET takes `?class=&template=&section=&date=` and answers with the items,
    the students in roll order, and whatever is already filled. POST takes the
    dirty rows back.

    `date` rather than `period`: the screen knows today, and the server knows
    what today means for a monthly template. The alternative is every caller
    computing ISO week numbers, and getting January wrong.
    """

    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'conduct'
    # A plain APIView has no `action`, so the method is all there is — and a
    # POST here is `take`, not `update`: filling today's sheet is the ordinary
    # act, and correcting an old one is the one that costs more.
    permission_action_map = {'get': 'view', 'post': 'take'}
    action = 'list'

    def get_permissions(self):
        self.permission_action_map = {
            'list': 'view' if self.request.method in ('GET', 'HEAD') else 'take',
        }
        return super().get_permissions()

    def resolve(self, request, data):
        branch = get_branch(request)
        academic_class = scoped_class(request, data.get('class') or data.get('academic_class'))

        template_id = data.get('template')
        candidates = templates_for(branch, academic_class)
        if template_id:
            template = next((t for t in candidates if str(t.pk) == str(template_id)), None)
            if template is None:
                raise NotFound('No such report for this class · এই শ্রেণির জন্য এমন রিপোর্ট নেই।')
        elif candidates:
            # The most specific template, so the screen opens on the right one
            # without asking for it (CLAUDE.md §7b).
            template = candidates[0]
        else:
            raise ValidationError({
                'template': 'This institution has no report set up yet · '
                            'এই প্রতিষ্ঠানের কোনো রিপোর্ট এখনো তৈরি হয়নি।',
            })

        section = None
        raw_section = data.get('section')
        if raw_section:
            section = (Section.objects.for_branch(branch)
                       .filter(pk=raw_section, academic_class=academic_class).first())
            if section is None:
                raise NotFound('No such section · এমন কোনো শাখা নেই।')

        period = parse_period(template.frequency, data.get('date') or data.get('period'))
        return template, academic_class, section, period

    def get(self, request):
        template, academic_class, section, period = self.resolve(request, request.GET)
        return Response(sheet(template, academic_class=academic_class,
                              section=section, period=period))

    def post(self, request):
        body = SaveSheetSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        template, academic_class, section, period = self.resolve(request, request.data)
        result = save_sheet(
            template=template, academic_class=academic_class, section=section,
            period=period, rows=data['rows'],
            teacher=teacher_for_user(request.user), actor=request.user,
        )

        log_activity(
            action=ActivityAction.UPDATE, user=request.user, request=request,
            branch=template.branch, obj=template, model='ReportTemplate',
            summary=(f'Filled {template.name} for {academic_class} ({period}): '
                     f'{result["saved"]} students'),
            summary_bn=f'{academic_class} — {period} রিপোর্ট সংরক্ষণ করা হয়েছে',
            after={'saved': result['saved'], 'skipped': len(result['skipped']),
                   'period': period},
            # The register's rule: an audit table that is momentarily full must
            # not be what stops a teacher recording their class.
            atomic=False,
        )
        return Response(result, status=status.HTTP_200_OK)


class StudentConductView(APIView):
    """`GET /api/conduct/student/<id>/` — one student's history.

    What a guardian is shown at the counter, and what a class teacher reads
    before a parents' meeting.
    """

    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'conduct'
    action = 'list'
    permission_action_map = {'list': 'view'}

    def get(self, request, pk):
        student = (Student.objects.for_branch(get_branch(request))
                   .filter(pk=pk).first())
        if student is None:
            raise NotFound('No such student in this institution · এই প্রতিষ্ঠানে এমন শিক্ষার্থী নেই।')

        # A scoped teacher reads their own classes' students and nobody else's.
        branch = get_branch(request)
        if teacher_scope_applies(request.user, branch):
            teacher = teacher_for_user(request.user)
            scope = teacher_class_scope(teacher) if teacher is not None else set()
            classes = set(student.enrolments.values_list('academic_class_id', flat=True))
            if not (classes & set(scope)):
                raise NotFound('No such student in this institution · এই প্রতিষ্ঠানে এমন শিক্ষার্থী নেই।')

        return Response({
            'student': student.pk,
            'name': student.name_bn or student.name,
            'reports': student_history(student),
        })


class StudentReportViewSet(ActivityLogMixin, BranchScopedViewSet):
    """The filled sheets, for reports and exports. Read and correct, never create
    — a sheet is written by `/api/conduct/sheet/`, which owns the rules."""

    queryset = (StudentReport.objects
                .select_related('template', 'student', 'enrolment', 'filled_by')
                .prefetch_related('answers'))
    serializer_class = StudentReportSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'conduct'
    permission_action_map = {'partial_update': 'update', 'update': 'update'}
    http_method_names = ['get', 'patch', 'head', 'options']
    activity_model = 'StudentReport'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['template', 'student', 'enrolment', 'period', 'status']
    search_fields = ['student__name', 'student__name_bn', 'remarks']
    ordering_fields = ['period', 'created_at']
