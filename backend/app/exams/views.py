"""The exams API (CLAUDE.md §5, docs/02 §4.7, docs/06 #12).

Three gates apply, in this order, and they are different questions:

1. **branch** — `BranchScopedViewSet`. Another institution's exam is 404, never
   403 (CLAUDE.md §5).
2. **permission** — `exams.*` for the exam and its schedule, `marks.*` for the
   entry grid. Two resources, because a teacher gets `marks.enter` without ever
   getting `exams.create` or `exams.publish`.
3. **assignment** — docs/08 D6. A teacher's marks grid is narrowed to their own
   classes by `TeacherScopedMixin` and to their own *subjects* by
   `services.assert_can_enter_marks`. The class-level gate is not enough: being
   class teacher of Class 5 is not a licence to enter its Arabic marks.

Marks are additionally invisible to a student until the exam is published —
`services.visible_marks_for`, applied to the queryset so an unpublished mark is
a 404 rather than a 403 that confirms it exists.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics.models import AcademicClass, Subject
from accounts.permissions import HasResourcePermission
from accounts.services import ActivityLogMixin
from academics.viewsets import TeacherScopedMixin
from core.viewsets import BranchScopedViewSet, BranchScopedReadOnlyViewSet
from students.models import Student

from .models import Exam, ExamClass, ExamSchedule, Mark
from .serializers import (ExamClassSerializer, ExamScheduleSerializer,
                          ExamSerializer, MarkSerializer, MarksGridSerializer)
from .services import (marks_are_visible_to, publish_exam, save_marks,
                       student_result, tabulation, visible_marks_for)


class ExamsViewSet(ActivityLogMixin, BranchScopedViewSet):
    """What the exam-administration endpoints have in common."""

    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'exams'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]


class ExamViewSet(ExamsViewSet):
    """Exams, their classes and the two read-only result views."""

    queryset = Exam.objects.select_related('session', 'stream', 'published_by')
    serializer_class = ExamSerializer
    filterset_fields = ['session', 'stream', 'exam_type', 'status']
    search_fields = ['name', 'name_bn']
    ordering_fields = ['starts_on', 'ends_on', 'name', 'created_at']
    activity_model = 'Exam'

    # `publish` names its own action rather than falling through to `update`.
    # An unmapped custom POST resolves to `update` (docs/WORKLOG F1), which would
    # mean `exams.update` — held by anyone who can create a test — releases
    # results. `marks` is `marks.enter` for the mirror-image reason: entering
    # marks must not require the permission to create an exam.
    permission_action_map = {
        'publish': 'publish',
        'marks': 'enter',
        'tabulation': 'view',
        'result': 'view',
    }

    def get_permissions(self):
        # The marks grid is the `marks` resource, not `exams`. Set on the
        # instance rather than by a second permission class so the resource and
        # the action always resolve from the same place.
        if self.action == 'marks':
            self.permission_resource = 'marks'
        else:
            self.permission_resource = 'exams'
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """`POST /api/exams/<id>/publish/` — principal-only.

        The permission is checked twice, deliberately: here by
        `permission_action_map` so the SPA gets a clean 403, and again inside
        `services.publish_exam`, because a management command or a Celery task
        never passes through a viewset at all.
        """
        exam = self.get_object()
        publish_exam(exam, actor=request.user, request=request)
        return Response(ExamSerializer(exam, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def marks(self, request, pk=None):
        """`POST /api/exams/<id>/marks/` — save one paper's grid.

        The whole grid in one request and one transaction, like the attendance
        register. `services.save_marks` owns the upsert, the subject-scope check
        and the idempotency; this view resolves ids and reports.
        """
        exam = self.get_object()
        body = MarksGridSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        subject = Subject.objects.filter(
            pk=body.validated_data['subject'], branch_id=exam.branch_id,
        ).first()
        if subject is None:
            # 404 and not 400: a subject id that belongs to another institution
            # must read exactly like one that does not exist (CLAUDE.md §5).
            raise NotFound('No such subject in this institution · এই প্রতিষ্ঠানে এমন বিষয় নেই।')

        result = save_marks(
            exam=exam, subject=subject, rows=body.validated_data['rows'],
            actor=request.user, request=request,
        )
        return Response(result)

    @action(detail=True, methods=['get'])
    def tabulation(self, request, pk=None):
        """`GET /api/exams/<id>/tabulation/?academic_class=<id>` — the class sheet."""
        exam = self.get_object()
        academic_class = self._class_param(exam, request)
        return Response(tabulation(exam, academic_class))

    @action(detail=True, methods=['get'])
    def result(self, request, pk=None):
        """`GET /api/exams/<id>/result/?student=<id>` — one student's marksheet.

        Computed on read (docs/05 §5.4 — `Result` is V2). Refused before the
        exam is published for a student reading their own: a result assembled
        from half-entered marks is a number they will quote back.
        """
        exam = self.get_object()
        student = Student.objects.filter(
            pk=request.GET.get('student'), branch_id=exam.branch_id,
        ).first()
        if student is None:
            raise NotFound('No such student in this institution · এই প্রতিষ্ঠানে এমন শিক্ষার্থী নেই।')

        if not marks_are_visible_to(exam, request.user):
            # 404, not 403: "it exists but you may not see it" is exactly what
            # an unpublished result must not reveal.
            raise NotFound('This result is not published yet · ফল এখনো প্রকাশিত হয়নি।')

        if getattr(request.user, 'user_type', None) == 'student':
            own = getattr(request.user, 'student_profile', None)
            if own is None or own.pk != student.pk:
                raise NotFound('No such student in this institution · এই প্রতিষ্ঠানে এমন শিক্ষার্থী নেই।')

        return Response(student_result(exam, student))

    def _class_param(self, exam, request):
        academic_class = AcademicClass.objects.filter(
            pk=request.GET.get('academic_class'), branch_id=exam.branch_id,
        ).first()
        if academic_class is None:
            raise ValidationError({
                'academic_class': 'Name the class · কোন শ্রেণি তা উল্লেখ করুন।',
            })
        return academic_class


class ExamClassViewSet(ExamsViewSet):
    """Which classes sit an exam."""

    queryset = ExamClass.objects.select_related('exam', 'academic_class')
    serializer_class = ExamClassSerializer
    filterset_fields = ['exam', 'academic_class']
    activity_model = 'ExamClass'


class ExamScheduleViewSet(ExamsViewSet):
    """The paper-by-paper timetable."""

    queryset = ExamSchedule.objects.select_related(
        'exam', 'academic_class', 'subject', 'invigilator',
    )
    serializer_class = ExamScheduleSerializer
    filterset_fields = ['exam', 'academic_class', 'subject', 'date']
    ordering_fields = ['date', 'start_time']
    activity_model = 'ExamSchedule'


class MarkViewSet(TeacherScopedMixin, BranchScopedReadOnlyViewSet):
    """Marks, read-only over the API.

    Read-only because there is exactly one supported way to write a mark —
    `POST /api/exams/<id>/marks/` — and it is a grid, in a transaction, with the
    subject-scope check on it. A per-row `create` here would be a second write
    path that skips both.

    `teacher_scope_field` reaches `AcademicClass` through the enrolment, which
    is the class the student sat this exam in — not the class they are in today.
    """

    queryset = Mark.objects.select_related('student', 'subject', 'exam', 'enrolment')
    serializer_class = MarkSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'marks'
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['exam', 'subject', 'student', 'enrolment', 'is_absent']
    teacher_scope_field = 'enrolment__academic_class'

    def get_queryset(self):
        # Applied last, over the branch- and teacher-scoped queryset: a student
        # reads only their own marks, and only after the exam is published.
        return visible_marks_for(super().get_queryset(), self.request.user)
