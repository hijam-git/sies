"""Everything that moves money. All of it in `transaction.atomic()`.

Five operations, and the reason each is here rather than in a serializer or a
signal (CLAUDE.md §4.3):

* `collect_fee()` — one transaction that locks the receipt counter, writes the
  Payment, updates the invoice, and posts the Income row (docs/06 #10). The
  three cannot be allowed to happen separately.
* `generate_monthly_fees()` — the 1st-of-month Celery job. Idempotent, and
  idempotent **at the database**: `Fee`'s unique constraint is what makes a
  retried run write nothing (docs/06 #9).
* `accrue_fines()` — nightly, from `Branch.fine_rule`, capped, and it stops the
  moment the balance reaches zero.
* `raise_admission_fees()` — called from `students.services.admit_student()`,
  inside that admission's transaction.
* `reverse_payment()` — a wrong receipt is reversed, never deleted.

**Status is derived here and nowhere else.** `recalculate_fee()` is the only
writer of `payable`, `paid_amount` and `status`, so the state machine in
docs/06 #8 exists in exactly one function that can be read and tested.

Money is `Decimal` throughout — including the `Sum()` below, which names an
`output_field` so the aggregate cannot come back as a float.
"""

import calendar
import logging
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import DecimalField, F, Sum
from django.utils import timezone

from accounts.models import ActivityAction
from accounts.services import CodedError, log_activity
from core.services import format_number, next_number

from .models import (ZERO, Fee, FeeCategory, FeeStatus, GeneratedBy,
                     OUTSTANDING_STATUSES, Payment, PaymentMethod, Recurrence)

logger = logging.getLogger(__name__)

CENT = Decimal('0.01')

# ─────────────────────────────────────────────────────────────────────────────
# Number series (CLAUDE.md §4.4)
#
# Both go through `core.services.next_number`, which is the only number
# generator in this project. Do not add another — three parallel ones appeared
# in Phase 2 (worklog F23) and the institution ended up with three counters for
# what people think of as one number.
#
# `kind` is a plain string rather than a `NumberSequence.Kind` member so this
# app needs no edit to `core/models.py`. The counter row is keyed on the string:
# renaming either constant restarts a branch's counter at 1 and re-issues
# receipt numbers that are already printed on paper people are holding.
# ─────────────────────────────────────────────────────────────────────────────

RECEIPT_KIND = 'receipt'
INVOICE_KIND = 'invoice'

RECEIPT_PREFIX = 'RCP'
INVOICE_PREFIX = 'INV'


def next_receipt_no(branch):
    """`RCP-DHK-000417` — gapless per branch, and read out loud at the counter.

    **Must be called inside the transaction that writes the Payment.** The row
    lock `next_number` takes is released at commit; reserving a number and then
    failing to write its receipt leaves a hole in a series whose only promise is
    that it has none.
    """
    _n, padded = next_number(branch=branch, kind=RECEIPT_KIND, width=6)
    return format_number(prefix=RECEIPT_PREFIX, branch=branch, number_padded=padded)


def next_invoice_no(branch, *, year=None):
    """`INV-DHK-2026-000123`.

    The year is in the string because an invoice is filed by the year it was
    raised in; the counter itself does not reset, so the number stays unique
    across the life of the institution without a per-year scope to reason about.
    """
    _n, padded = next_number(branch=branch, kind=INVOICE_KIND, width=6)
    return format_number(prefix=INVOICE_PREFIX, branch=branch,
                         number_padded=padded, year=year or timezone.localdate().year)


def money(value, field='amount'):
    """Decimal at two places, or a 400 naming the field. Never a float.

    Via `str()` deliberately: `Decimal(0.1)` is
    0.1000000000000000055511151231257827, because that is what the float
    actually is. A ledger built on that drifts by paisa per row and stops
    reconciling, and the first person to notice is a guardian holding a receipt
    (CLAUDE.md §1).
    """
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            raise CodedError(f'{field} must be a number · সংখ্যা লিখুন।',
                             'invalid_amount')
    return amount.quantize(CENT)


