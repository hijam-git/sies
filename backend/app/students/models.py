"""Student, Guardian, Admission and Document — docs/03 §4.

The shape to hold on to: **a Student is a person, not a class list.** Class,
section and session live on `academics.Enrolment`, and the brief's "admission
history" is simply `student.enrolments.all()` (docs/02 §4.1). Nothing here
duplicates a row another module owns.

Guardians are their own table for one concrete reason: siblings share a
guardian, and a changed phone number must change once. That phone is the SMS
destination, so a second copy of it is a message sent to the old number.

Every FK to `academics` and `staff` is a string reference. Those apps are built
alongside this one, and a string keeps the dependency in the migration graph
where it belongs instead of in the import graph (docs/WORKLOG F17).
"""

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel




class Gender(models.TextChoices):
    MALE = 'male', _('Male · ছেলে')
    FEMALE = 'female', _('Female · মেয়ে')
    OTHER = 'other', _('Other · অন্যান্য')


class StudentStatus(models.TextChoices):
    """Where the person stands with the institution — docs/03 §4.

    Distinct from `is_active`, which is the soft-delete flag. A passed-out
    student is `status=passed_out, is_active=True`: their record is live, their
    receipts still print, and they simply are not enrolled. `is_active=False`
    means the row was entered by mistake.
    """

    ACTIVE = 'active', _('Active · অধ্যয়নরত')
    PASSED_OUT = 'passed_out', _('Passed out · উত্তীর্ণ')
    WITHDRAWN = 'withdrawn', _('Withdrawn · ছাড়পত্রপ্রাপ্ত')
    TRANSFERRED = 'transferred', _('Transferred · স্থানান্তরিত')


class GuardianRelation(models.TextChoices):
    FATHER = 'father', _('Father · পিতা')
    MOTHER = 'mother', _('Mother · মাতা')
    BROTHER = 'brother', _('Brother · ভাই')
    OTHER = 'other', _('Other · অন্যান্য')


class AdmissionStatus(models.TextChoices):
    PENDING = 'pending', _('Pending · অপেক্ষমাণ')
    INTERVIEW = 'interview', _('Interview · সাক্ষাৎকার')
    ACCEPTED = 'accepted', _('Accepted · নির্বাচিত')
    REJECTED = 'rejected', _('Rejected · অনির্বাচিত')
    ADMITTED = 'admitted', _('Admitted · ভর্তি সম্পন্ন')
    CANCELLED = 'cancelled', _('Cancelled · বাতিল')


class DocumentOwner(models.TextChoices):
    STUDENT = 'student', _('Student · শিক্ষার্থী')
    TEACHER = 'teacher', _('Teacher · শিক্ষক')
    EMPLOYEE = 'employee', _('Employee · কর্মচারী')


class DocumentType(models.TextChoices):
    BIRTH_CERTIFICATE = 'birth_certificate', _('Birth certificate · জন্ম নিবন্ধন')
    NID = 'nid', _('NID · জাতীয় পরিচয়পত্র')
    PHOTO = 'photo', _('Photograph · ছবি')
    TESTIMONIAL = 'testimonial', _('Testimonial · প্রশংসাপত্র')
    TRANSFER_CERTIFICATE = 'transfer_certificate', _('Transfer certificate · ছাড়পত্র')
    MARKSHEET = 'marksheet', _('Marksheet · নম্বরপত্র')
    CERTIFICATE = 'certificate', _('Certificate · সনদ')
    OTHER = 'other', _('Other · অন্যান্য')


