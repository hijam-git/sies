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

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics.models import AcademicClass, Enrolment, Subject
from accounts.permissions import HasResourcePermission
from accounts.models import ActivityAction
from accounts.services import ActivityLogMixin, log_activity
from academics.services import (teacher_class_scope, teacher_for_user,
                                teacher_scope_applies)
from academics.viewsets import TeacherScopedMixin
from core.middleware import get_branch
from core.viewsets import BranchScopedViewSet, BranchScopedReadOnlyViewSet
from students.models import Student

from .grading import DIVISION, GPA, reset_to_preset
from .models import Exam, ExamClass, ExamSchedule, GradeScale, Mark
from notifications.serializers import SendResultSmsSerializer

from .serializers import (ExamClassSerializer, ExamScheduleSerializer,
                          ExamSerializer, GradeScaleSerializer, MarkSerializer,
                          MarksGridSerializer)
from .services import (marks_are_visible_to, publish_exam, save_marks,
                       student_report, student_result, tabulation,
                       unpublish_exam, visible_marks_for)


def own_student_only(request, student):
    """A student's own account may only ask about itself.

    `('student', 'guardian')` and not `'student'` alone: `marks_are_visible_to`
    has always treated the two as one class, and the gate here tested the
    narrower one — so a guardian-typed account holding `exams.view` could read
    any child's marksheet by id. Guardian login is V2 (docs/08 D4), which is
    precisely why the account type must not be the one that falls through.

    A guardian has no `student_profile`, so they resolve to no student and are
    refused until V1 grows the ward link.
    """
    if getattr(request.user, 'user_type', None) not in ('student', 'guardian'):
        return
    own = getattr(request.user, 'student_profile', None)
    if own is None or own.pk != student.pk:
        raise NotFound('No such student in this institution · এই প্রতিষ্ঠানে এমন শিক্ষার্থী নেই।')


