"""The academics API (CLAUDE.md §5, docs/08 D6 and D7).

Every viewset here is branch-scoped, so another institution's row is **404, not
403** (CLAUDE.md §5). The ones a teacher uses to reach students and classes are
*also* `TeacherScopedMixin`, which narrows the same queryset to their own
classes and produces the same 404 for a class that is not theirs.

Two viewsets are deliberately **not** teacher-scoped:

* `PeriodViewSet` — the bell schedule is institution-wide by construction and a
  teacher needs to read all of it to render their own day; and
* `SubjectAssignmentViewSet` — it is the assignment *screen*, an admin tool. A
  teacher scoping their own access grants would be circular.

All of them share the `academics` permission resource, because docs/02 §2.1 puts
classes, sections, subjects, sessions, streams and the routine under one
checkbox: they are edited by the same person on the same screens.
"""

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from rest_framework.exceptions import ValidationError

from accounts.permissions import HasResourcePermission
from accounts.services import ActivityLogMixin
from core.middleware import ALL_BRANCHES, get_branch
from core.viewsets import BranchScopedViewSet, writable_branch

from .models import (AcademicClass, ClassRoutine, Enrolment, Period, Section,
                     Subject, SubjectAssignment)
from .serializers import (AcademicClassSerializer, ClassRoutineSerializer,
                          EnrolmentSerializer, PeriodSerializer,
                          SectionSerializer, SubjectAssignmentSerializer,
                          SubjectSerializer)
from .services import (day_index, enrol_student, grant_from_routine,
                       teacher_for_user)
from .viewsets import TeacherScopedMixin




class AcademicsViewSet(ActivityLogMixin, BranchScopedViewSet):
    """What every academics endpoint has in common."""

    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'academics'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]


class AcademicClassViewSet(TeacherScopedMixin, AcademicsViewSet):
    """Classes. The teacher scope applies to the class list itself, which is
    what makes the restriction read as a shorter picker rather than an error
    (docs/08 D6)."""

    queryset = (AcademicClass.objects
                .select_related('stream', 'session', 'class_teacher')
                .annotate(section_count=Count('sections', distinct=True)))
    serializer_class = AcademicClassSerializer
    activity_model = 'AcademicClass'
    # The model IS AcademicClass, so the scope filters on its own primary key.
    teacher_scope_field = 'id'
    filterset_fields = ['stream', 'session', 'year', 'is_active', 'class_teacher']
    search_fields = ['name', 'name_bn']
    ordering_fields = ['level_order', 'name', 'year', 'created_at']
    # Spelled out because `annotate(Count(...))` makes this an aggregate query,
    # and Django drops `Meta.ordering` from those rather than adding a column to
    # the GROUP BY. Without it the list is unordered and page 2 can repeat a row
    # from page 1 (CLAUDE.md §4.2).
    ordering = ['-year', 'level_order', 'name']


class SectionViewSet(TeacherScopedMixin, AcademicsViewSet):
    queryset = Section.objects.select_related('academic_class', 'in_charge')
    serializer_class = SectionSerializer
    activity_model = 'Section'
    filterset_fields = ['academic_class', 'is_active', 'in_charge']
    search_fields = ['name', 'name_bn', 'room']
    ordering_fields = ['name', 'created_at']


class SubjectViewSet(TeacherScopedMixin, AcademicsViewSet):
    queryset = Subject.objects.select_related('stream', 'academic_class')
    serializer_class = SubjectSerializer
    activity_model = 'Subject'
    filterset_fields = ['stream', 'academic_class', 'is_optional',
                        'has_practical', 'is_active']
    search_fields = ['name', 'name_bn', 'code']
    ordering_fields = ['name', 'code', 'created_at']