class Student(BranchScopedModel):
    """A person the institution teaches. Identity only.

    `student_id` is permanent and never reused — it is what a fee receipt from
    2026 and a testimonial from 2031 have in common. It is allocated from a
    single platform-wide counter (`services.allocate_student_id`) rather than a
    per-branch one, because docs/03 declares the column globally unique and a
    per-branch counter would hand `SIES-000123` to two institutions on their
    first admission.
    """

    student_id = models.CharField(
        _('student ID · শিক্ষার্থী আইডি'), max_length=20, unique=True,
    )

    # docs/08 D4. Nullable and OneToOne: most young students have no phone, so
    # the login is an action on the record ("enable login") and never a
    # requirement of admission. SET_NULL rather than CASCADE — deleting the
    # account must not delete the child.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_('login account · লগইন অ্যাকাউন্ট'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='student_profile',
    )

    # docs/08 D2: the brief's *Student Type* AND its *Category* are this one
    # field. There is no StudentCategory table and there never will be. PROTECT —
    # a stream with students in it cannot be deleted out from under them.
    stream = models.ForeignKey(
        'branches.Stream',
        verbose_name=_('stream · বিভাগ'),
        on_delete=models.PROTECT,
        related_name='students',
    )

    name = models.CharField(_('name'), max_length=120)
    name_bn = models.CharField(_('নাম'), max_length=120, blank=True)
    photo = models.ImageField(
        _('photo · ছবি'), upload_to='students/photos/', blank=True, null=True,
    )

    date_of_birth = models.DateField(_('date of birth · জন্ম তারিখ'), null=True, blank=True)
    gender = models.CharField(
        _('gender · লিঙ্গ'), max_length=10, choices=Gender.choices, default=Gender.MALE,
    )
    birth_certificate_no = models.CharField(
        _('birth certificate no · জন্ম নিবন্ধন নম্বর'), max_length=30, blank=True,
    )
    nid = models.CharField(_('NID · জাতীয় পরিচয়পত্র'), max_length=30, blank=True)
    blood_group = models.CharField(_('blood group · রক্তের গ্রুপ'), max_length=5, blank=True)
    # Free text on purpose: for a hifz student this holds the current Sipara,
    # which changes monthly and is not a dimension anything queries or reports on.
    religion_notes = models.CharField(
        _('religious notes · দ্বীনি তথ্য'), max_length=120, blank=True,
    )

    # Optional, and deliberately not the SMS destination. The number that matters
    # is `Guardian.phone` — a nine-year-old's "phone" is their uncle's.
    phone = models.CharField(_('phone · ফোন'), max_length=11, blank=True)
    email = models.EmailField(_('email · ইমেইল'), blank=True)

    # ── Address, structured (docs/07 §4) ────────────────────────────────────
    # Four fields and not one, because the printed admission form asks for
    # গ্রাম/মহল্লা · ডাকঘর · উপজেলা · জেলা as four separate boxes and a single
    # Text field cannot fill them. It also makes "students from this upazila" a
    # query instead of a substring search over free text.
    village = models.CharField(_('village · গ্রাম/মহল্লা'), max_length=80, blank=True)
    post_office = models.CharField(_('post office · ডাকঘর'), max_length=80, blank=True)
    upazila = models.CharField(_('upazila · উপজেলা'), max_length=80, blank=True)
    district = models.CharField(_('district · জেলা'), max_length=80, blank=True)

    # Kept alongside the four, not replaced by them: a holding number, a road name
    # or a landmark has nowhere else to go.
    present_address = models.TextField(_('present address · বর্তমান ঠিকানা'), blank=True)
    permanent_address = models.TextField(_('permanent address · স্থায়ী ঠিকানা'), blank=True)

    previous_institution = models.CharField(
        _('previous institution · পূর্ববর্তী প্রতিষ্ঠান'), max_length=150, blank=True,
    )
    previous_class = models.CharField(
        _('previous class · পূর্ববর্তী শ্রেণি'), max_length=60, blank=True,
    )

    # First admission only. Re-admission into the next session writes a new
    # Enrolment and leaves this alone (docs/02 §4.1).
    admitted_on = models.DateField(_('admitted on · ভর্তির তারিখ'), null=True, blank=True)

    status = models.CharField(
        _('status · অবস্থা'), max_length=20,
        choices=StudentStatus.choices, default=StudentStatus.ACTIVE,
    )
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('student · শিক্ষার্থী')
        verbose_name_plural = _('students · শিক্ষার্থীরা')
        ordering = ['branch', 'name', 'student_id']
        indexes = [
            models.Index(fields=['branch', 'status', 'is_active'],
                         name='student_branch_status_idx'),
            models.Index(fields=['branch', 'name'], name='student_branch_name_idx'),
            # The scholarship list is built by upazila, by hand, every year.
            models.Index(fields=['branch', 'upazila'], name='student_branch_upazila_idx'),
        ]

    def __str__(self):
        return f'{self.name} ({self.student_id})'

    def save(self, *args, **kwargs):
        # Canonicalised for the same reason `accounts.User.phone` is: an SMS
        # gateway and a login both need one spelling of a number, and a
        # +880-prefixed form typed on the admission form is the same phone.
        from accounts.phone import normalize_bd_phone
        if self.phone:
            self.phone = normalize_bd_phone(self.phone) or self.phone
        return super().save(*args, **kwargs)

    @property
    def full_address(self):
        """The four structured boxes as one line, for a list or an SMS."""
        parts = [self.village, self.post_office, self.upazila, self.district]
        return ', '.join(part for part in parts if part)

    @property
    def primary_guardian(self):
        """The guardian an SMS goes to, or None.

        A property and not a stored column: `StudentGuardian.is_primary` already
        says it, and a second copy drifts the first time someone changes which
        guardian is primary.
        """
        link = self.guardian_links.filter(is_primary=True).select_related('guardian').first()
        return link.guardian if link else None


