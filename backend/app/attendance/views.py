"""The attendance API — docs/02 §5.1, exactly the four endpoints it specifies.

    GET  /api/attendance/register/?class=&section=&month=2026-03
    POST /api/attendance/register/bulk/
    GET  /api/attendance/my-day/?date=
    POST /api/attendance/class/

None of these is plain CRUD, which is why none of them is a `ModelViewSet`:
1,800 cells cannot be 1,800 requests, and the grid needs one request that
carries the dirty cells and one that returns the whole month.

**Two gates apply to every one of them** (docs/08 D6):

    can this user take attendance?   → permission:  attendance.take
    for THIS class?                  → assignment:  is it one of theirs?

The first is `HasResourcePermission`. The second is `TeacherScopedMixin` from
`academics.viewsets`, mixed in above `BranchScopedMixin` so the queryset is
narrowed to the institution first and to the teacher's own classes second. Both
produce **404, not 403** for a class the caller may not reach — a 403 confirms
the class exists, which is what a probe is looking for (CLAUDE.md §5).

The views are thin (CLAUDE.md §4.3). Every rule and every write is in
`services.py`, inside `transaction.atomic()`.
"""

from django.http import Http404
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from academics.models import AcademicClass, Section, Subject
from academics.services import teacher_for_user
from academics.viewsets import TeacherScopedMixin
from accounts.permissions import HasResourcePermission
from accounts.services import ActivityAction, log_activity
from core.middleware import ALL_BRANCHES, get_branch
from core.viewsets import BranchScopedMixin

from .serializers import (ClassAttendanceSaveSerializer,
                          ClassRosterQuerySerializer, MyDaySerializer,
                          RegisterBulkSerializer, RegisterQuerySerializer)
from .services import (month_register, period_roster, resolve_period,
                       save_class_attendance, save_register, teacher_today)


class AttendanceView(TeacherScopedMixin, BranchScopedMixin, generics.GenericAPIView):
    """What all four endpoints share: the branch, the class, and both gates.

    The queryset is `AcademicClass` rather than an attendance model on purpose.
    Everything these endpoints do is addressed by *class* — the register, the
    roster, the period — so the class is the object whose visibility decides the
    answer, and resolving it through the scoped queryset is what makes an
    out-of-scope class a 404 without a single explicit permission check.
    """

    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'attendance'

    queryset = AcademicClass.objects.select_related('session', 'stream')
    # The queryset's model IS AcademicClass, so the teacher scope filters on its
    # own primary key (`academics.viewsets.TeacherScopedMixin`).
    teacher_scope_field = 'id'

    #: `HasResourcePermission` reads `view.action` and there is none on a plain
    #: APIView, where a bare POST would otherwise map to `update`. Naming it
    #: here is what makes `attendance.take` — the checkbox an admin actually
    #: ticks for a teacher — authorise taking attendance.
    action = 'list'
    permission_action_map = {'list': 'view', 'take': 'take'}

    def current_branch(self):
        """The institution this request is about, or a 404.

        `get_branch()` and not `request.branch`: the latter is a
        `SimpleLazyObject`, so `request.branch is None` is **always False** and a
        check written against it silently passes for everyone (CLAUDE.md §5).

        A platform admin who has not chosen an institution gets a 404 and not a
        400, because "the register of every institution at once" names no class
        and no register — there is nothing here to answer with.

        `hasattr(branch, 'pk')` is NOT the test. `resolve_branch` hands a
        platform admin the raw string from `?branch=6` — the middleware
        deliberately does not resolve it, since it runs before authentication and
        must not query (docs/01 §5.2). Testing for `.pk` therefore 404'd every
        attendance endpoint for the platform admin while the identical request
        from a principal worked. That is the fourth place this exact mistake was
        made, which is why the resolving now happens in one shared helper.
        """
        from core.viewsets import writable_branch
        from rest_framework.exceptions import ValidationError

        try:
            return writable_branch(self.request)
        except ValidationError:
            # This view answers 404 rather than 400 where the branch cannot be
            # resolved: "the register of every institution at once" names no
            # class and no register, so there is nothing here to answer with.
            raise Http404

    def scoped_class(self, class_id):
        """The requested class, if this caller may reach it. Otherwise 404.

        Both gates are already in this queryset: `BranchScopedMixin` removed
        every other institution's classes, `TeacherScopedMixin` removed the ones
        this teacher is not assigned to. So a wrong-branch class and an
        unassigned class produce the identical answer, which is the point —
        neither reply tells the caller the class exists.
        """
        academic_class = self.get_queryset().filter(pk=class_id).first()
        if academic_class is None:
            raise Http404
        return academic_class

    def scoped_section(self, academic_class, section_id):
        """A section of *academic_class*, or None when none was asked for."""
        if section_id in (None, '', 0):
            return None
        section = (Section.objects
                   .for_branch(academic_class.branch_id)
                   .filter(pk=section_id, academic_class=academic_class)
                   .first())
        if section is None:
            raise Http404
        return section


class RegisterView(AttendanceView):
    """`GET /api/attendance/register/?class=&section=&month=2026-03`.

    The month grid of docs/02 §4.4 in one response: the days with their own
    `is_markable` flags, and the students with their cells and totals.

    Unpaginated, deliberately. It is one class for one month — sixty students at
    most — and the grid cannot render half a register: a second page of days
    would have no meaning, and a second page of students would break the
    per-column totals along the bottom.
    """

    action = 'list'
    serializer_class = RegisterQuerySerializer

    def get(self, request):
        query = self.get_serializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data

        branch = self.current_branch()
        academic_class = self.scoped_class(params['class'])
        section = self.scoped_section(academic_class, params.get('section'))

        return Response(month_register(
            branch, academic_class, section, params['month'], user=request.user,
        ))