class PeriodViewSet(AcademicsViewSet):
    """The bell schedule (docs/08 D7).

    Not teacher-scoped: a period belongs to the institution (or to a stream), not
    to a class, so there is nothing to narrow it by — and a teacher needs the
    whole schedule to render their own day.
    """

    queryset = Period.objects.select_related('stream')
    serializer_class = PeriodSerializer
    activity_model = 'Period'
    filterset_fields = ['stream', 'is_break', 'is_active']
    search_fields = ['name', 'name_bn']
    ordering_fields = ['order', 'start_time', 'created_at']


class ClassRoutineViewSet(TeacherScopedMixin, AcademicsViewSet):
    """The weekly timetable, and the teacher's today board (docs/08 D7)."""

    queryset = ClassRoutine.objects.select_related(
        'session', 'academic_class', 'section', 'subject', 'teacher', 'period',
    )
    serializer_class = ClassRoutineSerializer
    activity_model = 'ClassRoutine'
    filterset_fields = ['session', 'academic_class', 'section', 'subject',
                        'teacher', 'period', 'day_of_week', 'is_active']
    search_fields = ['room', 'subject__name', 'teacher__name']
    ordering_fields = ['day_of_week', 'period', 'created_at']

    # Placing a teacher in a cell is also the moment they are given the class
    # (docs/08 D6). Doing it in both hooks rather than in the serializer keeps
    # the grant on the write path only — a dry  grants nothing.
    def perform_create(self, serializer):
        with transaction.atomic():
            super().perform_create(serializer)
            grant_from_routine(serializer.instance)

    def perform_update(self, serializer):
        with transaction.atomic():
            super().perform_update(serializer)
            grant_from_routine(serializer.instance)

    @action(detail=False, methods=['get'], url_path='today')
    def today(self, request):
        """`GET /api/class-routines/today/` — the caller's classes, today.

        The board docs/08 D7 describes. Unpaginated: it is one day of one
        teacher's schedule, eight rows at most, and it renders as a vertical
        list of period cards on a phone (CLAUDE.md §7a).

        Filtered by `teacher` explicitly rather than relying on
        `TeacherScopedMixin`: the class scope is wider than "rows I teach" — it
        includes classes they are merely in charge of — and a board of periods
        somebody else is teaching is not a to-do list.
        """
        teacher = teacher_for_user(request.user)
        if teacher is None:
            # An account with no teacher profile has no board. Empty, not an
            # error: a principal opening the teacher dashboard should see
            # "nothing scheduled for you", not a 403.
            return Response([])

        rows = self.get_queryset().filter(
            teacher=teacher,
            day_of_week=day_index(timezone.localdate()),
            is_active=True,
            period__is_break=False,
        ).order_by('period__order')

        return Response(self.get_serializer(rows, many=True).data)

    @action(detail=False, methods=['get'], url_path='my-routine')
    def my_routine(self, request):
        """`GET /api/class-routines/my-routine/?session=` — the caller's week.

        The other half of the today board: a teacher wants to know when they
        teach and what, not only what is left today. Unpaginated for the same
        reason `today` is — one teacher's week is at most seven days of a bell
        schedule, and it is drawn as a grid that needs every cell at once.

        **`?teacher=` is ignored here, deliberately.** The list endpoint accepts
        it and is narrowed by `TeacherScopedMixin`, which means a class teacher
        can legitimately see who else teaches *their* class. This action answers
        a different question — *my* week — so it is filtered to the caller's own
        `Teacher` row and nothing a client sends can widen it. Passing another
        teacher's id returns the caller's own rows, never theirs.

        Built off `ClassRoutine.objects` rather than `self.get_queryset()`
        because the D6 class scope is the wrong gate for this: a routine row is
        already the narrowest possible claim on a class, and a teacher whose
        routine row has no matching `SubjectAssignment` would otherwise lose a
        period off their own timetable. `teacher.branch_id` keeps it branch-safe
        without the mixin — a teacher belongs to exactly one institution.
        """
        teacher = teacher_for_user(request.user)
        if teacher is None:
            # A principal or an accountant has no routine of their own. Empty
            # rather than 403: "nothing is assigned to you" is the honest answer
            # to a question about *your* week, and the screen says who assigns it.
            return Response({'session': None, 'rows': []})

        session, addressable = self._routine_session(request, teacher)
        if not addressable:
            # A session id that is not this institution's names no week of
            # theirs. Empty and 200, not 404: the id came from a query string,
            # and confirming which ids exist is what a probe is after.
            return Response({'session': None, 'session_name': '', 'rows': []})

        rows = (ClassRoutine.objects
                .filter(branch_id=teacher.branch_id, teacher=teacher, is_active=True)
                .select_related('session', 'academic_class', 'section', 'subject',
                                'teacher', 'period'))
        if session is not None:
            rows = rows.filter(session=session)

        rows = rows.order_by('day_of_week', 'period__order')
        return Response({
            'session': session.pk if session is not None else None,
            'session_name': session.name if session is not None else '',
            'rows': self.get_serializer(rows, many=True).data,
        })

    @staticmethod
    def _routine_session(request, teacher):
        """`(session, addressable)` — `?session=` if named, else the current one.

        Defaulting server-side keeps the screen free of a session picker the
        teacher would have to understand before seeing anything — and a routine
        without a session is every year's timetable stacked in one grid.

        The flag separates the two ways of having no session: an institution
        that has not opened one yet (show the whole timetable) from a caller who
        named a session that is not theirs (show nothing). Returning bare None
        for both would turn a foreign session id into "every session you have".
        """
        from branches.models import Session

        requested = request.query_params.get('session', '').strip()
        sessions = Session.objects.filter(branch_id=teacher.branch_id)
        if requested:
            if not requested.isdigit():
                raise ValidationError({'session': 'Not a session id · সঠিক শিক্ষাবর্ষ নয়।'})
            found = sessions.filter(pk=requested).first()
            return found, found is not None
        return sessions.filter(is_current=True).first(), True


