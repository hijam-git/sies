"""Fee categories, invoices and receipts — the money half of the system.

Three tables and one rule each:

* `FeeCategory` — *what may be charged*. Eleven seeded per branch from
  `branches.seed_data.FEE_CATEGORY_SEEDS`; an institution may add its own.
* `Fee` — *what one student owes*, one row per charge. Its uniqueness
  constraint is what makes the monthly Celery job safe to run twice.
* `Payment` — *a receipt*. Separate from the invoice because part payments are
  normal and one invoice may have several (docs/02 §4.5). Collapsing them into
  one row makes the second instalment impossible to record.

**Every amount here is `DecimalField(max_digits=12, decimal_places=2)`**
(CLAUDE.md §1). Not one of them may become a float — including in the
aggregations in `services.py`, which is where a `float` most easily sneaks back
in through `Sum()` without an `output_field`.

`FeeStructure` and standing `Discount` are **V2** (docs/05 §5.4). V1 prices a
monthly invoice from `AcademicClass.monthly_fee` and carries a per-invoice
`discount` amount on `Fee`. Do not add either table here.

Nothing in this module is a signal (CLAUDE.md §4.3). A signal that moves money
is a signal that fires twice during a fixture load.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel

#: Money everywhere in this app. Named so a new column cannot quietly disagree
#: with the eleven that already exist.
MONEY = {'max_digits': 12, 'decimal_places': 2}
ZERO = Decimal('0.00')


class Recurrence(models.TextChoices):
    """How often a category is charged — docs/03 §7.

    It is what `generate_monthly_fees()` filters on, and what tells the UI
    whether an invoice needs a `period`.
    """

    ONE_TIME = 'one_time', _('One time · এককালীন')
    MONTHLY = 'monthly', _('Monthly · মাসিক')
    SESSION = 'session', _('Per session · শিক্ষাবর্ষভিত্তিক')
    EXAM = 'exam', _('Per exam · পরীক্ষাভিত্তিক')
    CUSTOM = 'custom', _('Custom · প্রযোজ্য ক্ষেত্রে')


class FeeStatus(models.TextChoices):
    """Derived, never hand-set (docs/06 #8).

    There is no API path that writes this field from a request body: it is
    computed in `services.recalculate_fee()` from `paid_amount` and `payable`.
    A field a human can set to "paid" without money arriving is an invitation.
    """

    UNPAID = 'unpaid', _('Unpaid · বকেয়া')
    PARTIAL = 'partial', _('Partly paid · আংশিক পরিশোধিত')
    PAID = 'paid', _('Paid · পরিশোধিত')
    OVERDUE = 'overdue', _('Overdue · মেয়াদোত্তীর্ণ')
    WAIVED = 'waived', _('Waived · মওকুফ')


#: Statuses that still owe money. The nightly fine job and the dues report both
#: read this, so "which invoices are outstanding" has one definition.
OUTSTANDING_STATUSES = (FeeStatus.UNPAID, FeeStatus.PARTIAL, FeeStatus.OVERDUE)


class GeneratedBy(models.TextChoices):
    SYSTEM = 'system', _('System · স্বয়ংক্রিয়')
    MANUAL = 'manual', _('Manual · হাতে তৈরি')


class PaymentMethod(models.TextChoices):
    """The eight ways money actually arrives at a Bangladeshi institution.

    The mobile wallets are separate choices rather than one `mobile` value
    because reconciliation is per wallet: a bKash statement and a Nagad
    statement are two different documents that have to tie out separately.
    """

    CASH = 'cash', _('Cash · নগদ টাকা')
    BKASH = 'bkash', _('bKash · বিকাশ')
    NAGAD = 'nagad', _('Nagad · নগদ')
    ROCKET = 'rocket', _('Rocket · রকেট')
    BANK = 'bank', _('Bank · ব্যাংক')
    CHEQUE = 'cheque', _('Cheque · চেক')
    CARD = 'card', _('Card · কার্ড')
    ONLINE = 'online', _('Online · অনলাইন')


def default_applies_to():
    """Applies to everyone, until the institution narrows it.

    A callable rather than a literal: a mutable default is shared by every
    instance Django builds, so one branch editing its stream list would edit
    every branch's.

    The shape is fixed and small on purpose — `generate_monthly_fees()` is the
    only reader, and a free-form JSON blob nobody can enumerate is a filter
    nobody can debug:

        {"streams": [<stream id>, …],   empty ⇒ every stream
         "hostel_only": false,          true ⇒ only Enrolment.is_hostel
         "transport_only": false}       true ⇒ only Enrolment.is_transport
    """
    return {'streams': [], 'hostel_only': False, 'transport_only': False}


#: `applies_to` for the seeded codes that are not universal (docs/03 §7 notes:
#: "charged only to students marked as using transport", "only to residential
#: students"). It lives here rather than in `branches.seed_data` because it is a
#: *fees* concept — `branches` must not learn what an `applies_to` is — and
#: because the seed rows are shared data this app only reads (CLAUDE.md §2).
SEEDED_APPLIES_TO = {
    'TRN': {'streams': [], 'hostel_only': False, 'transport_only': True},
    'HOS': {'streams': [], 'hostel_only': True, 'transport_only': False},
    # Food is billed to residents, separately from the hostel seat where an
    # institution keeps the two apart (docs/03 §7).
    'FOD': {'streams': [], 'hostel_only': True, 'transport_only': False},
}


class FeeCategory(BranchScopedModel):
    """A head of charge. Seeded per branch, extendable by the institution.

    Seeded rows carry `is_system=True` and **may be deactivated but never
    deleted**: a category an invoice points at is `PROTECT`ed anyway, and
    pretending otherwise would let an accountant orphan last year's invoices.
    """

    code = models.CharField(_('code · কোড'), max_length=20)
    name = models.CharField(_('name'), max_length=80)
    name_bn = models.CharField(_('নাম'), max_length=80, blank=True)

    # The brief's "proper note": the sentence the accountant reads when choosing
    # a head, which is what stops Book Fee and Other Fee being used
    # interchangeably (docs/03 §7).
    note = models.TextField(_('note · নোট'), blank=True)
    note_bn = models.TextField(_('নোট'), blank=True)

    recurrence = models.CharField(
        _('recurrence · পুনরাবৃত্তি'), max_length=20,
        choices=Recurrence.choices, default=Recurrence.CUSTOM,
    )
    # The price of this head, for the institution, until FeeStructure
    # (V2) allows a different one per class. Nullable and NOT defaulted to
    # zero on purpose: `None` means "nobody has set this yet" and callers
    # refuse to raise the invoice, where 0 would quietly produce a ৳0 bill
    # that every screen renders as already paid.
    default_amount = models.DecimalField(
        _('default amount · নির্ধারিত পরিমাণ'),
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    is_refundable = models.BooleanField(_('refundable · ফেরতযোগ্য'), default=False)
    is_mandatory = models.BooleanField(_('mandatory · আবশ্যিক'), default=False)

    applies_to = models.JSONField(
        _('applies to · প্রযোজ্য'), default=default_applies_to, blank=True,
    )

    is_system = models.BooleanField(_('seeded · পূর্বনির্ধারিত'), default=False)
    display_order = models.PositiveIntegerField(_('order · ক্রম'), default=0)
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('fee category · ফি খাত')
        verbose_name_plural = _('fee categories · ফি খাতসমূহ')
        ordering = ['branch', 'display_order', 'name']
        constraints = [
            # The seeding loop matches on (branch, code) — this is the
            # constraint that makes a second `seed_categories` run a no-op
            # rather than a duplicate set of eleven heads.
            models.UniqueConstraint(
                fields=['branch', 'code'], name='feecategory_unique_code_per_branch',
            ),
        ]

    def __str__(self):
        return f'{self.code} · {self.name}'

    def save(self, *args, **kwargs):
        # Upper-cased for the reason Branch.code is: `code` is the join between
        # an institution's own label and the canonical set in docs/03 §7, and
        # 'mon' must not become a twelfth category next to 'MON'.
        self.code = (self.code or '').strip().upper()
        return super().save(*args, **kwargs)


class Fee(BranchScopedModel):
    """One invoice — what a single student owes under one head, once.

    `payable` and `paid_amount` are **stored**, not computed on read, and
    docs/03 §7 says so deliberately: the dues report filters and sorts on the
    balance across every invoice in the institution, and a property cannot be a
    WHERE clause. `services.recalculate_fee()` is the only writer of both, and
    of `status`.

    **`period`** is `'2026-03'` for a monthly charge and blank otherwise. It is
    part of the uniqueness key, so for a `custom` category charged more than
    once in a session (Book Fee, Other Fee) the caller must pass something that
    distinguishes the two — see the constraint's comment below.
    """

    # PROTECT on all four: an invoice is a financial record, and deleting the
    # student, the class or the head it points at must fail loudly rather than
    # take the money history with it (CLAUDE.md §4.2).
    student = models.ForeignKey(
        'students.Student',
        verbose_name=_('student · শিক্ষার্থী'),
        on_delete=models.PROTECT,
        related_name='fees',
    )
    # Nullable: an admission fee raised before the enrolment exists, and a
    # manual invoice for a student between sessions, both have no enrolment.
    enrolment = models.ForeignKey(
        'academics.Enrolment',
        verbose_name=_('enrolment · ভর্তি'),
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='fees',
    )
    category = models.ForeignKey(
        FeeCategory,
        verbose_name=_('category · খাত'),
        on_delete=models.PROTECT,
        related_name='fees',
    )
    session = models.ForeignKey(
        'branches.Session',
        verbose_name=_('session · শিক্ষাবর্ষ'),
        on_delete=models.PROTECT,
        related_name='fees',
    )

    period = models.CharField(
        _('period · মাস'), max_length=7, blank=True, default='',
        help_text='YYYY-MM for a monthly charge; blank otherwise.',
    )
    invoice_no = models.CharField(_('invoice no · বিল নম্বর'), max_length=30)

    amount = models.DecimalField(_('amount · পরিমাণ'), default=ZERO, **MONEY)
    discount = models.DecimalField(_('discount · ছাড়'), default=ZERO, **MONEY)
    fine = models.DecimalField(_('fine · জরিমানা'), default=ZERO, **MONEY)
    # amount - discount + fine. Recomputed on every change to any of the three.
    payable = models.DecimalField(_('payable · প্রদেয়'), default=ZERO, **MONEY)
    # Sum of this invoice's non-reversed payments. Maintained on payment save.
    paid_amount = models.DecimalField(_('paid · পরিশোধিত'), default=ZERO, **MONEY)

    due_date = models.DateField(_('due date · শেষ তারিখ'))

    status = models.CharField(
        _('status · অবস্থা'), max_length=20,
        choices=FeeStatus.choices, default=FeeStatus.UNPAID,
        help_text='Derived. Never written from a request body.',
    )

    # SET_NULL: an audit reference. The staff member who approved a waiver may
    # leave; the waiver stays and the reason stays with it.
    waived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('waived by · মওকুফকারী'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    waived_at = models.DateTimeField(_('waived at · মওকুফের সময়'), null=True, blank=True)
    waive_reason = models.TextField(_('waive reason · মওকুফের কারণ'), blank=True)

    generated_by = models.CharField(
        _('raised by · উৎস'), max_length=10,
        choices=GeneratedBy.choices, default=GeneratedBy.MANUAL,
    )
    note = models.TextField(_('note · মন্তব্য'), blank=True)

    # Soft delete only (CLAUDE.md §4.2). An invoice with a receipt against it is
    # an accounting record; it is deactivated, never removed.
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('fee · ফি')
        verbose_name_plural = _('fees · ফিসমূহ')
        ordering = ['branch', '-due_date', 'student', 'category']
        constraints = [
            # ── The one that matters ─────────────────────────────────────────
            # This single line is what makes `generate_monthly_fees()` safe to
            # run twice (docs/06 #9). Idempotency is enforced by the DATABASE,
            # not by application code: a retried Celery task, a beat that fired
            # on two workers, a clerk clicking the manual trigger again — all of
            # them hit this and write nothing.
            #
            # Note what it means for a `custom` category with a blank `period`:
            # Postgres treats '' as a value, so a student can hold only ONE Book
            # Fee per session unless the caller distinguishes the invoices by
            # `period`. That is the documented behaviour of the key docs/03 §7
            # specifies, and the reason `raise_fee()` takes `period` explicitly.
            models.UniqueConstraint(
                fields=['branch', 'student', 'category', 'period', 'session'],
                name='fee_unique_per_student_category_period',
            ),
            # Printed on a slip the guardian keeps.
            models.UniqueConstraint(
                fields=['branch', 'invoice_no'], name='fee_unique_invoice_no',
            ),
            # Money is never negative on an invoice. A refund is a separate
            # record, not a negative charge (V2 — `is_refundable` is the flag
            # that says which categories will ever get one).
            models.CheckConstraint(
                condition=(
                    models.Q(amount__gte=0) & models.Q(discount__gte=0)
                    & models.Q(fine__gte=0) & models.Q(paid_amount__gte=0)
                ),
                name='fee_amounts_non_negative',
            ),
            # A discount larger than the charge is a typo that turns into a
            # negative payable and a credit nobody granted.
            models.CheckConstraint(
                condition=models.Q(discount__lte=models.F('amount')),
                name='fee_discount_within_amount',
            ),
        ]
        indexes = [
            # The dues report: "who owes what, oldest first" (docs/03 §7).
            models.Index(fields=['branch', 'status', 'due_date'],
                         name='fee_branch_status_due_idx'),
            # One student's fee history, which is the fee-counter screen.
            models.Index(fields=['student', 'session'], name='fee_student_session_idx'),
            models.Index(fields=['branch', 'period'], name='fee_branch_period_idx'),
        ]

    def __str__(self):
        return f'{self.invoice_no} · {self.category_id and self.category.code or ""}'

    @property
    def balance(self):
        """What is still owed. Decimal, like everything else in this file."""
        return (self.payable or ZERO) - (self.paid_amount or ZERO)

    @property
    def computed_payable(self):
        """`amount - discount + fine` — the definition, in one place."""
        return (self.amount or ZERO) - (self.discount or ZERO) + (self.fine or ZERO)


class Payment(BranchScopedModel):
    """A receipt. Quoted out loud at the counter, so `receipt_no` is gapless.

    **A wrong receipt is reversed, never deleted** (docs/01 §9, docs/06 #8).
    Deleting one destroys an accounting record and silently un-posts the income
    row it created; `services.reverse_payment()` is the only correct answer, and
    there is no `destroy` route on the API.
    """

    fee = models.ForeignKey(
        Fee,
        verbose_name=_('fee · ফি'),
        on_delete=models.PROTECT,
        related_name='payments',
    )
    # Denormalised from `fee.student` on purpose: "every receipt this student
    # holds" is the counter's most common lookup and the one a guardian asks
    # for, and routing it through the invoice makes it a join on every read.
    student = models.ForeignKey(
        'students.Student',
        verbose_name=_('student · শিক্ষার্থী'),
        on_delete=models.PROTECT,
        related_name='payments',
    )

    receipt_no = models.CharField(_('receipt no · রসিদ নম্বর'), max_length=30)
    amount = models.DecimalField(_('amount · পরিমাণ'), **MONEY)
    method = models.CharField(
        _('method · মাধ্যম'), max_length=20,
        choices=PaymentMethod.choices, default=PaymentMethod.CASH,
    )
    transaction_id = models.CharField(
        _('transaction id · লেনদেন আইডি'), max_length=80, blank=True, default='',
    )
    paid_at = models.DateTimeField(_('paid at · আদায়ের সময়'))

    # SET_NULL: an audit reference (CLAUDE.md §4.2). A cashier who leaves must
    # not take the receipts they issued with them.
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('collected by · আদায়কারী'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    # The auto-posted income row (docs/02 §4.6). Written by `collect_fee()` in
    # the same transaction as this row, so the fee ledger and the accounts can
    # never disagree — there is only one entry, and nobody typed the second.
    #
    # PROTECT: deleting the income row would leave a receipt claiming to have
    # posted income that is not in the books.
    income = models.ForeignKey(
        'finance.Income',
        verbose_name=_('income row · আয় এন্ট্রি'),
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='+',
    )

    note = models.TextField(_('note · মন্তব্য'), blank=True)

    is_reversed = models.BooleanField(_('reversed · বাতিল'), default=False)
    reversed_at = models.DateTimeField(_('reversed at · বাতিলের সময়'), null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('reversed by · বাতিলকারী'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    reverse_reason = models.TextField(_('reversal reason · বাতিলের কারণ'), blank=True)

    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        verbose_name = _('payment · আদায়')
        verbose_name_plural = _('payments · আদায়সমূহ')
        ordering = ['branch', '-paid_at', '-id']
        constraints = [
            # Gapless AND unique. `core.services.next_number` provides the first
            # under a row lock; this provides the second, because a counter that
            # was somehow reset must not be able to print 412 twice.
            models.UniqueConstraint(
                fields=['branch', 'receipt_no'], name='payment_unique_receipt_no',
            ),
            # docs/03 §7: "unique per method when present". Two receipts quoting
            # the same bKash TrxID is either a double-entry or a fraud, and both
            # are worth failing on. Conditional, because blank is the normal
            # case for cash.
            models.UniqueConstraint(
                fields=['branch', 'method', 'transaction_id'],
                condition=~models.Q(transaction_id=''),
                name='payment_unique_txn_per_method',
            ),
            # A zero receipt is not a receipt, and a negative one is a refund
            # pretending to be a collection.
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name='payment_amount_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'paid_at'], name='payment_branch_paid_idx'),
            models.Index(fields=['student', 'paid_at'], name='payment_student_paid_idx'),
        ]

    def __str__(self):
        return f'{self.receipt_no} · {self.amount}'