def _actor(user):
    """A saveable user, or None. AnonymousUser has no pk and cannot be an FK."""
    return user if getattr(user, 'is_authenticated', False) else None


# ─────────────────────────────────────────────────────────────────────────────
# The state machine (docs/06 #8)
# ─────────────────────────────────────────────────────────────────────────────

def paid_total(fee):
    """Sum of this invoice's live receipts. Decimal, always.

    `output_field=DecimalField(...)` is not decoration: without it Django infers
    the field from the expression and a `Sum` over a joined column can come back
    as something other than a Decimal on some backends. On a money column that
    is the one place a float can still get in (CLAUDE.md §1).

    Reversed receipts are excluded — that is what a reversal *is*, and it is why
    `reverse_payment()` needs no compensating arithmetic of its own.
    """
    total = fee.payments.filter(is_reversed=False, is_active=True).aggregate(
        total=Sum('amount', output_field=DecimalField(max_digits=12, decimal_places=2)),
    )['total']
    return (total or ZERO).quantize(CENT)


def derive_status(fee, *, allow_overdue=False, on_date=None):
    """The status this invoice's numbers imply. Never read from a request body.

    Two callers, two meanings for `allow_overdue`, and the split is exactly what
    docs/06 #8 draws:

    * At collection time (`allow_overdue=False`) a part payment on a late
      invoice moves it to `partial` — the diagram's `overdue → partial` edge.
      The counter's screen should show that money arrived, not keep shouting
      "overdue" at the person who just paid.
    * The nightly job (`allow_overdue=True`) is what moves an unpaid or partly
      paid invoice to `overdue` once the due date passes. That is the diagram's
      `unpaid → overdue` and `partial → overdue` edges, and it is a *time*
      transition, so a time-driven job is the only honest place for it.

    `waived` is terminal and returns unchanged: money arriving on a waived
    invoice is a data-entry mistake, not a state change (`collect_fee()` refuses
    it outright).
    """
    if fee.status == FeeStatus.WAIVED:
        return FeeStatus.WAIVED

    payable = fee.payable or ZERO
    paid = fee.paid_amount or ZERO

    if paid >= payable:
        return FeeStatus.PAID

    # Overdue outranks partial, but only for the nightly caller. That ordering
    # is the diagram's `partial → overdue` edge: a part-paid invoice whose due
    # date has passed is late, and the dues report has to see it. At collection
    # time the ordering is reversed by `allow_overdue=False`, which is the
    # `overdue → partial` edge.
    on_date = on_date or timezone.localdate()
    if allow_overdue and fee.due_date and fee.due_date < on_date:
        return FeeStatus.OVERDUE

    if paid > ZERO:
        return FeeStatus.PARTIAL
    return FeeStatus.UNPAID


def recalculate_fee(fee, *, allow_overdue=False, on_date=None, save=True):
    """Recompute `payable`, `paid_amount` and `status`. The only writer of all three.

    `payable = amount - discount + fine`, stored rather than computed on read
    because the dues report filters and orders by the balance across every
    invoice in the institution, and a Python property cannot be a WHERE clause
    (docs/03 §7).

    It does **not** persist `amount`, `discount` or `fine` — those are the
    caller's inputs, not derived values, and a caller that changed one has to
    save it (see `accrue_fines()`, which saves `fine` in the same
    `update_fields` list).
    """
    fee.payable = fee.computed_payable.quantize(CENT)
    fee.paid_amount = paid_total(fee)
    fee.status = derive_status(fee, allow_overdue=allow_overdue, on_date=on_date)

    if save:
        fee.save(update_fields=['payable', 'paid_amount', 'status', 'updated_at'])
    return fee


# ─────────────────────────────────────────────────────────────────────────────
# Raising invoices
# ─────────────────────────────────────────────────────────────────────────────

