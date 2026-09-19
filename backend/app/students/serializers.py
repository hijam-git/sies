"""Shape and validation for the students API (CLAUDE.md §4.3).

`branch` is never writable. `BranchScopedViewSet` stamps it from
`request.branch`, and leaving it off every serializer here is the second of the
two independent reasons a `branch` in a POST body does nothing (docs/02 §3).

The other rule this module carries: **a scoped queryset controls what you can
read, and nothing else stops you WRITING a relation that points at another
institution.** Every FK exposed below is therefore checked against the caller's
own branch in a `validate_*`, or the API would let a Dhaka clerk enrol a student
against Chittagong's session.
"""

from rest_framework import serializers

from accounts.phone import normalize_bd_phone
from core.serializers import check_same_branch, request_branch_id  # noqa: F401

from .models import (Admission, Document, DocumentOwner, Guardian, Student,
                     StudentGuardian)


# `request_branch_id` and `check_same_branch` now live in `core.serializers`,
# imported above and re-exported for the `validate_*` methods below. They were
# written here first and copied into `academics` and `staff` by hand; the copies
# drifted — two of them could not read a platform admin's `?branch=5`, which is
# a string — so there is one of each now, and `BranchSafeSerializer` for whole
# serializers that would otherwise have to remember every field.


class GuardianSerializer(serializers.ModelSerializer):
    """A contact record. The phone is the SMS destination, so it is validated hard."""

    students = serializers.SerializerMethodField()

    class Meta:
        model = Guardian
        fields = ['id', 'name', 'name_bn', 'relation', 'phone', 'alt_phone',
                  'nid', 'occupation', 'monthly_income', 'address', 'user',
                  'is_active', 'students', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'students', 'created_at', 'updated_at']

    def get_students(self, obj):
        """The children on this guardian's row — the sibling view, in one call.

        A method field rather than a nested serializer: the guardian list screen
        shows names, and a full StudentSerializer per child would make a
        thirty-row page issue a hundred queries for data nobody reads there.
        """
        return [
            {'id': link.student_id,
             'name': link.student.name,
             'student_id': link.student.student_id,
             'is_primary': link.is_primary}
            for link in obj.student_links.select_related('student')
        ]

    def validate_phone(self, value):
        """Canonical, and unique within the institution.

        `Meta.constraints` is the real guarantee; this turns the common case into
        a 400 on `phone` — which the form can point at — instead of an integrity
        error it can only show as a banner. Answering with the existing
        guardian's name is deliberate: the clerk almost always wants to attach
        the sibling to that row rather than make a second one.
        """
        canonical = normalize_bd_phone(value)
        if not canonical:
            raise serializers.ValidationError(
                'Enter an 11-digit mobile number, e.g. 01712345678 · '
                'সঠিক ১১ সংখ্যার মোবাইল নম্বর দিন।'
            )

        branch_id = request_branch_id(self)
        if branch_id is None:
            return canonical

        clash = Guardian.objects.filter(branch_id=branch_id, phone=canonical)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        existing = clash.first()
        if existing is not None:
            raise serializers.ValidationError(
                f'{existing.name} already uses this number — attach the student to '
                f'that guardian instead · এই নম্বরটি {existing.name}-এর নামে আছে।'
            )
        return canonical