class Guardian(BranchScopedModel):
    """A parent or local guardian — a contact record, shared between siblings.

    `phone` is the SMS destination and is therefore required, canonical, and
    unique within the institution. That uniqueness is the point of the whole
    table: without it, admitting a second child creates a second guardian row
    holding the same number, and the fee-reminder job sends two messages that are
    then corrected in only one place.

    `user` is nullable and reserved — guardian login is V2 (docs/08 D4). The
    column exists now so switching it on is a settings change rather than a
    migration on a populated table.
    """

    name = models.CharField(_('name'), max_length=120)
    name_bn = models.CharField(_('নাম'), max_length=120, blank=True)
    relation = models.CharField(
        _('relation · সম্পর্ক'), max_length=20,
        choices=GuardianRelation.choices, default=GuardianRelation.FATHER,
    )

    # Char(11) exactly: a canonical BD mobile is 01XXXXXXXXX and nothing else
    # reaches the SMS gateway. Anything longer arriving here is a country code
    # that `normalize_bd_phone` should already have stripped.
    phone = models.CharField(_('phone · মোবাইল'), max_length=11)
    alt_phone = models.CharField(_('alternate phone · বিকল্প মোবাইল'), max_length=11, blank=True)
    nid = models.CharField(_('NID · জাতীয় পরিচয়পত্র'), max_length=30, blank=True)
    occupation = models.CharField(_('occupation · পেশা'), max_length=80, blank=True)

    # Decimal, never float (CLAUDE.md §1). It is not money that moves, but it is
    # money, and a fee-waiver decision gets read off it.
    monthly_income = models.DecimalField(
        _('monthly income · মাসিক আয়'), max_digits=12, decimal_places=2,
        null=True, blank=True,
    )
    address = models.TextField(_('address · ঠিকানা'), blank=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('login account · লগইন অ্যাকাউন্ট'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='guardian_profiles',
    )

    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('guardian · অভিভাবক')
        verbose_name_plural = _('guardians · অভিভাবকগণ')
        ordering = ['branch', 'name']
        constraints = [
            # What makes sibling reuse work: `services.link_guardian` matches on
            # (branch, phone), and this guarantees the match is unambiguous.
            models.UniqueConstraint(
                fields=['branch', 'phone'], name='guardian_unique_phone_per_branch',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'name'], name='guardian_branch_name_idx'),
        ]

    def __str__(self):
        return f'{self.name} ({self.phone})'

    def save(self, *args, **kwargs):
        from accounts.phone import normalize_bd_phone
        # The fallback keeps whatever was typed rather than emptying the column:
        # a required field silently blanked is worse than a number the SMS job
        # will report as undeliverable, which is at least visible.
        self.phone = normalize_bd_phone(self.phone) or (self.phone or '').strip()
        if self.alt_phone:
            self.alt_phone = normalize_bd_phone(self.alt_phone) or self.alt_phone.strip()
        return super().save(*args, **kwargs)


class StudentGuardian(BranchScopedModel):
    """student × guardian × is_primary — many-to-many with an attribute.

    A through model rather than a plain M2M, because the attribute is the useful
    part: a student can have a father and a local guardian, and the fee reminder
    has to know which number to send to. A bare M2M leaves that to whichever row
    the database returns first.
    """

    # CASCADE on both sides: a link row is meaningless without either end
    # (CLAUDE.md §4.2). Note the asymmetry with everything else here — this is
    # the join, not the record. Deleting a Student is separately blocked by every
    # PROTECT pointing at it from fees, marks and Admission.
    student = models.ForeignKey(
        Student, verbose_name=_('student · শিক্ষার্থী'),
        on_delete=models.CASCADE, related_name='guardian_links',
    )
    guardian = models.ForeignKey(
        Guardian, verbose_name=_('guardian · অভিভাবক'),
        on_delete=models.CASCADE, related_name='student_links',
    )
    is_primary = models.BooleanField(_('primary contact · প্রধান যোগাযোগ'), default=False)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('student guardian · শিক্ষার্থীর অভিভাবক')
        verbose_name_plural = _('student guardians · শিক্ষার্থীর অভিভাবকগণ')
        ordering = ['student', '-is_primary', 'guardian']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'guardian'], name='studentguardian_unique_pair',
            ),
            # At most one primary per student. Partial rather than a plain
            # unique: `is_primary=False` may repeat freely and only the True rows
            # are constrained. Two primaries means two SMS per reminder, which an
            # institution discovers from its gateway bill.
            models.UniqueConstraint(
                fields=['student'],
                condition=models.Q(is_primary=True),
                name='studentguardian_one_primary_per_student',
            ),
        ]

    def __str__(self):
        return f'{self.student.name} — {self.guardian.name}'


