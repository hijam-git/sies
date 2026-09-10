"""`TeacherScopedMixin` — the second gate (docs/02 §2.4, docs/08 D6).

A permission answers *what verb*. An assignment answers **which classes**. Both
apply:

    can this teacher take attendance?   → permission:  attendance.take
    for THIS class?                     → assignment:  is it one of theirs?

This mixin is the only place the second question is asked of a request. It sits
**alongside** `BranchScopedViewSet` and narrows further:

    class EnrolmentViewSet(TeacherScopedMixin, BranchScopedViewSet):
        teacher_scope_field = 'academic_class'

It lives in `academics` rather than in `core` because the scope is defined by
academic tables — `AcademicClass.class_teacher`, `Section.in_charge`,
`SubjectAssignment` — and `core` depends on no app (docs/06 §2). The attendance,
marks and student viewsets import it from here.
"""

from core.middleware import get_branch

from .services import teacher_class_scope, teacher_for_user, teacher_scope_applies


class TeacherScopedMixin:
    """Narrow a branch-scoped queryset to the caller's own classes, if they are
    a teacher and the institution has the restriction on.

    Out-of-scope rows are **filtered out of the queryset**, not rejected by a
    permission check. That is deliberate and it is what produces the required
    behaviour: `get_object()` raises Http404 for a class that is not theirs, so
    the answer is **404, not 403** — 403 confirms the row exists, which is what a
    probe is looking for (CLAUDE.md §5). The same filtering also makes the
    restriction read as a *shorter list* on the class picker rather than as an
    error the teacher cannot act on (D6).
    """

    #: Path from this viewset's model to `AcademicClass`. `'id'` when the model
    #: IS AcademicClass; `'academic_class'` on Section, Subject, Enrolment and
    #: the routine; `'enrolment__academic_class'` on an attendance row.
    teacher_scope_field = 'academic_class'

    #: Set False on a viewset a teacher must always see whole — the bell
    #: schedule, for instance, which is institution-wide by construction.
    teacher_scope_enabled = True

    def scoped_session(self):
        """The session the scope is evaluated for.

        `?session=` when the caller named one, otherwise the branch's current
        session. Scope is per session because `AcademicClass` is: a teacher who
        was class teacher of Class 5 in 2026 must not still reach it in 2027
        (D6).

        None means "every session this teacher has ever been assigned to", which
        is the right answer for a request that names no session — narrower than
        it looks, since a teacher's assignments are only ever to their own past
        classes.
        """
        requested = self.request.GET.get('session', '').strip()
        if requested:
            from branches.models import Session
            return Session.objects.filter(pk=requested).first()
        return None

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.teacher_scope_enabled:
            return queryset

        # `get_branch()` and not `request.branch`: the latter is a
        # SimpleLazyObject, so an identity check against it never behaves
        # (CLAUDE.md §5). Here it also has to be the unwrapped Branch, because
        # the switch is read off it as an attribute.
        branch = get_branch(self.request)
        if not teacher_scope_applies(self.request.user, branch):
            return queryset

        teacher = teacher_for_user(self.request.user)
        class_ids = teacher_class_scope(teacher, session=self.scoped_session())

        # An empty scope filters to nothing rather than to everything. A teacher
        # with no assignments yet sees an empty class list and asks the office —
        # the failure that files a support ticket, rather than the one nobody
        # ever mentions.
        return queryset.filter(**{f'{self.teacher_scope_field}__in': class_ids})
