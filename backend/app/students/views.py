"""The students API (CLAUDE.md §5).

Two endpoint families live here and they are deliberately not the same thing:

* `/api/students/`, `/api/guardians/`, `/api/admissions/`, `/api/documents/` —
  staff screens, gated on the permission catalogue and scoped to the caller's
  institution by `BranchScopedViewSet`. A wrong-branch row is **404, not 403**;
  403 confirms it exists.

* `/api/me/…` — self-service (docs/02 §2.5, docs/08 D4). Filtered to
  `request.user`'s own student record and granting nothing else. It is **not** a
  weak `students.view`: there is no id to change, because the only row these
  views can reach is the one whose `user` is the caller. Modelling this as a
  staff permission is exactly how a student ends up listing the whole class.
"""

from django.db import transaction
from django.http import FileResponse, Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasResourcePermission, has_permission
from core.middleware import ALL_BRANCHES, get_branch
from core.viewsets import BranchScopedViewSet, writable_branch
from accounts.services import ActivityLogMixin

from academics.viewsets import TeacherScopedMixin

from .models import Admission, Document, Guardian, Student, StudentGuardian
from .serializers import (AdmissionSerializer, AdmitSerializer,
                          DocumentSerializer, GuardianSerializer,
                          MyDocumentSerializer, MyProfileSerializer,
                          StudentGuardianSerializer, StudentSerializer,
                          guardian_summary)
from .services import (admit_student, allocate_student_id, create_application,
                       enable_student_login, link_guardian)




def _no_such_branch():
    raise ValidationError({'branch': 'No institution with that id.'})


