"""Branch, Stream and Session — the institution and its academic frame.

`Branch` is the one model the whole database hangs off: a **complete
institution**, not a campus of one (docs/08 D1). It is deliberately NOT
branch-scoped — it *is* the branch — and it is one of the rows on the closed
global list (CLAUDE.md §4.1).

`Stream` and `Session` are branch-scoped like everything else.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel


def default_weekly_off_days():
    """Friday, the Bangladeshi weekend.

    A callable rather than a literal: a mutable default is shared by every
    instance Django builds, so one branch editing its list would edit them all.
    """
    return ['fri']


def default_fine_rule():
    """No fine until the institution asks for one.

    `per_day` at 0 means the nightly fine job (docs/01 §4) reads this branch,
    computes nothing and moves on — the right behaviour for an institution that
    has not decided its policy yet. These are configuration numbers the fee
    service converts to Decimal on read, never an amount stored on a row.
    """
    return {'per_day': 0, 'grace_days': 0, 'max': 0}


class InstitutionType(models.TextChoices):
    """What kind of institution this branch is (docs/08 D1).

    It selects what `seeding.seed_branch()` creates and which labels the UI
    shows — মুহতামিম vs Principal, জামাত vs Class. Nothing in this codebase may
    be hard-coded to a madrasah; this field is how the difference is expressed.
    """

    MADRASAH = 'madrasah', _('Madrasah · মাদ্রাসা')
    SCHOOL = 'school', _('School · স্কুল')
    COLLEGE = 'college', _('College · কলেজ')
    COMBINED = 'combined', _('Combined · সমন্বিত')


class Language(models.TextChoices):
    BANGLA = 'bn', _('বাংলা · Bangla')
    ENGLISH = 'en', _('English · ইংরেজি')


class Branch(models.Model):
    """One institution on the platform — a madrasah, a school or a college.

    Not a `BranchScopedModel`: it is the thing everything else is scoped *to*,
    so it carries no `branch` column. The audit and timestamp columns are spelled
    out here rather than inherited from `BaseModel`, because `BaseModel.Meta`
    orders by `-created_at` and this list is a picker people scan alphabetically.

    Deleting one is not a supported operation — `BranchScopedModel.branch` is
    `PROTECT`, so the database refuses as soon as the institution owns a single
    row. Closing an institution is `is_active = False`.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    name = models.CharField(_('name'), max_length=150)
    name_bn = models.CharField(_('নাম'), max_length=150, blank=True)
    # Arabic, because it prints on the letterhead of a madrasah's certificates
    # and testimonials (docs/07 §1). Blank for a school that has no Arabic name.
    name_ar = models.CharField(_('الاسم'), max_length=150, blank=True)

    institution_type = models.CharField(
        _('institution type · প্রতিষ্ঠানের ধরন'),
        max_length=20,
        choices=InstitutionType.choices,
        default=InstitutionType.MADRASAH,
    )

    # Short, unique, and quoted out loud: it is embedded in every generated
    # number this branch issues — RCP-DHK-2026-00412 (CLAUDE.md §4.4) — so it
    # must be stable and typeable, not a slug of the name.
    code = models.CharField(_('code · কোড'), max_length=10, unique=True)

    established_year = models.PositiveIntegerField(
        _('established year · প্রতিষ্ঠাকাল'), null=True, blank=True,
    )

    # ── Contact ─────────────────────────────────────────────────────────────
    address = models.TextField(_('address'), blank=True)
    address_bn = models.TextField(_('ঠিকানা'), blank=True)
    district = models.CharField(_('district · জেলা'), max_length=80, blank=True)
    thana = models.CharField(_('thana · থানা'), max_length=80, blank=True)
    phone = models.CharField(_('phone · ফোন'), max_length=20, blank=True)
    alt_phone = models.CharField(_('alternate phone · বিকল্প ফোন'), max_length=20, blank=True)
    email = models.EmailField(_('email · ইমেইল'), blank=True)
    logo = models.ImageField(
        _('logo · লোগো'), upload_to='branches/logos/', blank=True, null=True,
    )

    # ── People and the academic frame ───────────────────────────────────────
    # SET_NULL: the principal's account may be deleted; the institution must not
    # go with it. `+` because "which branches does this user head" is a filter on
    # the rare occasion anyone asks, not a relation worth naming.
    head = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('head · প্রধান'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    # PROTECT, not SET_NULL: this is the session every new record defaults to.
    # Deleting the session a branch is actively working in would silently
    # re-point tomorrow's admissions at nothing, so the delete fails instead and
    # whoever meant it has to close the session out first.
    #
    # A string reference because Session is defined below and points back here.
    current_session = models.ForeignKey(
        'branches.Session',
        verbose_name=_('current session · চলতি শিক্ষাবর্ষ'),
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='current_for_branches',
    )

    # ── Policy ──────────────────────────────────────────────────────────────
    fine_rule = models.JSONField(
        _('fine rule · জরিমানার নিয়ম'), default=default_fine_rule, blank=True,
    )

    # docs/08 D7. Generous on purpose: the window guards against a period being
    # marked days later from memory; it is not a punishment for a teacher whose
    # phone lost signal. 0 means unlimited; a strict institution sets 15.
    attendance_window_minutes = models.PositiveIntegerField(
        _('attendance window (minutes) · হাজিরার সময়সীমা'), default=120,
    )

    # docs/08 D6. On by default, because role-only access control lets any
    # teacher holding `attendance.take` mark every class in the institution. A
    # small madrasah where three teachers cover everything turns it off.
    restrict_teachers_to_assigned_classes = models.BooleanField(
        _('restrict teachers to assigned classes · শিক্ষককে নির্ধারিত ক্লাসে সীমাবদ্ধ রাখুন'),
        default=True,
    )

    # docs/08 D8. The activity feed grows faster than any other table; the
    # nightly prune is what keeps it a feature rather than a problem.
    activity_retention_days = models.PositiveIntegerField(
        _('activity retention (days) · কার্যক্রম সংরক্ষণ (দিন)'), default=180,
    )

    # V1, not V2: the month attendance grid (docs/02 §4.4) renders four or five
    # weekends on screen at once and cannot wait for the holiday calendar.
    weekly_off_days = models.JSONField(
        _('weekly off days · সাপ্তাহিক ছুটি'), default=default_weekly_off_days, blank=True,
    )

    sms_sender_id = models.CharField(_('SMS sender id · এসএমএস প্রেরক'), max_length=20, blank=True)
    default_language = models.CharField(
        _('default language · ডিফল্ট ভাষা'),
        max_length=2, choices=Language.choices, default=Language.BANGLA,
    )

    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    # ── Audit ───────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )

    class Meta:
        verbose_name = _('institution · প্রতিষ্ঠান')
        verbose_name_plural = _('institutions · প্রতিষ্ঠানসমূহ')
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active', 'name'], name='branch_active_name_idx'),
        ]

    def __str__(self):
        return f'{self.name} ({self.code})'

    def save(self, *args, **kwargs):
        # Uppercased here rather than in a serializer, because the code is
        # embedded in receipt numbers that are read out over a counter. 'dhk' and
        # 'DHK' issued by the same branch would look like two institutions.
        self.code = (self.code or '').strip().upper()
        return super().save(*args, **kwargs)


