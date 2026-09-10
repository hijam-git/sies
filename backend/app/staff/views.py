"""The staff API (CLAUDE.md §5).

Two resources, because docs/02 §2.1 has two checkboxes: `teachers` and
`employees`. That separation is not cosmetic — an institution routinely wants an
office manager who maintains the non-teaching roster and never sees a teacher's
salary, and a single `staff` permission could not express it.

Both viewsets are ordinary `BranchScopedViewSet`s, so another institution's row
is **404, not 403** — 403 confirms it exists (CLAUDE.md §5).
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import HasResourcePermission
from accounts.services import ActivityLogMixin
from core.middleware import ALL_BRANCHES, get_branch
from core.viewsets import BranchScopedViewSet
from rest_framework.exceptions import ValidationError

from .models import Employee, Teacher, TeacherQualification
from .serializers import (EmployeeSerializer, TeacherQualificationSerializer,
                          TeacherSerializer)
from .services import create_employee, create_teacher


def _writable_branch(request):
    """The branch a write lands in, or a 400 saying which parameter is missing.

    A platform admin posting without `?branch=` has not said which institution to
    create the staff member in, and "create this teacher in every institution"
    has no meaning. `get_branch()` and not `request.branch`, because the latter is
    a `SimpleLazyObject` and an `is None` check against it is False even when the
    branch is None (CLAUDE.md §5).
    """
    branch = get_branch(request)
    if branch is None or branch == ALL_BRANCHES or not hasattr(branch, 'pk'):
        raise ValidationError({
            'branch': ('Choose an institution before creating this. '
                       'Add ?branch=<id> to the request.'),
        })
    return branch


class TeacherViewSet(ActivityLogMixin, BranchScopedViewSet):
    """Teaching staff."""

    queryset = Teacher.objects.select_related('branch', 'user').prefetch_related(
        'streams', 'qualifications',
    )
    serializer_class = TeacherSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'teachers'
    activity_model = 'Teacher'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['employment_status', 'is_active', 'is_class_teacher', 'streams']
    search_fields = ['name', 'name_bn', 'teacher_id', 'phone', 'designation',
                     'specialization']
    ordering_fields = ['name', 'teacher_id', 'joining_date', 'created_at']

    def save_new(self, serializer):
        """Create through the service, so the teacher id is issued under a lock.

        `save_new` rather than `perform_create`, so `ActivityLogMixin` still
        writes the audit entry — overriding `perform_create` here would shadow it.
        The base `BranchScopedMixin.perform_create` cannot be used either: it
        calls `serializer.save()` directly, which would leave `teacher_id` unset.
        """
        branch = _writable_branch(self.request)
        data = dict(serializer.validated_data)
        streams = data.pop('streams', None)
        serializer.instance = create_teacher(
            branch=branch, streams=streams, created_by=self.request.user, **data,
        )

    @action(detail=True, methods=['get'], url_path='qualifications')
    def qualifications(self, request, pk=None):
        """`GET …/teachers/<id>/qualifications/` — the degrees this teacher holds.

        Unpaginated: a teacher has a handful, and the profile screen renders all
        of them at once. `self.get_object()` first, so an out-of-branch id is a
        404 here exactly as it is on the detail route.
        """
        teacher = self.get_object()
        serializer = TeacherQualificationSerializer(
            teacher.qualifications.all(), many=True, context=self.get_serializer_context(),
        )
        return Response(serializer.data)


class EmployeeViewSet(ActivityLogMixin, BranchScopedViewSet):
    """Non-teaching staff."""

    queryset = Employee.objects.select_related('branch', 'user')
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'employees'
    activity_model = 'Employee'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['employment_status', 'is_active', 'department', 'duty_shift']
    search_fields = ['name', 'name_bn', 'employee_id', 'phone', 'designation',
                     'department']
    ordering_fields = ['name', 'employee_id', 'joining_date', 'created_at']

    def save_new(self, serializer):
        branch = _writable_branch(self.request)
        serializer.instance = create_employee(
            branch=branch, created_by=self.request.user, **serializer.validated_data,
        )


class TeacherQualificationViewSet(ActivityLogMixin, BranchScopedViewSet):
    """Degrees, edited from the teacher's profile screen.

    Gated on `teachers` rather than a resource of its own: it is part of the
    teacher record, and a permission the catalogue does not describe is one the
    SPA cannot render a checkbox for.
    """

    queryset = TeacherQualification.objects.select_related('teacher')
    serializer_class = TeacherQualificationSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'teachers'
    activity_model = 'TeacherQualification'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['teacher', 'year']
    search_fields = ['degree', 'institution', 'result', 'teacher__name']
    ordering_fields = ['year', 'degree', 'created_at']