def teacher_class_ids(request):
    """The classes this caller may see, or None when they are not scoped.

    The result endpoints are read-only `@action`s, so `TeacherScopedMixin` —
    which narrows a *queryset* — never touched them: a Class 5 teacher with
    `exams.view` could pull Class 9's whole merit sheet by changing one query
    parameter. D6 is a rule about classes, not about querysets.
    """
    branch = get_branch(request)
    if not teacher_scope_applies(request.user, branch):
        return None
    teacher = teacher_for_user(request.user)
    return teacher_class_scope(teacher) if teacher is not None else set()


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
        'unpublish': 'publish',
        # Sending the results IS releasing them (see the action).
        'send_results_sms': 'publish',
        'results_sms_preview': 'view',
        'marks': 'enter',
        'tabulation': 'view',
        'result': 'view',
        'report': 'view',
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

    @action(detail=True, methods=['get'], url_path='results-sms')
    def results_sms_preview(self, request, pk=None):
        """`GET /api/exams/<id>/results-sms/?academic_class=<id>` — what a send would do.

        The principal is about to spend the institution's money on four hundred
        messages, so the screen shows the exact body of the first one, what it
        costs in parts, how many guardians have a number on file, and who does
        not. Nothing is sent by this call.
        """
        from notifications.services import preview_result_sms

        exam = self.get_object()
        academic_class = self._optional_class(exam, request)
        return Response(preview_result_sms(exam, academic_class=academic_class))

    @action(detail=True, methods=['post'], url_path='send-results-sms')
    def send_results_sms(self, request, pk=None):
        """`POST /api/exams/<id>/send-results-sms/` — queue the results to guardians.

        `exams.publish`, not `marks.enter` and not a resource of its own:
        releasing a result to a screen and releasing it to a handset are one
        decision, and it is the principal's. Idempotent — a second press queues
        only the guardians the first one missed (`SmsMessage`'s unique
        constraint), which is what makes a half-finished fan-out safe to repeat.
        """
        from notifications.services import send_result_sms

        exam = self.get_object()
        academic_class = self._optional_class(exam, request)
        body = SendResultSmsSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                summary = send_result_sms(exam, academic_class=academic_class,
                                          actor=request.user)
        except ValueError as exc:
            # The exam is not published. A 400 and not a 500: the caller named a
            # real exam and asked for something that is not allowed yet.
            raise ValidationError({'exam': str(exc)})

        log_activity(
            action=ActivityAction.UPDATE, user=request.user, request=request,
            branch=exam.branch, obj=exam, model='Exam',
            summary=f'Sent {exam.name} results by SMS: {summary["queued"]} queued',
            summary_bn=f'{exam.name} পরীক্ষার ফল এসএমএসে পাঠানো হয়েছে',
            after=summary, atomic=False,
        )
        return Response(summary)

    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        """`POST /api/exams/<id>/unpublish/` — reopen a published result.

        The other half of `publish`. Marks entry refuses a published exam, so
        without this one wrong mark was permanent.
        """
        exam = self.get_object()
        with transaction.atomic():
            unpublish_exam(exam, actor=request.user, request=request)
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

        own_student_only(request, student)
        self._assert_teaches(request, student)

        return Response(student_result(exam, student))

    @action(detail=False, methods=['get'], url_path='student-report')
    def report(self, request):
        """`GET /api/exams/student-report/?student=<id>` — every result of one student.

        The same three gates as `result`, applied to a list: the student must be
        in the caller's institution (404 otherwise), a student account may only
        ask about themselves, and an exam whose results a caller may not see yet
        is simply not in the list — an empty list, rather than a 404, because
        "no published results yet" is a true and ordinary answer.
        """
        raw = str(request.GET.get('student', ''))
        student = None
        if raw.isdigit():
            student = (
                Student.objects.filter(pk=int(raw))
                .for_branch(get_branch(request))
                .first()
            )
        if student is None:
            raise NotFound('No such student in this institution · এই প্রতিষ্ঠানে এমন শিক্ষার্থী নেই।')

        own_student_only(request, student)
        self._assert_teaches(request, student)

        exams = [
            exam for exam in self.get_queryset().filter(marks__student=student).distinct()
            if marks_are_visible_to(exam, request.user)
        ]
        return Response(student_report(student, exams))

    def _assert_teaches(self, request, student):
        """A scoped teacher may only read a student of one of their own classes."""
        scope = teacher_class_ids(request)
        if scope is None:
            return
        classes = set(
            Enrolment.objects.filter(student=student)
            .values_list('academic_class_id', flat=True)
        )
        if not (classes & set(scope)):
            raise NotFound('No such student in this institution · এই প্রতিষ্ঠানে এমন শিক্ষার্থী নেই।')

    def _optional_class(self, exam, request):
        """`?academic_class=` when given, else None for "every class".

        Separate from `_class_param` below, which demands one: the tabulation is
        a sheet of one class and has no meaning without it, while a send covers
        the whole exam unless the principal narrows it.
        """
        raw = str(request.GET.get('academic_class') or
                  request.data.get('academic_class') or '').strip()
        if not raw or not raw.isdigit():
            return None
        academic_class = AcademicClass.objects.filter(
            pk=int(raw), branch_id=exam.branch_id,
        ).first()
        if academic_class is None:
            raise NotFound('No such class in this institution · এই প্রতিষ্ঠানে এমন শ্রেণি নেই।')
        scope = teacher_class_ids(request)
        if scope is not None and academic_class.pk not in scope:
            raise NotFound('No such class in this institution · এই প্রতিষ্ঠানে এমন শ্রেণি নেই।')
        return academic_class

    def _class_param(self, exam, request):
        academic_class = AcademicClass.objects.filter(
            pk=request.GET.get('academic_class'), branch_id=exam.branch_id,
        ).first()
        scope = teacher_class_ids(request)
        if academic_class is not None and scope is not None and academic_class.pk not in scope:
            # Out of scope reads exactly like a class that does not exist, for
            # the reason 404-not-403 exists at all (CLAUDE.md §5).
            raise NotFound('No such class in this institution · এই প্রতিষ্ঠানে এমন শ্রেণি নেই।')
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


class GradeScaleViewSet(ActivityLogMixin, BranchScopedViewSet):
    """Settings → Grading. One scale per বিভাগ; its bands are written whole."""

    permission_classes = [IsAuthenticated, HasResourcePermission]
    # Institution configuration, like fee heads — `settings`, not `exams`. A
    # teacher who may set up a monthly test must not thereby re-grade a year.
    permission_resource = 'settings'
    permission_action_map = {'create': 'update', 'destroy': 'update', 'reset': 'update'}
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    queryset = GradeScale.objects.select_related('stream').prefetch_related('bands')
    serializer_class = GradeScaleSerializer
    filterset_fields = ['stream', 'method', 'is_active']
    activity_model = 'GradeScale'

    @action(detail=True, methods=['post'])
    def reset(self, request, pk=None):
        """`POST /api/grade-scales/<id>/reset/` `{"method": "gpa"|"division"}`.

        Replaces the bands with the standard set for a method — how a বিভাগ
        switches method, and how an edited scale goes back to the standard.
        Published results are unaffected; they were frozen at publish.
        """
        scale = self.get_object()
        method = request.data.get('method') or scale.method
        if method not in (GPA, DIVISION):
            raise ValidationError({'method': 'Choose gpa or division · জিপিএ অথবা কওমি পদ্ধতি বেছে নিন।'})
        with transaction.atomic():
            reset_to_preset(scale, method, actor=request.user)
        scale = self.get_queryset().get(pk=scale.pk)
        return Response(self.get_serializer(scale).data)