class StudentGuardianSerializer(serializers.ModelSerializer):
    """The link row, with enough of the guardian inlined to render a card."""

    guardian_name = serializers.CharField(source='guardian.name', read_only=True)
    guardian_phone = serializers.CharField(source='guardian.phone', read_only=True)
    relation = serializers.CharField(source='guardian.relation', read_only=True)

    class Meta:
        model = StudentGuardian
        fields = ['id', 'student', 'guardian', 'guardian_name', 'guardian_phone',
                  'relation', 'is_primary', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_student(self, value):
        return check_same_branch(self, value, 'That student belongs to another '
                                              'institution · ওই শিক্ষার্থী অন্য প্রতিষ্ঠানের।')

    def validate_guardian(self, value):
        return check_same_branch(self, value, 'That guardian belongs to another '
                                              'institution · ওই অভিভাবক অন্য প্রতিষ্ঠানের।')


class StudentSerializer(serializers.ModelSerializer):
    """The student record. Identity only — class and section come from Enrolment.

    `user` is read-only: a login is created by `services.enable_student_login`,
    which checks that the number is free and forces a password change. Letting a
    PATCH set the FK directly would let one student's record be pointed at
    another student's account.
    """

    stream_name = serializers.CharField(source='stream.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    full_address = serializers.CharField(read_only=True)
    guardians = StudentGuardianSerializer(source='guardian_links', many=True, read_only=True)
    has_login = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id', 'student_id', 'user', 'has_login',
            'stream', 'stream_name',
            'name', 'name_bn', 'photo',
            'date_of_birth', 'gender',
            'birth_certificate_no', 'nid', 'blood_group', 'religion_notes',
            'phone', 'email',
            'village', 'post_office', 'upazila', 'district', 'full_address',
            'present_address', 'permanent_address',
            'previous_institution', 'previous_class',
            'admitted_on', 'status', 'status_display', 'is_active',
            'guardians',
            'created_at', 'updated_at',
        ]
        # `student_id` is permanent and never reused (docs/02 §4.2). It is
        # allocated by `services.allocate_student_id` and editing it would break
        # every receipt already printed with it.
        read_only_fields = ['id', 'student_id', 'user', 'created_at', 'updated_at']

    def get_has_login(self, obj):
        """Whether this student can sign in — docs/08 D4, and most cannot."""
        return obj.user_id is not None

    def validate_stream(self, value):
        return check_same_branch(self, value, 'That stream belongs to another '
                                              'institution · ওই বিভাগ অন্য প্রতিষ্ঠানের।')

    def validate_phone(self, value):
        if not value:
            return ''
        canonical = normalize_bd_phone(value)
        if not canonical:
            raise serializers.ValidationError(
                'Enter an 11-digit mobile number, e.g. 01712345678 · '
                'সঠিক ১১ সংখ্যার মোবাইল নম্বর দিন।'
            )
        return canonical


class StudentCreateSerializer(StudentSerializer):
    """Direct entry — the paper roll being typed in, not an admission.

    Separate from the admission path on purpose: `admit_student()` is for an
    application becoming a student, and it also writes an Enrolment. This one
    creates the person alone, which is what `import_students` and a mid-year
    correction need. The view allocates `student_id` through the service so both
    paths draw from the same series.
    """

    class Meta(StudentSerializer.Meta):
        pass


class AdmissionSerializer(serializers.ModelSerializer):
    """An application. `application_no` is allocated, never supplied."""

    status_display = serializers.CharField(source='get_status_display', read_only=True)
    session_name = serializers.CharField(source='session.name', read_only=True)
    stream_name = serializers.CharField(source='stream.name', read_only=True)
    student_name = serializers.CharField(source='student.name', read_only=True, default=None)
    student_code = serializers.CharField(source='student.student_id',
                                         read_only=True, default=None)

    class Meta:
        model = Admission
        fields = [
            'id', 'application_no',
            'session', 'session_name', 'stream', 'stream_name', 'academic_class',
            'applicant_name', 'applicant_name_bn', 'dob', 'gender', 'photo',
            'guardian_name', 'guardian_phone',
            'village', 'post_office', 'upazila', 'district', 'address',
            'previous_institution', 'previous_class', 'previous_result',
            'status', 'status_display',
            'interview_date', 'interview_score', 'remarks',
            'student', 'student_name', 'student_code',
            'processed_by', 'processed_at',
            'created_at', 'updated_at',
        ]
        # `student` is set by `admit_student()` and by nothing else — a PATCH
        # that pointed an application at an arbitrary student would produce an
        # admission with no enrolment and no fees behind it.
        read_only_fields = ['id', 'application_no', 'student', 'student_name',
                            'student_code', 'processed_by', 'processed_at',
                            'created_at', 'updated_at']

    def validate_session(self, value):
        return check_same_branch(self, value, 'That session belongs to another '
                                              'institution · ওই শিক্ষাবর্ষ অন্য প্রতিষ্ঠানের।')

    def validate_stream(self, value):
        return check_same_branch(self, value, 'That stream belongs to another '
                                              'institution · ওই বিভাগ অন্য প্রতিষ্ঠানের।')

    def validate_academic_class(self, value):
        return check_same_branch(self, value, 'That class belongs to another '
                                              'institution · ওই শ্রেণি অন্য প্রতিষ্ঠানের।')

    def validate_guardian_phone(self, value):
        canonical = normalize_bd_phone(value)
        if not canonical:
            raise serializers.ValidationError(
                "Enter the guardian's 11-digit mobile number · "
                'অভিভাবকের সঠিক মোবাইল নম্বর দিন।'
            )
        return canonical


class AdmitSerializer(serializers.Serializer):
    """The body of `POST /api/admissions/<id>/admit/`.

    A plain Serializer and not a ModelSerializer: this is a command, not a row.
    It names where the student is going — the class, the section, and optionally
    the roll — and `services.admit_student()` does the rest.
    """

    academic_class = serializers.IntegerField(required=False, allow_null=True)
    section = serializers.IntegerField(required=False, allow_null=True)
    # Left out means "let academics allocate the next roll", which is the normal
    # case. Supplied means the institution keeps its own roll order on paper.
    roll = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    admitted_on = serializers.DateField(required=False, allow_null=True)
    is_hostel = serializers.BooleanField(required=False, default=False)
    is_transport = serializers.BooleanField(required=False, default=False)


class DocumentSerializer(serializers.ModelSerializer):
    """A stored file.

    **`file` is write-only and `download_url` is the only way out.** Exposing
    `file.url` would hand out a `/media/...` path that Traefik serves to anyone
    who has it — and these are minors' birth certificates (docs/01 §8). The
    download endpoint checks branch and permission on every request; a static
    URL checks nothing, forever.
    """

    file = serializers.FileField(write_only=True)
    download_url = serializers.SerializerMethodField()
    doc_type_display = serializers.CharField(source='get_doc_type_display', read_only=True)
    filename = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ['id', 'owner_type', 'student', 'teacher', 'employee',
                  'doc_type', 'doc_type_display', 'title', 'file', 'filename',
                  'download_url', 'issued_on', 'expires_on', 'uploaded_by',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'uploaded_by', 'created_at', 'updated_at']

    def get_download_url(self, obj):
        request = self.context.get('request')
        path = f'/api/documents/{obj.pk}/download/'
        return request.build_absolute_uri(path) if request is not None else path

    def get_filename(self, obj):
        """The stored name, so the SPA can show an icon and an extension.

        Only the basename: the directory says the upload month and the branch's
        media layout, which is nothing a client needs and one more thing a
        crafted request could aim at.
        """
        return obj.file.name.rsplit('/', 1)[-1] if obj.file else ''

    def validate_student(self, value):
        return check_same_branch(self, value, 'That student belongs to another '
                                              'institution · ওই শিক্ষার্থী অন্য প্রতিষ্ঠানের।')

    def validate(self, attrs):
        """Exactly one owner, matching `owner_type`.

        The CheckConstraint enforces it in the database. Repeating it here is
        what turns an IntegrityError — which reaches the SPA as a generic
        failure — into a field error naming the box that was left empty.
        """
        def value_of(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, f'{field}_id', None)

        owner_type = attrs.get('owner_type',
                               getattr(self.instance, 'owner_type', DocumentOwner.STUDENT))
        owners = {
            DocumentOwner.STUDENT: value_of('student'),
            DocumentOwner.TEACHER: value_of('teacher'),
            DocumentOwner.EMPLOYEE: value_of('employee'),
        }

        if owners.get(owner_type) is None:
            raise serializers.ValidationError({
                owner_type: f'Name the {owner_type} this document belongs to · '
                            'কাগজটি কার, তা নির্বাচন করুন।',
            })

        extra = [key for key, value in owners.items()
                 if key != owner_type and value is not None]
        if extra:
            raise serializers.ValidationError({
                extra[0]: 'A document belongs to one person only · '
                          'একটি কাগজ একজনেরই হতে পারে।',
            })
        return attrs


# ─────────────────────────────────────────────────────────────────────────────
# /api/me/ — self-service (docs/02 §2.5, docs/08 D4)
#
# Read-only and narrower than the staff serializers on purpose. A student may
# see their own record; they have no business seeing the audit columns, the
# interview score that admitted them, or who processed their application.
# ─────────────────────────────────────────────────────────────────────────────

def guardian_summary(links):
    """Name, relation and phone only — never the guardian's NID or income.

    A student may see who the institution contacts about them. They may not see
    their father's national ID number or declared monthly income, which is what
    `GuardianSerializer` would hand over.
    """
    return [
        {'name': link.guardian.name,
         'name_bn': link.guardian.name_bn,
         'relation': link.guardian.relation,
         'phone': link.guardian.phone,
         'is_primary': link.is_primary}
        for link in links
    ]


class MyProfileSerializer(serializers.ModelSerializer):
    stream_name = serializers.CharField(source='stream.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    full_address = serializers.CharField(read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    guardians = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ['id', 'student_id', 'name', 'name_bn', 'photo',
                  'stream', 'stream_name', 'branch_name',
                  'date_of_birth', 'gender', 'blood_group',
                  'phone', 'email',
                  'village', 'post_office', 'upazila', 'district', 'full_address',
                  'present_address', 'permanent_address',
                  'admitted_on', 'status', 'status_display', 'guardians']
        read_only_fields = fields

    def get_guardians(self, obj):
        return guardian_summary(obj.guardian_links.select_related('guardian'))


class MyDocumentSerializer(serializers.ModelSerializer):
    doc_type_display = serializers.CharField(source='get_doc_type_display', read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ['id', 'doc_type', 'doc_type_display', 'title',
                  'download_url', 'issued_on', 'expires_on', 'created_at']
        read_only_fields = fields

    def get_download_url(self, obj):
        request = self.context.get('request')
        path = f'/api/me/documents/{obj.pk}/download/'
        return request.build_absolute_uri(path) if request is not None else path
