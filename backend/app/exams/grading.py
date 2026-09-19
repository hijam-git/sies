"""Grading — how marks become a grade, one scale per বিভাগ (docs/02 §4.7).

Two methods, because Bangladesh has two marksheet traditions and neither is a
variant of the other:

* **GPA** — the board method, used by general schools and colleges. Each
  subject is graded on its own percentage; GPA is the average of the compulsory
  subjects' grade points, an optional (4th) subject adds only the points it
  earns above a threshold, and failing any compulsory subject fails the result
  with a GPA of 0.00. Merit order is GPA, then total marks.
* **Division** — the Qawmi tradition: one grade from the percentage of the
  total — মুমতাজ, জায়্যিদ জিদ্দান, জায়্যিদ, মাকবুল, রাসিব — and no GPA at all.
  Merit order is total marks.

**The paper's pass mark decides pass or fail; the bands only name what a pass
is worth.** A subject below its schedule's pass mark, or absent, fails in both
methods whatever the bands say. A pass that lands below the lowest passing band
(pass mark 30, bands starting at 33) takes the lowest passing grade rather than
a failing one, because the institution already said that paper was passed.

The presets are what a new বিভাগ starts with. The Qawmi cut-offs differ between
boards, so they are a starting point the institution edits under Settings →
Grading, not a claim about any one board.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q

ZERO = Decimal('0.00')
HUNDRED = Decimal('100')
CENT = Decimal('0.01')

GPA = 'gpa'
DIVISION = 'division'

# (min_percent, grade, grade_bn, point, is_fail) — highest first.
GPA_BANDS = (
    ('80', 'A+', 'এ+', '5.00', False),
    ('70', 'A', 'এ', '4.00', False),
    ('60', 'A-', 'এ-', '3.50', False),
    ('50', 'B', 'বি', '3.00', False),
    ('40', 'C', 'সি', '2.00', False),
    ('33', 'D', 'ডি', '1.00', False),
    ('0', 'F', 'এফ', '0.00', True),
)

DIVISION_BANDS = (
    ('80', 'Mumtaz', 'মুমতাজ', '0.00', False),
    ('65', 'Jayyid Jiddan', 'জায়্যিদ জিদ্দান', '0.00', False),
    ('50', 'Jayyid', 'জায়্যিদ', '0.00', False),
    ('33', 'Maqbul', 'মাকবুল', '0.00', False),
    ('0', 'Rasib', 'রাসিব', '0.00', True),
)

PRESETS = {
    GPA: {'name': 'GPA (board)', 'name_bn': 'জিপিএ পদ্ধতি (বোর্ড)', 'bands': GPA_BANDS},
    DIVISION: {'name': 'Qawmi grades', 'name_bn': 'কওমি পদ্ধতি (মুমতাজ–রাসিব)',
               'bands': DIVISION_BANDS},
}

# Streams that grade the Qawmi way out of the box. Everything else — general,
# science, commerce, arts, and any stream an institution adds — starts on GPA.
DIVISION_STREAM_CODES = frozenset({'hifz', 'qaumi'})

DEFAULT_OPTIONAL_BONUS_ABOVE = Decimal('2.00')


def method_for_stream(code):
    return DIVISION if code in DIVISION_STREAM_CODES else GPA


def preset_band_dicts(method):
    return [
        {'min_percent': Decimal(floor), 'grade': grade, 'grade_bn': grade_bn,
         'point': Decimal(point), 'is_fail': is_fail}
        for floor, grade, grade_bn, point, is_fail in PRESETS[method]['bands']
    ]


# ─────────────────────────────────────────────────────────────────────────────
# The scale, as arithmetic sees it
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Band:
    min_percent: Decimal
    grade: str
    grade_bn: str
    point: Decimal
    is_fail: bool


FALLBACK_FAIL = Band(ZERO, 'F', 'এফ', ZERO, True)


@dataclass(frozen=True)
class Scale:
    name: str
    name_bn: str
    method: str
    optional_bonus_above: Decimal
    bands: tuple  # highest `min_percent` first

    def fail_band(self):
        return next((band for band in self.bands if band.is_fail), FALLBACK_FAIL)

    def passing(self):
        return [band for band in self.bands if not band.is_fail]

    def lowest_pass(self):
        passing = self.passing()
        return min(passing, key=lambda band: band.min_percent) if passing else self.fail_band()

    def top_point(self):
        return max((band.point for band in self.passing()), default=ZERO)

    def band_for_percent(self, percentage):
        for band in self.bands:
            if percentage >= band.min_percent:
                return band
        return self.fail_band()

    def band_for_point(self, gpa):
        for band in sorted(self.passing(), key=lambda b: (b.point, b.min_percent), reverse=True):
            if gpa >= band.point:
                return band
        return self.fail_band()


def _make_scale(name, name_bn, method, bonus, bands):
    return Scale(
        name=name, name_bn=name_bn, method=method,
        optional_bonus_above=Decimal(bonus),
        bands=tuple(sorted(bands, key=lambda band: band.min_percent, reverse=True)),
    )


def preset_scale(method):
    preset = PRESETS[method]
    return _make_scale(
        preset['name'], preset['name_bn'], method, DEFAULT_OPTIONAL_BONUS_ABOVE,
        [Band(**row) for row in preset_band_dicts(method)],
    )


def scale_from_row(row):
    return _make_scale(
        row.name, row.name_bn, row.method, row.optional_bonus_above,
        [Band(band.min_percent, band.grade, band.grade_bn, band.point, band.is_fail)
         for band in row.bands.all()],
    )


def scale_for(exam):
    """The scale this exam is graded on.

    The exam's own বিভাগ first, then the institution-wide scale (stream left
    empty), then the preset its stream code implies — so an institution that
    never opened the Grading screen still gets a sensible marksheet.
    """
    from .models import GradeScale

    rows = list(
        GradeScale.objects
        .filter(branch_id=exam.branch_id, is_active=True)
        .filter(Q(stream_id=exam.stream_id) | Q(stream__isnull=True))
        .prefetch_related('bands')
    )
    row = (
        next((r for r in rows if r.stream_id is not None and r.stream_id == exam.stream_id), None)
        or next((r for r in rows if r.stream_id is None), None)
    )
    if row is not None:
        scale = scale_from_row(row)
        return scale if scale.bands else preset_scale(row.method)

    code = exam.stream.code if exam.stream_id else ''
    return preset_scale(method_for_stream(code))


# ─────────────────────────────────────────────────────────────────────────────
# Marks → grades
# ─────────────────────────────────────────────────────────────────────────────

def evaluate(scale, papers):
    """Grade one student's papers.

    *papers* is a list of `{'name', 'full', 'pass_mark', 'obtained', 'is_absent',
    'is_optional'}` with Decimal numbers; absent papers carry `obtained=0`.

    Returns `(graded, summary)`: `graded` runs parallel to *papers* with each
    paper's `is_passed`, `grade`, `grade_bn` and `point`; `summary` carries the
    totals, percentage, GPA (None under division), overall grade, pass/fail and
    the failed compulsory subjects.
    """
    graded = []
    total_full = ZERO
    total_obtained = ZERO
    points = ZERO
    bonus = ZERO
    compulsory = 0
    failed = []
    is_gpa = scale.method == GPA

    for paper in papers:
        full = paper['full']
        obtained = paper['obtained']
        percentage = (obtained / full * HUNDRED) if full > ZERO else ZERO
        passed = (not paper['is_absent']) and obtained >= paper['pass_mark']

        if passed:
            band = scale.band_for_percent(percentage)
            if band.is_fail:
                band = scale.lowest_pass()
        else:
            band = scale.fail_band()

        if not paper['is_optional']:
            # The optional (4th) subject is out of the percentage for the same
            # reason it is out of the GPA divisor: it can only add. Counting its
            # marks in the total made *taking* it lower the printed percentage —
            # 80 and 80 with an optional 20 read as 60%, and a student who sat
            # an extra paper looked worse for it.
            total_full += full
            total_obtained += obtained

        if paper['is_optional']:
            # Board rule: the optional subject can only help, and only by what
            # it earns above the threshold. Failing it fails nothing.
            if passed:
                bonus += max(ZERO, band.point - scale.optional_bonus_above)
        else:
            compulsory += 1
            points += band.point
            if not passed:
                failed.append(paper['name'])

        graded.append({
            'is_passed': passed,
            'grade': band.grade,
            'grade_bn': band.grade_bn,
            'point': band.point if is_gpa else None,
        })

    percentage = (
        (total_obtained / total_full * HUNDRED).quantize(CENT, ROUND_HALF_UP)
        if total_full > ZERO else ZERO
    )
    is_passed = bool(papers) and not failed and compulsory > 0

    if is_gpa:
        if is_passed:
            gpa = min(scale.top_point(), (points + bonus) / Decimal(compulsory))
            gpa = gpa.quantize(CENT, ROUND_HALF_UP)
            overall = scale.band_for_point(gpa)
        else:
            # A failed student has no GPA on a Bangladeshi marksheet — printing
            # one beside "F" is the contradiction a guardian brings in.
            gpa = ZERO
            overall = scale.fail_band()
    else:
        gpa = None
        overall = scale.band_for_percent(percentage) if is_passed else scale.fail_band()
        if overall.is_fail:
            is_passed = False

    return graded, {
        'total_marks': total_full,
        'obtained_marks': total_obtained,
        'percentage': percentage,
        'gpa': gpa,
        'grade': overall.grade,
        'grade_bn': overall.grade_bn,
        'is_passed': is_passed,
        'failed_subjects': failed,
    }


def rank_key(method, row):
    """What merit order sorts on. Equal keys share a rank."""
    obtained = Decimal(str(row['obtained_marks']))
    if method == GPA:
        return (Decimal(str(row['gpa'] or '0')), obtained)
    return (obtained,)


# ─────────────────────────────────────────────────────────────────────────────
# Writing scales
# ─────────────────────────────────────────────────────────────────────────────

def write_bands(scale, bands, actor=None):
    """Replace a scale's bands. The scale is one decision, so it is written whole."""
    from .models import GradeBand

    scale.bands.all().delete()
    GradeBand.objects.bulk_create([
        GradeBand(
            branch_id=scale.branch_id, scale=scale,
            min_percent=Decimal(str(band['min_percent'])),
            grade=str(band['grade']).strip(),
            grade_bn=str(band.get('grade_bn') or '').strip(),
            point=Decimal(str(band.get('point') or '0')),
            is_fail=bool(band.get('is_fail')),
            created_by=actor, updated_by=actor,
        )
        for band in bands
    ])
    # A viewset's prefetch would otherwise serialise the bands just deleted.
    getattr(scale, '_prefetched_objects_cache', {}).pop('bands', None)


def reset_to_preset(scale, method, actor=None):
    scale.method = method
    scale.updated_by = actor
    scale.save(update_fields=['method', 'updated_by', 'updated_at'])
    write_bands(scale, preset_band_dicts(method), actor=actor)
    return scale


@transaction.atomic
def seed_grade_scales(branch):
    """One scale per stream, from the preset its code implies. Safe to re-run.

    Called from `branches.seeding.seed_branch()`. A scale that already exists
    is left exactly as the institution edited it; only missing ones appear.
    """
    from branches.models import Stream

    from .models import GradeScale

    created = 0
    for stream in Stream.objects.filter(branch=branch):
        method = method_for_stream(stream.code)
        scale, was_created = GradeScale.objects.get_or_create(
            branch=branch, stream=stream,
            defaults={
                'name': PRESETS[method]['name'],
                'name_bn': PRESETS[method]['name_bn'],
                'method': method,
            },
        )
        if was_created:
            write_bands(scale, preset_band_dicts(method))
            created += 1
    return created