def default_due_date(*, period=None, on_date=None, due_day=10):
    """The 10th of the invoice's month, or of this month for a one-off.

    A fixed day rather than a per-category `due_day`: `FeeStructure` — which is
    where docs/03 puts that column — is V2 (docs/05 §5.4), and inventing a field
    to hold it here would be exactly the drift CLAUDE.md §8.6 forbids. The
    caller passes `due_date` explicitly whenever the institution's rule differs.
    """
    if period:
        year, month = (int(part) for part in period.split('-'))
    else:
        today = on_date or timezone.localdate()
        year, month = today.year, today.month

    last_day = calendar.monthrange(year, month)[1]
    return date_cls(year, month, min(due_day, last_day))


@transaction.atomic
def raise_fee(*, branch, student, category, session, amount, period='',
              enrolment=None, due_date=None, discount=ZERO, note='',
              generated_by=GeneratedBy.MANUAL, actor=None, request=None,
              log=True):
    """Create one invoice, or return `(existing, False)` if it already exists.

    Returns `(fee, created)`.

    **This is where idempotency lives**, and it is the database that provides
    it: the pre-check below is an optimisation, and the `IntegrityError` handler
    underneath it is the actual guarantee. Two workers running the monthly job
    in the same second both pass the pre-check; exactly one of them wins the
    unique constraint and the other returns the winner's row.

    The savepoint around the insert is not optional. On Postgres an
    IntegrityError marks the enclosing transaction as broken, so catching one
    without a savepoint would leave the caller — a whole month's generation
    loop — unable to commit anything at all.

    Atomic in its own right, and it has to be: the invoice number is reserved
    from the shared counter under a row lock, so a reservation whose insert then
    failed would leave a hole. Nesting inside a caller's transaction (the
    monthly loop, an admission) makes it a savepoint, which is the correct
    behaviour there too.
    """
    period = period or ''
    # `is_active=True`: a cancelled invoice is soft-deleted (CLAUDE.md §4.2), and
    # counting it here meant a month cancelled by mistake could never be raised
    # again — `generate_monthly_fees` skipped that (student, category, period)
    # for good, with nothing on any screen to say why.
    existing = Fee.objects.filter(
        branch=branch, student=student, category=category,
        period=period, session=session, is_active=True,
    ).first()
    if existing is not None:
        return existing, False

    amount = money(amount, 'amount')
    discount = money(discount, 'discount')
    if amount < ZERO:
        raise CodedError('An invoice cannot be for a negative amount · '
                         'ঋণাত্মক পরিমাণে বিল করা যাবে না।', 'invalid_amount')
    if discount > amount:
        raise CodedError('The discount cannot be more than the fee · '
                         'ছাড় ফি-এর চেয়ে বেশি হতে পারে না।', 'invalid_discount')

    fee = Fee(
        branch=branch,
        student=student,
        enrolment=enrolment,
        category=category,
        session=session,
        period=period,
        # Filled inside the savepoint below, not here: a number reserved in the
        # outer transaction survives a lost unique-constraint race and leaves a
        # gap in a series the office quotes by number.
        invoice_no='',
        amount=amount,
        discount=discount,
        fine=ZERO,
        due_date=due_date or default_due_date(period=period),
        generated_by=generated_by,
        note=note or '',
        created_by=_actor(actor),
    )
    fee.payable = fee.computed_payable
    fee.paid_amount = ZERO
    fee.status = FeeStatus.UNPAID

    try:
        with transaction.atomic():
            fee.invoice_no = next_invoice_no(branch)
            fee.save()
    except IntegrityError:
        # Lost the race, or the invoice was raised between the pre-check and
        # here. The winner's row is what the caller wanted either way.
        existing = Fee.objects.filter(
            branch=branch, student=student, category=category,
            period=period, session=session, is_active=True,
        ).first()
        if existing is None:
            raise
        return existing, False

    if log:
        log_activity(
            action=ActivityAction.CREATE,
            user=actor, request=request, branch=branch, obj=fee,
            model='Fee',
            summary=(f'Raised {fee.invoice_no} · {category.code} {amount} '
                     f'for {student.name}'),
            summary_bn=f'{student.name}-এর জন্য {category.name} বিল তৈরি হয়েছে',
            # atomic=False: the monthly job raises thousands of these, and an
            # audit table that is momentarily full must not fail a month of
            # invoicing. Collection — where money actually moves — logs
            # atomically instead.
            atomic=False,
        )
    return fee, True