class RegisterBulkView(AttendanceView):
    """`POST /api/attendance/register/bulk/` — the batch upsert.

    The three properties docs/02 §5.1 requires, and where each one lives:

    1. **Idempotent** — `services.save_register()` upserts on the table's own
       unique key, so the same payload twice writes the same rows.
    2. **Server-authoritative** — markability is re-decided per cell inside the
       service. A future date or an off day lands in `skipped` and never in the
       database, however the client was persuaded to send it.
    3. **One transaction** — the service is `@transaction.atomic`, so a partial
       save cannot leave half a month written.

    `taken_by` comes from `request.user` per cell and is not readable from the
    payload at all (the serializer does not declare it).
    """

    action = 'take'
    serializer_class = RegisterBulkSerializer

    def post(self, request):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        branch = self.current_branch()
        academic_class = self.scoped_class(data['class'])
        section = self.scoped_section(academic_class, data.get('section'))

        result = save_register(
            branch=branch,
            academic_class=academic_class,
            section=section,
            month=data['month'],
            cells=data['cells'],
            user=request.user,
            source=data['source'],
        )

        # Logged after the service's transaction has committed, and with
        # `atomic=False`: the register is not money, and an audit table that is
        # full must not be what stops a teacher marking their class
        # (accounts.services.log_activity).
        log_activity(
            action=ActivityAction.TAKE_ATTENDANCE,
            user=request.user,
            request=request,
            branch=branch,
            model='DailyAttendance',
            object_id=academic_class.pk,
            object_label=f'{academic_class} · {data["month"]}',
            summary=(f'Saved {result["saved"]} attendance cells for '
                     f'{academic_class} ({data["month"]})'),
            summary_bn=f'{academic_class} ({data["month"]}) — হাজিরা সংরক্ষণ করা হয়েছে',
            after={'saved': result['saved'], 'skipped': len(result['skipped'])},
            atomic=False,
        )

        return Response(result)


class MyDayView(AttendanceView):
    """`GET /api/attendance/my-day/?date=` — the teacher's today board (D7).

    Not teacher-*scoped* in the queryset sense: it is filtered to the caller's
    own `ClassRoutine` rows, which is narrower than the D6 class scope already.
    A principal opening it sees an empty board rather than a 403 — they have no
    routine rows, and "nothing scheduled for you" is the honest answer to a
    question about *your* day.
    """

    action = 'list'
    serializer_class = MyDaySerializer

    def get(self, request):
        query = self.get_serializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        self.current_branch()
        teacher = teacher_for_user(request.user)
        on_date = query.validated_data.get('date') or timezone.localdate()

        return Response({
            'date': on_date.isoformat(),
            'periods': teacher_today(teacher, on_date, user=request.user),
        })


class ClassAttendanceView(AttendanceView):
    """`POST /api/attendance/class/` — one period's roster (docs/08 D7).

    GET is here too, and it is what the **Take attendance** button opens: the
    roster defaulted to present, with anything already recorded winning over the
    default. Same URL because it is the same resource — the period's roster —
    read and then written.

    This is the one path where the **attendance window** applies: a period that
    ended more than `Branch.attendance_window_minutes` ago is `window_closed`
    for a subject teacher and still open for whoever holds `attendance.update`.
    """

    serializer_class = ClassAttendanceSaveSerializer

    def initial(self, request, *args, **kwargs):
        # Read is `view`, write is `take`. Set before the permission check runs,
        # because that check reads `self.action`.
        self.action = 'take' if request.method == 'POST' else 'list'
        super().initial(request, *args, **kwargs)

    def get_serializer_class(self):
        # The roster read has no cells to send, and a write whose only mandatory
        # list is optional is a write that can silently do nothing.
        if self.request.method == 'POST':
            return ClassAttendanceSaveSerializer
        return ClassRosterQuerySerializer

    def get(self, request):
        payload = self.get_serializer(data=request.query_params)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        branch = self.current_branch()
        academic_class = self.scoped_class(data['class'])
        section = self.scoped_section(academic_class, data.get('section'))
        period = self._scoped_period(branch, data['period'])

        return Response(period_roster(
            branch=branch, academic_class=academic_class, section=section,
            period=period, on_date=data['date'], user=request.user,
        ))

    def post(self, request):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        branch = self.current_branch()
        academic_class = self.scoped_class(data['class'])
        section = self.scoped_section(academic_class, data.get('section'))
        period = self._scoped_period(branch, data['period'])
        subject = self._scoped_subject(branch, data.get('subject'))

        result = save_class_attendance(
            branch=branch,
            academic_class=academic_class,
            section=section,
            subject=subject,
            period=period,
            on_date=data['date'],
            cells=data['cells'],
            user=request.user,
            source=data['source'],
        )

        log_activity(
            action=ActivityAction.TAKE_ATTENDANCE,
            user=request.user,
            request=request,
            branch=branch,
            model='ClassAttendance',
            object_id=academic_class.pk,
            object_label=f'{academic_class} · {period} · {data["date"]}',
            summary=(f'Saved {result["saved"]} period attendance rows for '
                     f'{academic_class} ({period}, {data["date"]})'),
            summary_bn=f'{academic_class} — ক্লাস হাজিরা সংরক্ষণ করা হয়েছে',
            after={'saved': result['saved'], 'skipped': len(result['skipped'])},
            atomic=False,
        )

        return Response(result)

    def _scoped_period(self, branch, period_id):
        period = resolve_period(branch, period_id)
        if period is None:
            raise Http404
        return period

    def _scoped_subject(self, branch, subject_id):
        if subject_id in (None, '', 0):
            return None
        subject = Subject.objects.for_branch(branch).filter(pk=subject_id).first()
        if subject is None:
            raise Http404
        return subject