class StudentViewSet(ActivityLogMixin, TeacherScopedMixin, BranchScopedViewSet):
    """Student records — identity only. Class and section come from Enrolment.

    No `destroy`: `is_active` is the soft delete (CLAUDE.md §4.2), and a student
    is pointed at by fees, marks and attendance, so a hard delete would be
    refused by PROTECT anyway. Deactivating is a PATCH.

    **Teacher-scoped** (docs/08 D6), reached through the enrolment. Without it,
    `students.view` — which a teacher needs to see their own roster — read every
    student in the institution: phone, NID, address and guardians, including the
    classes the attendance screen bars them from. The register was scoped and
    the record behind it was not.
    """

    teacher_scope_field = 'enrolments__academic_class'

    queryset = Student.objects.select_related('stream', 'branch', 'user').all()
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'students'
    permission_action_map = {
        # Creating a login is not "updating a student" in any sense an admin
        # would recognise, but it is the closest catalogue action there is —
        # `students` has no `manage`. Declared rather than inferred so nobody has
        # to read POST_IS_AN_UPDATE to know what the endpoint costs.
        'enable_login': 'update',
        # GET lists them, POST attaches one, and the pair used to cost
        # `students.update` for both halves — so a teacher who may read a
        # student could not read the guardian's phone number on the same record.
        # Resolved per method in `get_permissions` below.
        'guardians': 'update',
    }
    activity_model = 'Student'
    filterset_fields = ['stream', 'status', 'gender', 'is_active', 'upazila', 'district']
    search_fields = ['name', 'name_bn', 'student_id', 'phone',
                     'birth_certificate_no', 'village', 'upazila']
    ordering_fields = ['name', 'student_id', 'admitted_on', 'created_at']

    def get_permissions(self):
        if self.action == 'guardians' and self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            self.permission_action_map = {**self.permission_action_map,
                                          'guardians': 'view'}
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in ('retrieve', 'list'):
            queryset = queryset.prefetch_related('guardian_links__guardian')
        return queryset

    def save_new(self, serializer):
        """Direct entry — the paper roll typed in, or `import_students`.

        The ID comes from the same platform-wide series `admit_student()` draws
        from, in the same transaction as the insert: an ID allocated and then
        lost to a failed save is a hole in a series whose only promise is that it
        has none.
        """
        branch = writable_branch(self.request)
        with transaction.atomic():
            serializer.save(
                branch=branch,
                student_id=allocate_student_id(),
                created_by=self.request.user,
            )

    @action(detail=True, methods=['post'], url_path='enable-login')
    def enable_login(self, request, pk=None):
        """`POST /api/students/<id>/enable-login/` — docs/08 D4.

        An action on the record, never a step in admission: most young students
        have no phone at all, and requiring one would mean inventing numbers to
        get a child onto the roll.
        """
        student = self.get_object()
        user = enable_student_login(
            student,
            phone=request.data.get('phone'),
            password=request.data.get('password'),
            actor=request.user,
            request=request,
        )
        return Response({'user': user.id, 'phone': user.phone,
                         'must_change_password': user.must_change_password},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'])
    def guardians(self, request, pk=None):
        """List this student's guardians, or attach one.

        POST reuses an existing guardian when the phone already exists in this
        institution — the sibling case, and the reason `Guardian` is its own
        table. It goes through `services.link_guardian` rather than the
        serializer so both this and `admit_student` share one matching rule.
        """
        student = self.get_object()

        if request.method == 'GET':
            links = student.guardian_links.select_related('guardian')
            return Response(StudentGuardianSerializer(links, many=True).data)

        name = (request.data.get('name') or '').strip()
        if not name:
            raise ValidationError({'name': "The guardian's name is required · "
                                           'অভিভাবকের নাম দিতে হবে।'})

        with transaction.atomic():
            _, link = link_guardian(
                student=student,
                name=name,
                phone=request.data.get('phone'),
                relation=request.data.get('relation') or 'father',
                is_primary=str(request.data.get('is_primary', 'true')).lower() != 'false',
            )
        return Response(StudentGuardianSerializer(link).data,
                        status=status.HTTP_201_CREATED)


class GuardianViewSet(ActivityLogMixin, TeacherScopedMixin, BranchScopedViewSet):
    """Parents and local guardians — contact records shared between siblings.

    Under the `students` resource, not one of its own: the catalogue (docs/02
    §2.1) has no `guardians` entry, and whoever may edit a student is exactly
    who may correct their father's phone number.
    """

    # Through the student, for the same reason the student list is scoped: a
    # guardian record is a parent's phone number and NID.
    teacher_scope_field = 'student_links__student__enrolments__academic_class'

    queryset = Guardian.objects.select_related('branch').all()
    serializer_class = GuardianSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'students'
    activity_model = 'Guardian'
    filterset_fields = ['relation', 'is_active']
    search_fields = ['name', 'name_bn', 'phone', 'alt_phone', 'nid', 'occupation']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        return super().get_queryset().prefetch_related('student_links__student')


class AdmissionViewSet(ActivityLogMixin, BranchScopedViewSet):
    """Applications, and the one click that turns one into a student.

    No `destroy`: an application that came to nothing is `status=cancelled`, and
    the row is the paper trail behind an admission that did happen. The
    catalogue gives `admissions` only view/create/update, which says the same
    thing.
    """

    queryset = Admission.objects.select_related(
        'session', 'stream', 'branch', 'student').all()
    serializer_class = AdmissionSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'admissions'
    # `admit` is a custom POST, so the fallback would call it `update`. It is
    # declared anyway: admitting is what this whole module exists for, and the
    # cost of the endpoint should be readable in the class.
    permission_action_map = {'admit': 'update'}
    activity_model = 'Admission'
    filterset_fields = ['session', 'stream', 'academic_class', 'status', 'gender']
    search_fields = ['application_no', 'applicant_name', 'applicant_name_bn',
                     'guardian_name', 'guardian_phone']
    ordering_fields = ['application_no', 'created_at', 'interview_date',
                       'interview_score']
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def save_new(self, serializer):
        """Capture the application through the service that numbers it.

        `application_no` is gapless per (branch, session) — allocating it in the
        serializer would put a number-issuing `SELECT … FOR UPDATE` inside
        validation, where a later failure silently burns it.
        """
        branch = writable_branch(self.request)
        fields = dict(serializer.validated_data)
        session = fields.pop('session')

        serializer.instance = create_application(
            branch=branch,
            session=session,
            actor=self.request.user,
            request=self.request,
            **fields,
        )

    @action(detail=True, methods=['post'])
    def admit(self, request, pk=None):
        """`POST /api/admissions/<id>/admit/` — docs/02 §4.1.

        One click, several consequences, all or nothing: the Student, the
        Enrolment with its roll and admission number, the Guardian, and the
        application closed against the student. `services.admit_student` owns
        that transaction; this view only resolves the ids and reports.
        """
        application = self.get_object()
        body = AdmitSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        # A photograph and a stack of certificates may ride along (multipart).
        # Storing a document costs `documents.upload`, which admitting does not
        # include — but a clerk who may admit and may not file papers must still
        # be able to admit. So the documents are dropped and counted, never a
        # 403: refusing the admission would punish the child for the clerk's
        # role. The photo is part of the student record itself and rides with
        # the admission permission.
        documents = data.get('documents') or []
        skipped = 0
        if documents and not has_permission(request.user, 'documents', 'upload'):
            skipped, documents = len(documents), []

        student, enrolment = admit_student(
            application,
            academic_class=self._resolve_class(data.get('academic_class'), application),
            section=self._resolve_section(data.get('section')),
            roll=data.get('roll'),
            admitted_on=data.get('admitted_on'),
            is_hostel=data.get('is_hostel', False),
            is_transport=data.get('is_transport', False),
            photo=data.get('photo'),
            documents=documents,
            actor=request.user,
            request=request,
        )

        return Response(
            {
                'student': StudentSerializer(student, context=self.get_serializer_context()).data,
                'enrolment': getattr(enrolment, 'pk', None),
                'admission_number': getattr(enrolment, 'admission_number', None),
                'roll': getattr(enrolment, 'roll', None),
                'documents_attached': len(documents),
                # Nonzero means the files were sent and not kept. Said out loud
                # so the screen can tell the clerk rather than leaving them to
                # discover it next month.
                'documents_skipped': skipped,
            },
            status=status.HTTP_201_CREATED,
        )

    def _resolve_class(self, class_id, application):
        """The class to enrol into, defaulting to the one applied for.

        Resolved through the branch-scoped queryset, so naming another
        institution's class is a 400 that says so rather than a cross-branch
        write. The applicant is often moved a class up or down after the
        interview, which is why this is an argument at all.
        """
        if class_id is None:
            return application.academic_class

        from academics.models import AcademicClass

        academic_class = AcademicClass.objects.filter(
            pk=class_id, branch=application.branch,
        ).first()
        if academic_class is None:
            raise ValidationError({'academic_class': 'No class with that id in this '
                                                     'institution · এই প্রতিষ্ঠানে ওই শ্রেণি নেই।'})
        return academic_class

    def _resolve_section(self, section_id):
        if section_id is None:
            return None

        from academics.models import Section

        branch = writable_branch(self.request)
        section = Section.objects.filter(pk=section_id, branch=branch).first()
        if section is None:
            raise ValidationError({'section': 'No section with that id in this '
                                              'institution · এই প্রতিষ্ঠানে ওই শাখা নেই।'})
        return section


class DocumentViewSet(ActivityLogMixin, TeacherScopedMixin, BranchScopedViewSet):
    """Certificates, testimonials and scans — for students, teachers and employees.

    The files are **never** reachable by URL (docs/01 §8): `file` is write-only
    on the serializer and `download` below is the only way to read one back. A
    `/media/documents/...` path would be a permanent, unauthenticated grant to
    whoever happens to have seen it, and these are minors' birth certificates.
    """

    # A document owned by a teacher or an employee carries no student and so
    # no class; `teacher_scope_field` would exclude it. That is the safe side of
    # the line — a scoped teacher reads student documents for their own classes
    # and nobody's personnel file.
    teacher_scope_field = 'student__enrolments__academic_class'

    queryset = Document.objects.select_related('branch', 'student').all()
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'documents'
    # The catalogue's actions are view/upload/delete — there is no `create` or
    # `update` to fall back to, so every write maps onto `upload` explicitly.
    permission_action_map = {
        'create': 'upload',
        'update': 'upload',
        'partial_update': 'upload',
        'download': 'view',
    }
    activity_model = 'Document'
    filterset_fields = ['owner_type', 'doc_type', 'student', 'teacher', 'employee']
    search_fields = ['title']
    ordering_fields = ['created_at', 'issued_on', 'expires_on']

    def save_new(self, serializer):
        branch = writable_branch(self.request)
        serializer.save(branch=branch, created_by=self.request.user,
                        uploaded_by=self.request.user)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """`GET /api/documents/<id>/download/` — the only way a file leaves.

        `get_object()` runs the branch-scoped queryset first, so another
        institution's document is a 404 before a byte is read; the permission
        class has already required `documents.view`.
        """
        document = self.get_object()
        return _stream(document)


def _stream(document):
    """Send the stored file, or 404 if it is missing from storage.

    `as_attachment` so a browser saves it rather than rendering it inline — an
    inline HTML or SVG upload would otherwise execute on this origin, which is
    the origin holding the caller's session.
    """
    if not document.file:
        raise Http404

    try:
        handle = document.file.open('rb')
    except (FileNotFoundError, OSError) as exc:
        # The row survived its file: a restored database against a media
        # directory that was not restored with it. A 404 is the honest answer.
        raise Http404('The stored file is missing.') from exc

    filename = document.file.name.rsplit('/', 1)[-1]
    return FileResponse(handle, as_attachment=True, filename=filename)


# ─────────────────────────────────────────────────────────────────────────────
# /api/me/ — the student's own record, and nothing else
# ─────────────────────────────────────────────────────────────────────────────

def own_student(request):
    """The Student row belonging to the caller, or 404.

    This function is the entire security model of the family below, which is why
    it is one function and not a filter repeated per view. It matches on
    `user=request.user` — an identity DRF resolved from the token — so there is
    no id in any of these URLs for a caller to change, and no queryset that
    could be widened by a permission somebody was granted for another reason.

    404 and not 403 for a staff account with no student record: whether a given
    account has a student profile is not something these endpoints should
    confirm either way.
    """
    student = Student.objects.filter(user=request.user, is_active=True).first()
    if student is None:
        raise Http404('No student record for this account.')
    return student


class MyProfileView(APIView):
    """`GET /api/me/profile/` — the caller's own student record.

    `IsAuthenticated` alone, with no `HasResourcePermission`. That is the point
    of docs/02 §2.5: self-service is a separate endpoint family whose queryset is
    the caller, not a weakened `students.view` that would also make every other
    student's row reachable.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = own_student(request)
        return Response(MyProfileSerializer(student, context={'request': request}).data)


class MyDocumentViewSet(mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    """`/api/me/documents/` — the caller's own certificates.

    Read-only, and the queryset is built from `own_student(request)` on every
    call. A student passing another student's document id gets 404 from
    `get_object()`, because that row was never in the queryset — the same
    mechanism that makes wrong-branch rows 404 for staff.
    """

    serializer_class = MyDocumentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Document.objects.filter(student=own_student(self.request))

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        return _stream(self.get_object())


class MyGuardianView(APIView):
    """`GET /api/me/guardians/` — who the institution contacts about the caller."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        links = StudentGuardian.objects.filter(
            student=own_student(request),
        ).select_related('guardian')
        # The summary shape, not `GuardianSerializer`: a student may see who the
        # institution phones about them, not their father's NID and income.
        return Response(guardian_summary(links))