def raise_admission_fees(*, enrolment=None, student=None, amounts=None,
                         actor=None, request=None):
    """The Admission Fee and the Session Fee, raised when a student is admitted.

    Called from `students.services.admit_student()` **inside that admission's
    transaction** (docs/02 §4.1), so a student never exists without the invoices
    admitting them creates. Returns the list of invoices actually raised.

    `amounts` is `{'ADM': Decimal('1000'), 'SES': Decimal('500')}` — what this
    particular admission charges, which wins when it is given. Without it each
    head is priced from its own `default_amount`, set on Fees → Fee setup, so
    an institution that priced its heads once does not have to repeat the
    figure on every admission.

    A head with neither is skipped rather than raised at zero: an invoice for
    ৳0 looks paid, prints, and hides the fact that nobody set the admission fee.
    """
    if enrolment is None:
        raise CodedError('An enrolment is required to raise admission fees.',
                         'enrolment_required')

    amounts = amounts or {}
    branch = getattr(enrolment, 'branch', None)
    if branch is None:
        # A stand-in enrolment. `admit_student()` is the caller and its own
        # tests substitute the enrolment service, whose stand-in carries no
        # branch — there is nothing to price against, so nothing to raise.
        return []

    student = student or enrolment.student
    raised = []

    for code in ('ADM', 'SES'):
        category = FeeCategory.objects.filter(
            branch=branch, code=code, is_active=True,
        ).first()
        if category is None:
            logger.warning('Branch %s has no active %s fee category', branch.code, code)
            continue

        # This admission's own figure first, then the head's standing price.
        amount = amounts.get(code)
        if amount is None:
            amount = category.default_amount
        if amount is None:
            continue

        fee, created = raise_fee(
            branch=branch,
            student=student,
            enrolment=enrolment,
            category=category,
            session=enrolment.session,
            amount=amount,
            # Blank period: both are once-per-(student, session) charges, and
            # the unique key already carries the session. A period here would
            # let the same admission fee be raised twice in one year.
            period='',
            due_date=default_due_date(on_date=enrolment.enrolled_on),
            generated_by=GeneratedBy.SYSTEM,
            actor=actor, request=request,
        )
        if created:
            raised.append(fee)

    return raised


def _applies_to_enrolment(category, enrolment):
    """Does this category apply to this student, this year? (docs/06 #9)

    Three filters, all read off `FeeCategory.applies_to`: the stream list, and
    the two flags that live on the *enrolment* rather than on the student —
    because a student may board one year and not the next, and last year's fees
    must not change when they move out (`academics.Enrolment`).
    """
    rule = category.applies_to or {}

    streams = rule.get('streams') or []
    if streams:
        stream_id = (enrolment.academic_class.stream_id
                     or getattr(enrolment.student, 'stream_id', None))
        if stream_id not in streams:
            return False

    if rule.get('hostel_only') and not enrolment.is_hostel:
        return False
    if rule.get('transport_only') and not enrolment.is_transport:
        return False
    return True


#: The monthly বেতন, the one head `AcademicClass.monthly_fee` prices.
TUITION_CODE = 'MON'


