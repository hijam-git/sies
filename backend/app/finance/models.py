"""Income, expense and their heads — the institution's ledger.

Income and Expense are structurally the same shape (docs/02 §4.6), so they
share `LedgerEntry` and differ only in direction and in which category table
they point at. Two tables rather than one signed table because every report the
institution actually wants — this month's income, this month's expense, the
P&L — reads one of them, and a `direction` column would put a filter in front
of every one of those queries for no gain.

**`source` is the field that keeps the books honest.** A row with
`source='fee_payment'` was written by `fees.services.collect_fee()` in the same
transaction as the receipt; nobody typed it, and nobody may edit it. The API
refuses to update or delete any non-manual row (`views.py`), which is what makes
"the fee ledger and the accounts can never disagree" a property of the system
rather than a habit of the accountant.

Money is `Decimal` here too (CLAUDE.md §1) — see `fees.models` for why.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BranchScopedModel

MONEY = {'max_digits': 12, 'decimal_places': 2}


class EntrySource(models.TextChoices):
    """Who wrote this row, and therefore who may change it.

    `manual` is the only editable one. `fee_payment` rows belong to a receipt
    and `payroll` rows to a payslip; editing either would make the ledger
    disagree with the document it was posted from.
    """

    MANUAL = 'manual', _('Entered manually · হাতে লেখা')
    FEE_PAYMENT = 'fee_payment', _('Fee collection · ফি আদায়')
    PAYROLL = 'payroll', _('Payroll · বেতন')


class LedgerMethod(models.TextChoices):
    """Deliberately the same eight values as `fees.models.PaymentMethod`.

    docs/03 §8 lists five for the ledger and eight for a receipt. Posting a
    Rocket or card collection into a five-value column means mapping it to
    something it was not, and the first person to notice is whoever reconciles
    the Rocket statement. Keeping the sets identical means the auto-posted row
    carries the receipt's own method unchanged.
    """

    CASH = 'cash', _('Cash · নগদ টাকা')
    BKASH = 'bkash', _('bKash · বিকাশ')
    NAGAD = 'nagad', _('Nagad · নগদ')
    ROCKET = 'rocket', _('Rocket · রকেট')
    BANK = 'bank', _('Bank · ব্যাংক')
    CHEQUE = 'cheque', _('Cheque · চেক')
    CARD = 'card', _('Card · কার্ড')
    ONLINE = 'online', _('Online · অনলাইন')


class LedgerCategory(BranchScopedModel):
    """Shared shape for the two category tables. Seeded per branch."""

    code = models.CharField(_('code · কোড'), max_length=20)
    name = models.CharField(_('name'), max_length=80)
    name_bn = models.CharField(_('নাম'), max_length=80, blank=True)
    note = models.TextField(_('note · নোট'), blank=True)
    note_bn = models.TextField(_('নোট'), blank=True)
    is_system = models.BooleanField(_('seeded · পূর্বনির্ধারিত'), default=False)
    display_order = models.PositiveIntegerField(_('order · ক্রম'), default=0)
    is_active = models.BooleanField(_('active · সক্রিয়'), default=True)

    class Meta(BranchScopedModel.Meta):
        abstract = True
        ordering = ['branch', 'display_order', 'name']

    def __str__(self):
        return f'{self.code} · {self.name}'

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        return super().save(*args, **kwargs)


class IncomeCategory(LedgerCategory):
    """An income head. `fee_category` is what makes auto-posting possible.

    Without the link, a collection would have to guess its head or land in a
    null one, and an accountant would be re-classifying receipts by hand every
    month — which is exactly the manual step the auto-posted row exists to
    remove (docs/03 §8).

    SET_NULL rather than PROTECT: a fee category the institution deactivates and
    later removes must not lock the income head that holds years of history.
    Collections then fall back to the catch-all head instead of failing.
    """

    fee_category = models.ForeignKey(
        'fees.FeeCategory',
        verbose_name=_('fee category · ফি খাত'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='income_categories',
    )

    class Meta(LedgerCategory.Meta):
        verbose_name = _('income category · আয়ের খাত')
        verbose_name_plural = _('income categories · আয়ের খাতসমূহ')
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'code'], name='incomecategory_unique_code_per_branch',
            ),
            # One income head per fee category, or `post_payment_income()` has
            # to choose between two and the same fee lands in different heads on
            # different days.
            models.UniqueConstraint(
                fields=['branch', 'fee_category'],
                condition=models.Q(fee_category__isnull=False),
                name='incomecategory_one_head_per_fee_category',
            ),
        ]


class ExpenseCategory(LedgerCategory):
    class Meta(LedgerCategory.Meta):
        verbose_name = _('expense category · ব্যয়ের খাত')
        verbose_name_plural = _('expense categories · ব্যয়ের খাতসমূহ')
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'code'], name='expensecategory_unique_code_per_branch',
            ),
        ]


class LedgerEntry(BranchScopedModel):
    """The shared half of Income and Expense (docs/03 §8).

    `category` is declared on each concrete model rather than here: the two
    point at different tables, and an abstract FK cannot.
    """

    voucher_no = models.CharField(_('voucher no · ভাউচার নম্বর'), max_length=30)
    amount = models.DecimalField(_('amount · পরিমাণ'), **MONEY)
    date = models.DateField(_('date · তারিখ'))
    method = models.CharField(
        _('method · মাধ্যম'), max_length=20,
        choices=LedgerMethod.choices, default=LedgerMethod.CASH,
    )
    reference = models.CharField(
        _('reference · সূত্র'), max_length=120, blank=True, default='',
        help_text='Transaction id, cheque number, bill number.',
    )
    description = models.TextField(_('description · বিবরণ'), blank=True)
    attachment = models.FileField(
        _('attachment · সংযুক্তি'), upload_to='finance/vouchers/%Y/%m/',
        null=True, blank=True,
    )

    # PROTECT: the session is what a session-wise P&L groups by, and deleting it
    # would silently re-point a year of the ledger at nothing.
    session = models.ForeignKey(
        'branches.Session',
        verbose_name=_('session · শিক্ষাবর্ষ'),
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='%(class)s_entries',
    )

    source = models.CharField(
        _('source · উৎস'), max_length=20,
        choices=EntrySource.choices, default=EntrySource.MANUAL,
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('recorded by · লিপিবদ্ধকারী'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    is_approved = models.BooleanField(_('approved · অনুমোদিত'), default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('approved by · অনুমোদনকারী'),
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    approved_at = models.DateTimeField(_('approved at · অনুমোদনের সময়'), null=True, blank=True)

    # Reversal, mirroring Payment. A ledger row is never deleted — the reversed
    # row and its reason stay, and every total excludes `is_reversed`. docs/03
    # §8 does not list these four columns; they are here because docs/06 #8
    # requires a reversed receipt's income to be reversed too, and the
    # alternative (deleting the row) destroys the record the reversal is about.
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
        abstract = True
        ordering = ['branch', '-date', '-id']

    def __str__(self):
        return f'{self.voucher_no} · {self.amount}'


class Income(LedgerEntry):
    """Money in. Fee collections post here by themselves (docs/02 §4.6)."""

    category = models.ForeignKey(
        IncomeCategory,
        verbose_name=_('category · খাত'),
        on_delete=models.PROTECT,
        related_name='entries',
    )

    # The back-link to the receipt. Nullable because donations and other
    # non-fee income have no receipt behind them.
    #
    # PROTECT: the receipt is the document this row was posted from. Removing it
    # while the income stands would leave an entry nobody can trace to anything
    # — and `Payment` is never deleted anyway, only reversed.
    payment = models.ForeignKey(
        'fees.Payment',
        verbose_name=_('payment · আদায়'),
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='income_entries',
    )

    class Meta(LedgerEntry.Meta):
        verbose_name = _('income · আয়')
        verbose_name_plural = _('income · আয়সমূহ')
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'voucher_no'], name='income_unique_voucher_no',
            ),
            # Exactly one income row per receipt. This is the database half of
            # "a collection writes exactly one Income row": a retried collect
            # that somehow got past the transaction cannot double-post.
            models.UniqueConstraint(
                fields=['payment'], condition=models.Q(payment__isnull=False),
                name='income_one_per_payment',
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name='income_amount_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'date'], name='income_branch_date_idx'),
            models.Index(fields=['branch', 'category', 'date'],
                         name='income_branch_cat_date_idx'),
            models.Index(fields=['branch', 'source'], name='income_branch_source_idx'),
        ]


class Expense(LedgerEntry):
    """Money out. Salary is an ordinary expense row in V1 (docs/05 §5.4).

    `payslip` is V2 with the payroll module — there is no column for it here,
    because a nullable FK to a table that does not exist is a migration waiting
    to be edited rather than a design.
    """

    category = models.ForeignKey(
        ExpenseCategory,
        verbose_name=_('category · খাত'),
        on_delete=models.PROTECT,
        related_name='entries',
    )

    class Meta(LedgerEntry.Meta):
        verbose_name = _('expense · ব্যয়')
        verbose_name_plural = _('expenses · ব্যয়সমূহ')
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'voucher_no'], name='expense_unique_voucher_no',
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name='expense_amount_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['branch', 'date'], name='expense_branch_date_idx'),
            models.Index(fields=['branch', 'category', 'date'],
                         name='expense_branch_cat_date_idx'),
        ]