class Stream(BranchScopedModel):
    """The student's study sector — the brief's *Student Type* and *Category*,
    which are one field (docs/08 D2).

    A per-branch table rather than a fixed enum, for the two reasons D1 and D2
    give: a college's sectors are Science/Commerce/Arts and not a madrasah's,
    and one madrasah writes হিফজ where another writes হাফজ. The `code` stays
    canonical (`hifz`); only `name_bn` differs, so no institution has to be told
    it spells its own word wrong.

    Pointed at by Student, AcademicClass, Subject, Session and Period, which is
    why it is a table with a foreign key rather than a JSON list on Branch: a
    typo'd stream string would silently create a sixth stream nobody can find.
    """

    code = models.CharField(_('code · কোড'), max_length=20)
    name = models.CharField(_('name'), max_length=60)
    name_bn = models.CharField(_('নাম'), max_length=60, blank=True)
    order = models.PositiveIntegerField(_('order · ক্রম'), default=0)
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('stream · শাখা')
        verbose_name_plural = _('streams · শাখাসমূহ')
        ordering = ['branch', 'order', 'name']
        constraints = [
            # The whole point of `code` being canonical. Without this, a second
            # 'hifz' typed on the settings screen would look identical in every
            # picker and split the institution's students across two ids.
            models.UniqueConstraint(
                fields=['branch', 'code'], name='stream_unique_code_per_branch',
            ),
        ]

    def __str__(self):
        return f'{self.name} · {self.branch.code}'

    def save(self, *args, **kwargs):
        # Lower-cased for the same reason Branch.code is upper-cased: the code is
        # the join between an institution's own label and the canonical set in
        # docs/00 §1, and 'Hifz' must not become a fourth stream.
        self.code = (self.code or '').strip().lower()
        return super().save(*args, **kwargs)


class Session(BranchScopedModel):
    """An academic year.

    `streams` is many-to-many rather than a single FK because some madrasahs run
    the Hijri year for the qaumi stream and the Gregorian for the general one
    (docs/03 §2). A session therefore belongs to a *stream set*, not to the whole
    institution.

    **"At most one current session per (branch, stream)" is enforced in
    `services.set_current_session()`, not by a database constraint.** It cannot
    be one: the pair being constrained spans a join table, and neither
    `UniqueConstraint` nor `CheckConstraint` can reach through an M2M. The
    service is therefore the only supported way to raise `is_current`, and it
    lowers the flag on every session sharing a stream in the same transaction.
    """

    name = models.CharField(_('name · নাম'), max_length=40)
    streams = models.ManyToManyField(
        Stream,
        verbose_name=_('streams · শাখাসমূহ'),
        related_name='sessions',
        blank=True,
    )
    starts_on = models.DateField(_('starts on · শুরু'))
    ends_on = models.DateField(_('ends on · শেষ'))
    is_current = models.BooleanField(_('current · চলতি'), default=False)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('session · শিক্ষাবর্ষ')
        verbose_name_plural = _('sessions · শিক্ষাবর্ষসমূহ')
        # Newest first: the session anyone is working in is almost always the
        # latest, and the picker should open on it.
        ordering = ['branch', '-starts_on', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'name'], name='session_unique_name_per_branch',
            ),
            # A session that ends before it starts breaks every date-range report
            # that reads it — silently, and much later.
            models.CheckConstraint(
                condition=models.Q(ends_on__gt=models.F('starts_on')),
                name='session_ends_after_start',
            ),
        ]

    def __str__(self):
        return f'{self.name} · {self.branch.code}'