def monthly_amount(category, enrolment, *, amounts=None):
    """What this category costs this student this month, or None if unpriced.

    Three price sources, most specific first:

    * `amounts` — what this run was told to charge, which is how a one-off
      generation prices a head differently for a month;
    * `AcademicClass.monthly_fee` — the per-class tuition, and **only** for the
      tuition head: it is the monthly বেতন, not the hostel, not the bus, and not
      the electricity charge an institution adds later;
    * `FeeCategory.default_amount` — the institution's own price for this head,
      typed on Fees → Fee setup.

    The third used to be missing, which made that screen a lie: the field was
    served by the API and editable, an accountant set ৳500 against Transport
    Fee, and the monthly job still skipped it as unpriced. `FeeStructure` — a
    price per class *and* head — is still V2 (docs/05 §5.4); this is the
    per-institution price, which is what the seeded heads are.

    Returning None rather than 0 is deliberate. A ৳0 hostel invoice is
    indistinguishable from a paid one on every screen, so it would quietly
    replace "nobody has set the hostel fee" with "this student owes nothing" —
    and by the time anyone notices, a term of hostel fees was never billed.
    """
    override = (amounts or {}).get(category.code)
    if override is not None:
        return money(override, category.code)

    # `MON` and nothing else. "Not hostel and not transport" was the wrong
    # test: an institution that adds a second monthly head — Electricity at
    # ৳200, priced on Fees → Fee setup — had every student billed the class
    # tuition for it instead, every month, silently.
    if category.code == TUITION_CODE:
        fee = getattr(enrolment.academic_class, 'monthly_fee', None)
        if fee is not None:
            return money(fee, 'monthly_fee')

    if category.default_amount is not None:
        return money(category.default_amount, category.code)
    return None


def current_period(on_date=None):
    """`'2026-03'` — the period string for a month."""
    today = on_date or timezone.localdate()
    return f'{today.year:04d}-{today.month:02d}'