class Admission(BranchScopedModel):
    """An application, which exists before any Student row (docs/02 §4.1).

    Kept separate from `Student` on purpose: most applications are never
    admitted, and writing a Student for each one fills the roll with people who
    did not come. `services.admit_student()` is the only supported way to turn
    one into a student.
    """

    session = models.ForeignKey(
        'branches.Session', verbose_name=_('session · শিক্ষাবর্ষ'),
        on_delete=models.PROTECT, related_name='admissions',
    )
    stream = models.ForeignKey(
        'branches.Stream', verbose_name=_('stream · বিভাগ'),
        on_delete=models.PROTECT, related_name='admissions',
    )
    academic_class = models.ForeignKey(
        'academics.AcademicClass', verbose_name=_('class applied for · আবেদিত শ্রেণি'),
        on_delete=models.PROTECT, related_name='admissions',
    )

    # Gapless per (branch, session) — CLAUDE.md §4.4. Quoted back over a counter
    # when someone asks after their application, so it has to be typeable and its
    # sequence has to mean something: applicant 41 really is the forty-first.
    application_no = models.CharField(_('application no · আবেদন নম্বর'), max_length=40)

    applicant_name = models.CharField(_('applicant name · আবেদনকারীর নাম'), max_length=120)
    applicant_name_bn = models.CharField(_('আবেদনকারীর নাম (বাংলা)'), max_length=120, blank=True)
    dob = models.DateField(_('date of birth · জন্ম তারিখ'), null=True, blank=True)
    gender = models.CharField(
        _('gender · লিঙ্গ'), max_length=10, choices=Gender.choices, default=Gender.MALE,
    )
    photo = models.ImageField(
        _('photo · ছবি'), upload_to='admissions/photos/', blank=True, null=True,
    )

    guardian_name = models.CharField(_('guardian name · অভিভাবকের নাম'), max_length=120)
    guardian_phone = models.CharField(_('guardian phone · অভিভাবকের মোবাইল'), max_length=11)

    # The same four boxes as Student, for the same reason (docs/07 §4): the
    # printed form is filled in before the student exists, and copying the answer
    # forward at admission is only possible if it was captured in that shape.
    village = models.CharField(_('village · গ্রাম/মহল্লা'), max_length=80, blank=True)
    post_office = models.CharField(_('post office · ডাকঘর'), max_length=80, blank=True)
    upazila = models.CharField(_('upazila · উপজেলা'), max_length=80, blank=True)
    district = models.CharField(_('district · জেলা'), max_length=80, blank=True)
    address = models.TextField(_('address · ঠিকানা'), blank=True)

    previous_institution = models.CharField(
        _('previous institution · পূর্ববর্তী প্রতিষ্ঠান'), max_length=150, blank=True,
    )
    previous_class = models.CharField(
        _('previous class · পূর্ববর্তী শ্রেণি'), max_length=60, blank=True,
    )
    previous_result = models.CharField(
        _('previous result · পূর্ববর্তী ফলাফল'), max_length=60, blank=True,
    )

    status = models.CharField(
        _('status · অবস্থা'), max_length=20,
        choices=AdmissionStatus.choices, default=AdmissionStatus.PENDING,
    )
    interview_date = models.DateField(_('interview date · সাক্ষাৎকারের তারিখ'),
                                      null=True, blank=True)
    interview_score = models.DecimalField(
        _('interview score · সাক্ষাৎকারের নম্বর'), max_digits=6, decimal_places=2,
        null=True, blank=True,
    )
    remarks = models.TextField(_('remarks · মন্তব্য'), blank=True)

    # PROTECT: this application is the paper trail behind a student's admission,
    # so deleting the student while it still points at them must fail loudly.
    student = models.ForeignKey(
        Student, verbose_name=_('student · শিক্ষার্থী'),
        null=True, blank=True,
        on_delete=models.PROTECT, related_name='applications',
    )

    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('processed by · প্রক্রিয়াকারী'),
        null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )
    processed_at = models.DateTimeField(_('processed at · প্রক্রিয়ার সময়'),
                                        null=True, blank=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('admission application · ভর্তির আবেদন')
        verbose_name_plural = _('admission applications · ভর্তির আবেদনসমূহ')
        # Newest first — the screen is a work queue, not an archive.
        ordering = ['branch', '-created_at', '-application_no']
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'session', 'application_no'],
                name='admission_unique_application_no',
            ),
            # An admitted application with no student is a click that half
            # happened. `admit_student` writes both in one transaction; this says
            # so even for a row someone later edits in the Django admin.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=AdmissionStatus.ADMITTED)
                    | models.Q(student__isnull=False)
                ),
                name='admission_admitted_has_student',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'session', 'status'],
                         name='admission_branch_status_idx'),
        ]

    def __str__(self):
        return f'{self.application_no} — {self.applicant_name}'

    def save(self, *args, **kwargs):
        from accounts.phone import normalize_bd_phone
        self.guardian_phone = (
            normalize_bd_phone(self.guardian_phone) or (self.guardian_phone or '').strip()
        )
        return super().save(*args, **kwargs)