class EnrolmentViewSet(TeacherScopedMixin, AcademicsViewSet):
    """Students in classes.

    Teacher-scoped, so a teacher sees the students of their own classes and
    nobody else's — the "Student list" row of D6's action table.

    Creation goes through `services.enrol_student()` so the roll and the
    admission number are issued inside the same transaction that writes the row;
    that is what makes them gapless (CLAUDE.md §4.4).
    """

    queryset = Enrolment.objects.select_related(
        'student', 'session', 'academic_class', 'section',
    )
    serializer_class = EnrolmentSerializer
    activity_model = 'Enrolment'
    permission_resource = 'admissions'
    filterset_fields = ['session', 'academic_class', 'section', 'status',
                        'is_hostel', 'is_transport', 'is_active']
    search_fields = ['admission_number', 'student__name', 'student__name_bn']
    ordering_fields = ['roll', 'admission_number', 'enrolled_on', 'created_at']

    def save_new(self, serializer):
        """`save_new` and not `perform_create`, so `ActivityLogMixin` still logs.

        The base `BranchScopedMixin.perform_create` cannot be used: it calls
        `serializer.save()` directly, which would leave `roll` and
        `admission_number` unset — they are read-only on the serializer precisely
        because the service issues them.
        """
        serializer.instance = enrol_student(
            branch=writable_branch(self.request),
            created_by=self.request.user,
            **serializer.validated_data,
        )


class SubjectAssignmentViewSet(AcademicsViewSet):
    """Staff → Assignments (docs/08 D6).

    Not teacher-scoped: this is the admin screen that *grants* the scope, and a
    teacher filtering their own grants would be circular. It is gated on
    `academics` like the rest of this app, so only someone who can edit the
    academic frame can widen what a teacher reaches.
    """

    queryset = SubjectAssignment.objects.select_related(
        'session', 'teacher', 'subject', 'academic_class', 'section',
    )
    serializer_class = SubjectAssignmentSerializer
    activity_model = 'SubjectAssignment'
    filterset_fields = ['session', 'teacher', 'subject', 'academic_class',
                        'section', 'is_active']
    search_fields = ['teacher__name', 'subject__name', 'academic_class__name']
    ordering_fields = ['created_at']
