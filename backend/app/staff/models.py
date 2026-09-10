"""Teachers, employees, and the fields they share (docs/03 §5, docs/08 D5).

**Two models, two tables.** A teacher is going to grow features an employee
never has — evaluation, grading, subject expertise, class load — and merging
them would make every one of those a column that is null for half the rows
(D5). The twenty-odd identity, contact, salary and employment fields they
genuinely share are defined once in `PersonProfile`, which is **abstract**: each
table stands alone with no implicit join, and the two cannot drift.

`NumberSequence`numbers, can import it without `staff` ever importing `academics` back. `core`
would be the other candidate and is worse: core deliberately owns no domain
tables and depends on no app (docs/06 §2).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel


class Gender(models.TextChoices):
    MALE = 'male', _('Male · পুরুষ')
    FEMALE = 'female', _('Female · মহিলা')
    OTHER = 'other', _('Other · অন্যান্য')


class BloodGroup(models.TextChoices):
    """A choice rather than free text because it prints on an ID card and is
    read out in an emergency; 'B +ve' and 'B+' must not be two values."""

    A_POS = 'A+', 'A+'
    A_NEG = 'A-', 'A-'
    B_POS = 'B+', 'B+'
    B_NEG = 'B-', 'B-'
    AB_POS = 'AB+', 'AB+'
    AB_NEG = 'AB-', 'AB-'
    O_POS = 'O+', 'O+'
    O_NEG = 'O-', 'O-'


class EmploymentStatus(models.TextChoices):
    ACTIVE = 'active', _('Active · কর্মরত')
    ON_LEAVE = 'on_leave', _('On leave · ছুটিতে')
    SUSPENDED = 'suspended', _('Suspended · সাময়িক বরখাস্ত')
    RESIGNED = 'resigned', _('Resigned · পদত্যাগ')
    TERMINATED = 'terminated', _('Terminated · চাকরিচ্যুত')
    TRANSFERRED = 'transferred', _('Transferred · বদলি')




class PersonProfile(BranchScopedModel):
    """The fields a teacher and an employee both have. **Abstract — no table.**

    Abstract inheritance and not multi-table inheritance (docs/08 D5): each of
    the two concrete models gets a clean, independent table with no hidden join
    to a shared parent, while the field definitions stay written down once.
    Adding a shared field is one edit here and two generated migrations.
    """

    # OneToOne and nullable: most of an institution's staff never sign in. The
    # ones who do are matched to their account here, and `phone` is expected to
    # equal `user.phone` in that case — the profile keeps its own copy because it
    # must still be reachable by phone when there is no account at all.
    #
    # SET_NULL, not CASCADE: deleting a login must not delete the employment
    # record it was attached to, with its salary and attendance history.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_('login · অ্যাকাউন্ট'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='%(class)s_profile',
    )

    name = models.CharField(_('name'), max_length=120)
    name_bn = models.CharField(_('নাম'), max_length=120, blank=True)
    photo = models.ImageField(
        _('photo · ছবি'), upload_to='staff/photos/', null=True, blank=True,
    )

    dob = models.DateField(_('date of birth · জন্ম তারিখ'), null=True, blank=True)
    gender = models.CharField(
        _('gender · লিঙ্গ'), max_length=10, choices=Gender.choices, blank=True,
    )
    nid = models.CharField(_('NID · জাতীয় পরিচয়পত্র'), max_length=30, blank=True)
    blood_group = models.CharField(
        _('blood group · রক্তের গ্রুপ'), max_length=3,
        choices=BloodGroup.choices, blank=True,
    )

    # 11 characters: the canonical Bangladeshi mobile form `01XXXXXXXXX` that
    # `accounts.phone` normalises to, so a staff phone and a login phone compare
    # equal without either side re-normalising.
    phone = models.CharField(_('phone · মোবাইল'), max_length=11, blank=True)
    alt_phone = models.CharField(_('alternate phone · বিকল্প ফোন'), max_length=20, blank=True)
    email = models.EmailField(_('email · ইমেইল'), blank=True)

    # Structured rather than one address blob, exactly as on Student: the
    # appointment and admission forms ask for these as four separate boxes
    # (docs/07 §4), and it makes "staff from this upazila" a query.
    village = models.CharField(_('village · গ্রাম'), max_length=80, blank=True)
    post_office = models.CharField(_('post office · ডাকঘর'), max_length=80, blank=True)
    upazila = models.CharField(_('upazila · উপজেলা'), max_length=80, blank=True)
    district = models.CharField(_('district · জেলা'), max_length=80, blank=True)
    address = models.TextField(_('address · ঠিকানা'), blank=True)

    designation = models.CharField(_('designation · পদবি'), max_length=80, blank=True)
    joining_date = models.DateField(_('joining date · যোগদানের তারিখ'), null=True, blank=True)
    leaving_date = models.DateField(_('leaving date · প্রস্থানের তারিখ'), null=True, blank=True)
    employment_status = models.CharField(
        _('employment status · চাকরির অবস্থা'),
        max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.ACTIVE,
    )

    # Decimal, never Float (CLAUDE.md §1). A binary float cannot represent 0.10,
    # so a payroll built on one drifts by paisa per row and stops reconciling —
    # and the first person to notice is a teacher holding a payslip.
    basic_salary = models.DecimalField(
        _('basic salary · মূল বেতন'), max_digits=12, decimal_places=2, default=0,
    )
    allowances = models.DecimalField(
        _('allowances · ভাতা'), max_digits=12, decimal_places=2, default=0,
    )
    deductions = models.DecimalField(
        _('deductions · কর্তন'), max_digits=12, decimal_places=2, default=0,
    )

    bank_account = models.CharField(_('bank account · ব্যাংক হিসাব'), max_length=40, blank=True)
    mobile_banking = models.CharField(
        _('mobile banking · মোবাইল ব্যাংকিং'), max_length=40, blank=True,
    )
    emergency_contact_name = models.CharField(
        _('emergency contact · জরুরি যোগাযোগ'), max_length=120, blank=True,
    )
    emergency_contact_phone = models.CharField(
        _('emergency contact phone · জরুরি ফোন'), max_length=20, blank=True,
    )

    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        abstract = True
        ordering = ['branch', 'name']

    def __str__(self):
        return self.name

    @property
    def gross_salary(self):
        """Basic + allowances − deductions.

        A property and not a stored column: nothing reports off it yet, and a
        stored total is a value that can disagree with its own parts. Payroll
        (V2) stores its figures on the payslip, where they are a historical
        record rather than a derivation.
        """
        return self.basic_salary + self.allowances - self.deductions


class Teacher(PersonProfile):
    """Teaching staff.

    Pointed at by `AcademicClass.class_teacher`, `Section.in_charge`,
    `SubjectAssignment.teacher` and `ClassRoutine.teacher` — none of which can
    point at an `Employee`, which is itself an argument for the split (docs/03
    §5.1). Those same relations are what a teacher may *reach* (docs/08 D6); see
    `academics.services.teacher_class_scope`.
    """

    # Globally unique, not per-branch: the branch code is inside the value
    # (`TCH-DHK-0042`), so a global unique index costs nothing extra and makes
    # the id safe to quote across institutions — which is what an id printed on
    # a card has to be.
    teacher_id = models.CharField(_('teacher id · শিক্ষক আইডি'), max_length=20, unique=True)

    # M2M because a madrasah teacher commonly covers both the hifz and the
    # general stream, and the routine screen has to offer them classes in either.
    streams = models.ManyToManyField(
        'branches.Stream',
        verbose_name=_('streams · শাখাসমূহ'),
        related_name='teachers',
        blank=True,
    )

    # A convenience flag for filtering the staff list. The authoritative link is
    # `AcademicClass.class_teacher`; nothing derives access from this field,
    # because the two are set by different people at different times.
    is_class_teacher = models.BooleanField(_('class teacher · শ্রেণি শিক্ষক'), default=False)
    specialization = models.CharField(
        _('specialization · বিশেষত্ব'), max_length=120, blank=True,
    )
    # Guards against over-assignment on the routine screen. Null means the
    # institution has not set a limit, which is not the same as a limit of zero.
    max_weekly_periods = models.PositiveIntegerField(
        _('max weekly periods · সাপ্তাহিক সর্বোচ্চ ঘণ্টা'), null=True, blank=True,
    )

    class Meta(PersonProfile.Meta):
        verbose_name = _('teacher · শিক্ষক')
        verbose_name_plural = _('teachers · শিক্ষকগণ')
        ordering = ['branch', 'name']
        indexes = [
            models.Index(fields=['branch', 'employment_status'],
                         name='teacher_branch_status_idx'),
            models.Index(fields=['branch', 'is_active', 'name'],
                         name='teacher_branch_active_idx'),
        ]

    def __str__(self):
        return f'{self.name} ({self.teacher_id})'


class Employee(PersonProfile):
    """Non-teaching staff — office, kitchen, hostel, security, transport."""

    employee_id = models.CharField(_('employee id · কর্মচারী আইডি'), max_length=20, unique=True)
    department = models.CharField(_('department · বিভাগ'), max_length=80, blank=True)
    duty_shift = models.CharField(_('duty shift · কর্মপালা'), max_length=40, blank=True)

    class Meta(PersonProfile.Meta):
        verbose_name = _('employee · কর্মচারী')
        verbose_name_plural = _('employees · কর্মচারীগণ')
        ordering = ['branch', 'name']
        indexes = [
            models.Index(fields=['branch', 'employment_status'],
                         name='employee_branch_status_idx'),
            models.Index(fields=['branch', 'department'],
                         name='employee_branch_dept_idx'),
        ]

    def __str__(self):
        return f'{self.name} ({self.employee_id})'


class TeacherQualification(BranchScopedModel):
    """One degree. A teacher has several (docs/03 §5).

    Its own table rather than a text field on the profile, because "how many of
    our teachers hold a Kamil?" is a question an institution actually gets asked
    — by a board, in writing — and free text cannot answer it.
    """

    # CASCADE: a qualification is meaningless without the teacher it describes,
    # and it is one of the few rows in this project with no financial or
    # academic consequence of its own (CLAUDE.md §4.2).
    teacher = models.ForeignKey(
        Teacher,
        verbose_name=_('teacher · শিক্ষক'),
        on_delete=models.CASCADE,
        related_name='qualifications',
    )
    degree = models.CharField(_('degree · সনদ'), max_length=120)
    institution = models.CharField(_('institution · প্রতিষ্ঠান'), max_length=150, blank=True)
    year = models.PositiveIntegerField(_('year · সাল'), null=True, blank=True)
    result = models.CharField(_('result · ফলাফল'), max_length=60, blank=True)
    # Served through an authenticated view, never a public URL (docs/01 §8) — a
    # certificate carries a name, a date of birth and a signature.
    certificate = models.FileField(
        _('certificate · সনদপত্র'),
        upload_to='staff/qualifications/', null=True, blank=True,
    )

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('qualification · শিক্ষাগত যোগ্যতা')
        verbose_name_plural = _('qualifications · শিক্ষাগত যোগ্যতা')
        # Most recent first: that is the one a testimonial quotes.
        ordering = ['teacher', '-year', 'degree']
        constraints = [
            # The same degree from the same institution twice is a duplicate
            # entry, not a second qualification.
            models.UniqueConstraint(
                fields=['teacher', 'degree', 'institution'],
                name='qualification_unique_per_teacher',
            ),
        ]

    def __str__(self):
        return f'{self.degree} — {self.teacher.name}'