class Document(BranchScopedModel):
    """A file belonging to a student, a teacher or an employee.

    **Never served from a public URL** (docs/01 §8). These are minors' birth
    certificates and NID scans; a guessable `/media/...` path is a directory of
    them for anyone who finds one. `views.DocumentViewSet.download` streams the
    file after checking branch and permission, and the serializer exposes that
    endpoint instead of `file.url`.

    One table for all three owner types rather than three, because the screen,
    the permission and the retention rule are identical and only the FK differs.
    `owner_type` plus the CheckConstraint below is what keeps that honest.
    """

    owner_type = models.CharField(
        _('owner type · মালিকের ধরন'), max_length=20, choices=DocumentOwner.choices,
        default=DocumentOwner.STUDENT,
    )

    # CASCADE on the owner FKs: a document is meaningless without the person it
    # belongs to, and keeping an orphaned scan of a child's birth certificate is
    # the wrong answer to every question anyone could ask about it.
    student = models.ForeignKey(
        Student, verbose_name=_('student · শিক্ষার্থী'),
        null=True, blank=True, on_delete=models.CASCADE, related_name='documents',
    )
    teacher = models.ForeignKey(
        'staff.Teacher', verbose_name=_('teacher · শিক্ষক'),
        null=True, blank=True, on_delete=models.CASCADE, related_name='documents',
    )
    employee = models.ForeignKey(
        'staff.Employee', verbose_name=_('employee · কর্মচারী'),
        null=True, blank=True, on_delete=models.CASCADE, related_name='documents',
    )

    doc_type = models.CharField(
        _('document type · কাগজের ধরন'), max_length=30,
        choices=DocumentType.choices, default=DocumentType.OTHER,
    )
    title = models.CharField(_('title · শিরোনাম'), max_length=150)
    file = models.FileField(_('file · ফাইল'), upload_to='documents/%Y/%m/')
    issued_on = models.DateField(_('issued on · প্রদানের তারিখ'), null=True, blank=True)
    # Drives the "expiring soon" list — a testimonial does not expire, a
    # registration card does.
    expires_on = models.DateField(_('expires on · মেয়াদ শেষ'), null=True, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('uploaded by · আপলোডকারী'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('document · কাগজপত্র')
        verbose_name_plural = _('documents · কাগজপত্র')
        ordering = ['branch', '-created_at']
        constraints = [
            # Exactly one owner, and it is the one `owner_type` names. Without
            # this a row can claim to be a student document while pointing at a
            # teacher, and the download view's ownership check would be reading
            # the wrong column — which is how a private file reaches the wrong
            # person while every test still passes.
            models.CheckConstraint(
                condition=(
                    models.Q(owner_type=DocumentOwner.STUDENT,
                             student__isnull=False,
                             teacher__isnull=True, employee__isnull=True)
                    | models.Q(owner_type=DocumentOwner.TEACHER,
                               teacher__isnull=False,
                               student__isnull=True, employee__isnull=True)
                    | models.Q(owner_type=DocumentOwner.EMPLOYEE,
                               employee__isnull=False,
                               student__isnull=True, teacher__isnull=True)
                ),
                name='document_exactly_one_owner',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'owner_type', 'doc_type'],
                         name='document_branch_owner_idx'),
            models.Index(fields=['branch', 'expires_on'], name='document_expiry_idx'),
        ]

    def __str__(self):
        return f'{self.get_doc_type_display()} — {self.title}'