def generate_monthly_fees(branch=None, *, period=None, on_date=None,
                          amounts=None, actor=None):
    """Raise this month's recurring invoices. **Safe to run twice** (docs/06 #9).

    Returns `{'created': n, 'skipped': n, 'unpriced': n}`.

    `branch=None` means every active institution — that is how the beat task
    calls it. One transaction per (enrolment, category) rather than one for the
    whole run: a month of generation across every branch in a single
    transaction is a long lock on the invoice counter, and one bad row would
    roll back thousands of correct ones.

    Idempotency is not implemented here. It is `Fee`'s unique constraint on
    (branch, student, category, period, session), and `raise_fee()` is where a
    losing insert is turned back into the winning row. That single line is what
    stands between a retried job and a double-charged guardian.
    """
    from academics.models import Enrolment, EnrolmentStatus
    from branches.models import Branch

    period = period or current_period(on_date)
    branches = [branch] if branch is not None else list(
        Branch.objects.filter(is_active=True).order_by('id')
    )

    result = {'created': 0, 'skipped': 0, 'unpriced': 0}

    for each in branches:
        categories = list(
            FeeCategory.objects.filter(
                branch=each, recurrence=Recurrence.MONTHLY, is_active=True,
            ).order_by('display_order', 'id')
        )
        if not categories:
            continue

        enrolments = (
            Enrolment.objects
            .filter(branch=each, is_active=True, status=EnrolmentStatus.ACTIVE,
                    session__is_current=True)
            .select_related('student', 'academic_class', 'session')
            .order_by('id')
        )

        for enrolment in enrolments.iterator():
            for category in categories:
                if not _applies_to_enrolment(category, enrolment):
                    continue

                amount = monthly_amount(category, enrolment, amounts=amounts)
                if amount is None or amount <= ZERO:
                    result['unpriced'] += 1
                    continue

                with transaction.atomic():
                    _fee, created = raise_fee(
                        branch=each,
                        student=enrolment.student,
                        enrolment=enrolment,
                        category=category,
                        session=enrolment.session,
                        amount=amount,
                        period=period,
                        generated_by=GeneratedBy.SYSTEM,
                        actor=actor,
                    )
                result['created' if created else 'skipped'] += 1

    logger.info('generate_monthly_fees %s: %s', period, result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Fines (docs/03 §1 — Branch.fine_rule)
# ─────────────────────────────────────────────────────────────────────────────

def fine_for(*, rule, days_late):
    """`per_day × days`, capped at `max`. Decimal, from JSON that may hold floats.

    `Decimal(str(...))` on every value read out of the JSON blob: those numbers
    arrive from a settings screen as JSON, which means they may genuinely be
    floats, and `Decimal(0.1)` is not 0.10 (CLAUDE.md §1).
    """
    per_day = Decimal(str(rule.get('per_day') or 0))
    cap = Decimal(str(rule.get('max') or 0))
    if per_day <= 0 or days_late <= 0:
        return ZERO

    amount = (per_day * Decimal(days_late)).quantize(CENT)
    if cap > 0:
        amount = min(amount, cap.quantize(CENT))
    return amount


def accrue_fines(branch=None, *, on_date=None):
    """Nightly. Add the late fine to every still-outstanding invoice.

    Returns `{'updated': n, 'unchanged': n}`.

    Four properties, each of which is a rule someone will be asked about:

    * **respects the grace period** — a fine starts `grace_days` after the due
      date, not on it;
    * **capped** — `fine_rule['max']` is a ceiling, so an invoice forgotten for
      a year does not accrue a fine larger than the fee;
    * **stops when paid** — the queryset excludes anything whose balance has
      reached zero, so a paid invoice never gains a fine overnight;
    * **idempotent within a day** — the fine is *recomputed from the day count*,
      never incremented, so running the job twice on the same night produces
      the same number. An `F('fine') + x` here would double it.
    """
    from branches.models import Branch

    on_date = on_date or timezone.localdate()
    branches = [branch] if branch is not None else list(
        Branch.objects.filter(is_active=True).order_by('id')
    )
    result = {'updated': 0, 'unchanged': 0}

    for each in branches:
        rule = each.fine_rule or {}
        if Decimal(str(rule.get('per_day') or 0)) <= 0:
            # The branch has not set a fine policy. Reading it and moving on is
            # the documented behaviour of `default_fine_rule()`.
            continue

        grace = int(rule.get('grace_days') or 0)
        cutoff = on_date - timedelta(days=grace)

        outstanding = (
            Fee.objects
            .filter(branch=each, is_active=True, status__in=OUTSTANDING_STATUSES,
                    due_date__lt=cutoff)
            # "Stops when paid", in the queryset rather than in the loop: a
            # fully paid invoice is never even read, so it cannot gain a fine
            # overnight.
            .filter(paid_amount__lt=F('payable'))
            .order_by('id')
        )

        for fee in outstanding.iterator():
            days_late = (on_date - fee.due_date).days - grace
            fine = fine_for(rule=rule, days_late=days_late)

            if fine == (fee.fine or ZERO):
                # Already at the cap, or nothing to add. Recompute the status
                # anyway — this is the job that moves a due-date-passed invoice
                # to `overdue` (docs/06 #8).
                before = fee.status
                recalculate_fee(fee, allow_overdue=True, on_date=on_date)
                result['updated' if fee.status != before else 'unchanged'] += 1
                continue

            with transaction.atomic():
                fee.fine = fine
                recalculate_fee(fee, allow_overdue=True, on_date=on_date, save=False)
                fee.save(update_fields=['fine', 'payable', 'paid_amount',
                                        'status', 'updated_at'])
            result['updated'] += 1

    logger.info('accrue_fines %s: %s', on_date, result)
    return result


def mark_overdue(branch=None, *, on_date=None):
    """Move past-due invoices to `overdue` even where no fine is configured.

    `accrue_fines()` does this as a side effect for branches that fine; a branch
    with `per_day: 0` would otherwise never leave `unpaid`, and its dues screen
    would show nothing as late.
    """
    from branches.models import Branch

    on_date = on_date or timezone.localdate()
    branches = [branch] if branch is not None else list(
        Branch.objects.filter(is_active=True).order_by('id')
    )
    updated = 0

    for each in branches:
        stale = (
            Fee.objects
            .filter(branch=each, is_active=True, due_date__lt=on_date,
                    status__in=(FeeStatus.UNPAID, FeeStatus.PARTIAL))
            .filter(paid_amount__lt=F('payable'))
            .order_by('id')
        )
        for fee in stale.iterator():
            recalculate_fee(fee, allow_overdue=True, on_date=on_date)
            updated += int(fee.status == FeeStatus.OVERDUE)

    return updated


# ─────────────────────────────────────────────────────────────────────────────
# Collection — the one cross-module write (docs/06 #10)
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def collect_fee(*, fee, amount, method=PaymentMethod.CASH, transaction_id='',
                paid_at=None, collected_by=None, note='', request=None):
    """Take money against one invoice. Returns the `Payment`.

    **One transaction, four writes, no exceptions** (docs/06 #10):

      1. lock the invoice row, so two clerks cannot both pass the
         over-collection check against the same balance;
      2. reserve the receipt number from the per-branch counter, under the row
         lock `core.services.next_number` takes;
      3. insert the Payment, then recompute the invoice's `paid_amount` and
         `status`;
      4. insert the matching `finance.Income` row, in this same transaction.

    Step 4 is what makes the fee ledger and the accounts unable to disagree:
    there is one entry, written by the system, and nobody re-types the second
    (docs/02 §4.6). If any step fails, none of them happened — including the
    income row, which is the property `test_income.py` pins.
    """
    # SELECT … FOR UPDATE on the invoice. Without it, two concurrent
    # collections both read a balance of 500, both accept 500, and the invoice
    # ends up paid twice — the money is real, so the error surfaces as an
    # over-collection nobody can explain rather than as a failed request.
    fee = Fee.objects.select_for_update().select_related(
        'branch', 'student', 'category', 'session',
    ).get(pk=fee.pk)

    amount = money(amount, 'amount')
    if amount <= ZERO:
        raise CodedError('Enter an amount greater than zero · '
                         'শূন্যের বেশি পরিমাণ লিখুন।', 'invalid_amount')

    if fee.status == FeeStatus.WAIVED:
        raise CodedError('This fee has been waived; there is nothing to collect · '
                         'এই ফি মওকুফ করা হয়েছে।', 'fee_waived')
    if not fee.is_active:
        raise CodedError('This invoice is cancelled · এই বিলটি বাতিল।',
                         'fee_inactive')

    # Recompute the balance from the live rows rather than trusting the stored
    # column: it is the number the refusal below is decided on, and a stale
    # `paid_amount` would let the invoice be over-collected by exactly the
    # amount it was stale by.
    recalculate_fee(fee, save=True)
    balance = fee.balance

    if balance <= ZERO:
        raise CodedError('This fee is already fully paid · '
                         'এই ফি ইতিমধ্যে সম্পূর্ণ পরিশোধিত।', 'already_paid')
    if amount > balance:
        # Refused, not clamped. Taking ৳600 against a ৳500 balance and silently
        # recording ৳500 hands the guardian a receipt for less than they paid.
        raise CodedError(
            f'That is more than the outstanding balance ({balance}) · '
            f'বকেয়ার ({balance}) চেয়ে বেশি পরিমাণ নেওয়া যাবে না।',
            'over_collection',
        )

    payment = Payment.objects.create(
        branch=fee.branch,
        fee=fee,
        student=fee.student,
        receipt_no=next_receipt_no(fee.branch),
        amount=amount,
        method=method or PaymentMethod.CASH,
        transaction_id=transaction_id or '',
        paid_at=paid_at or timezone.now(),
        collected_by=_actor(collected_by),
        note=note or '',
        created_by=_actor(collected_by),
    )

    recalculate_fee(fee, save=True)

    # The cross-module write. Imported here rather than at module scope: it is
    # the only place `fees` touches `finance`, and keeping the import local
    # makes the one-way dependency visible at the call site (CLAUDE.md §2).
    from finance.services import post_payment_income

    payment.income = post_payment_income(payment)
    payment.save(update_fields=['income', 'updated_at'])

    log_activity(
        action=ActivityAction.COLLECT,
        user=collected_by, request=request, branch=fee.branch, obj=payment,
        model='Payment',
        summary=(f'Receipt {payment.receipt_no} · {amount} from '
                 f'{fee.student.name} for {fee.category.code}'),
        summary_bn=f'{fee.student.name}-এর কাছ থেকে {amount} টাকা আদায় '
                   f'(রসিদ {payment.receipt_no})',
        after={'receipt_no': payment.receipt_no, 'amount': str(amount),
               'method': payment.method, 'fee': fee.invoice_no,
               'status': fee.status},
        # atomic=True: this is money. A receipt whose audit row could not be
        # written is a payment with no record of who took it, and rolling both
        # back is the right answer (accounts.services.log_activity).
        atomic=True,
    )

    # The receipt, on the guardian's phone — if this institution asked for it.
    # `notify()` swallows anything the send raises: the money is written and
    # audited above, and a courtesy about the money does not get to roll back
    # a receipt (notifications.services).
    from notifications.services import notify, send_payment_sms

    notify(send_payment_sms, payment, actor=collected_by)

    return payment


@transaction.atomic
def reverse_payment(payment, *, reason, actor=None, request=None):
    """Reverse a wrong receipt. **Never delete one** (docs/01 §9, docs/06 #8).

    The Payment row stays, flagged, with the reason and who did it. Its income
    row is reversed in the same transaction, so the ledger moves with the
    receipt rather than being corrected by hand afterwards. The invoice is then
    recomputed: `paid_amount` drops because `paid_total()` excludes reversed
    receipts, which is the diagram's `paid → partial` edge.

    Deleting instead would destroy an accounting record, un-post income with no
    trace, and leave a hole in a receipt series whose only promise is that it
    has none.
    """
    if not reason:
        raise CodedError('Give a reason for the reversal · '
                         'বাতিলের কারণ লিখুন।', 'reason_required')

    payment = Payment.objects.select_for_update().select_related('fee').get(pk=payment.pk)
    if payment.is_reversed:
        raise CodedError('This receipt is already reversed · '
                         'এই রসিদ ইতিমধ্যে বাতিল করা হয়েছে।', 'already_reversed')

    payment.is_reversed = True
    payment.reversed_at = timezone.now()
    payment.reversed_by = _actor(actor)
    payment.reverse_reason = reason
    payment.save(update_fields=['is_reversed', 'reversed_at', 'reversed_by',
                                'reverse_reason', 'updated_at'])

    if payment.income_id is not None:
        from finance.services import reverse_income

        reverse_income(payment.income, reason=f'Receipt {payment.receipt_no} reversed: {reason}',
                       actor=actor, request=request)

    fee = Fee.objects.select_for_update().get(pk=payment.fee_id)
    recalculate_fee(fee, save=True)

    log_activity(
        action=ActivityAction.UPDATE,
        user=actor, request=request, branch=payment.branch, obj=payment,
        model='Payment',
        summary=f'Reversed receipt {payment.receipt_no}: {reason}',
        summary_bn=f'রসিদ {payment.receipt_no} বাতিল করা হয়েছে',
        atomic=True,
    )
    return payment


@transaction.atomic
def waive_fee(fee, *, reason, actor=None, request=None):
    """Write off the remainder of an invoice, with a reason and a name attached.

    `waived` is terminal (docs/06 #8): `collect_fee()` refuses a waived invoice,
    and `derive_status()` leaves it alone. Any payments already taken stay —
    what is waived is the balance, not the history.
    """
    if not reason:
        raise CodedError('Give a reason for the waiver · মওকুফের কারণ লিখুন।',
                         'reason_required')

    fee = Fee.objects.select_for_update().get(pk=fee.pk)
    if fee.status == FeeStatus.WAIVED:
        raise CodedError('This fee is already waived · এই ফি ইতিমধ্যে মওকুফ করা হয়েছে।',
                         'already_waived')
    if fee.status == FeeStatus.PAID:
        raise CodedError('This fee is already paid in full · '
                         'এই ফি সম্পূর্ণ পরিশোধিত।', 'already_paid')

    fee.status = FeeStatus.WAIVED
    fee.waived_by = _actor(actor)
    fee.waived_at = timezone.now()
    fee.waive_reason = reason
    fee.save(update_fields=['status', 'waived_by', 'waived_at', 'waive_reason',
                            'updated_at'])

    log_activity(
        action=ActivityAction.WAIVE,
        user=actor, request=request, branch=fee.branch, obj=fee,
        model='Fee',
        summary=f'Waived {fee.invoice_no} ({fee.balance} outstanding): {reason}',
        summary_bn=f'{fee.invoice_no} মওকুফ করা হয়েছে',
        atomic=True,
    )
    return fee
