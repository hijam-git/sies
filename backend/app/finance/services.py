"""Ledger writes — all of them in transactions (CLAUDE.md §4.3).

`post_payment_income()` is the one that matters. It is called by
`fees.services.collect_fee()` **inside that function's transaction**, which is
what makes the receipt and the income row a single fact rather than two records
that have to be kept in step (docs/02 §4.6).

Voucher numbers come from `core.services.next_number` — the only number
generator in this project (CLAUDE.md §4.4). There is no second one here.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounts.models import ActivityAction
from accounts.services import CodedError, log_activity
from core.services import format_number, next_number

from .models import EntrySource, Expense, ExpenseCategory, Income, IncomeCategory

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Voucher numbers
#
# Two counters, not one. Income and Expense are separate books and an
# accountant reads a voucher number to mean which book it came from; a shared
# sequence would interleave them and make "receipt voucher 41" ambiguous.
#
# `kind` is a plain string rather than a `NumberSequence.Kind` member: adding
# members to that enum means editing `core/models.py` and a migration for a
# choices change that constrains nothing at the database level. The counter row
# is keyed on the string, so these two values ARE the kinds — do not rename
# them, or a branch's counter restarts at 1 and re-issues printed numbers.
# ─────────────────────────────────────────────────────────────────────────────

INCOME_VOUCHER_KIND = 'income_voucher'
EXPENSE_VOUCHER_KIND = 'expense_voucher'

#: RV = receipt voucher (money in), PV = payment voucher (money out). The
#: conventional Bangladeshi bookkeeping prefixes, so a printed voucher reads the
#: way the accountant's previous ledger did.
INCOME_VOUCHER_PREFIX = 'RV'
EXPENSE_VOUCHER_PREFIX = 'PV'


def next_income_voucher_no(branch):
    """`RV-DHK-000123`. Gapless within the branch — call inside a transaction."""
    _n, padded = next_number(branch=branch, kind=INCOME_VOUCHER_KIND, width=6)
    return format_number(prefix=INCOME_VOUCHER_PREFIX, branch=branch, number_padded=padded)


def next_expense_voucher_no(branch):
    """`PV-DHK-000123`. Gapless within the branch — call inside a transaction."""
    _n, padded = next_number(branch=branch, kind=EXPENSE_VOUCHER_KIND, width=6)
    return format_number(prefix=EXPENSE_VOUCHER_PREFIX, branch=branch, number_padded=padded)


def _money(value, field):
    """Decimal, or a 400 that names the field. Never a float (CLAUDE.md §1).

    `Decimal(str(value))` rather than `Decimal(value)`: a float that reached
    here — from JSON, from a JSON settings blob — converts exactly to its binary
    value, so 0.1 becomes 0.1000000000000000055511151231257827. Going through
    `str` gives the number the caller meant.
    """
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            raise CodedError(f'{field} must be a number.', 'invalid_amount')
    return amount.quantize(Decimal('0.01'))


# ─────────────────────────────────────────────────────────────────────────────
# Manual entry
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def record_income(*, branch, category, amount, date=None, method=None,
                  reference='', description='', session=None, attachment=None,
                  source=EntrySource.MANUAL, payment=None, recorded_by=None,
                  is_approved=False, request=None):
    """Write one income row. Donations, rent received, anything not a receipt.

    The voucher number is allocated inside this transaction, so a failed insert
    takes the reserved number with it and the series stays gapless
    (`core.services.next_number`).
    """
    amount = _money(amount, 'amount')
    if amount <= 0:
        raise CodedError('An income entry must be more than zero · '
                         'আয়ের পরিমাণ শূন্যের বেশি হতে হবে।', 'invalid_amount')

    entry = Income.objects.create(
        branch=branch,
        category=category,
        voucher_no=next_income_voucher_no(branch),
        amount=amount,
        date=date or timezone.localdate(),
        method=method or 'cash',
        reference=reference or '',
        description=description or '',
        attachment=attachment,
        session=session,
        source=source,
        payment=payment,
        recorded_by=_actor(recorded_by),
        is_approved=is_approved,
        created_by=_actor(recorded_by),
    )

    log_activity(
        action=ActivityAction.CREATE,
        user=recorded_by, request=request, branch=branch, obj=entry,
        model='Income',
        summary=f'Income {entry.voucher_no} · {entry.amount} ({entry.category.name})',
        summary_bn=f'আয় {entry.voucher_no} · {entry.amount}',
        # atomic=True: this is money. An entry whose audit row could not be
        # written is an entry with no record of who made it, and rolling both
        # back is the right answer (accounts.services.log_activity).
        atomic=True,
    )
    return entry


@transaction.atomic
def record_expense(*, branch, category, amount, date=None, method=None,
                   reference='', description='', session=None, attachment=None,
                   source=EntrySource.MANUAL, recorded_by=None,
                   is_approved=False, request=None):
    """Write one expense row. Salary in V1 is one of these (docs/05 §5.4)."""
    amount = _money(amount, 'amount')
    if amount <= 0:
        raise CodedError('An expense entry must be more than zero · '
                         'ব্যয়ের পরিমাণ শূন্যের বেশি হতে হবে।', 'invalid_amount')

    entry = Expense.objects.create(
        branch=branch,
        category=category,
        voucher_no=next_expense_voucher_no(branch),
        amount=amount,
        date=date or timezone.localdate(),
        method=method or 'cash',
        reference=reference or '',
        description=description or '',
        attachment=attachment,
        session=session,
        source=source,
        recorded_by=_actor(recorded_by),
        is_approved=is_approved,
        created_by=_actor(recorded_by),
    )

    log_activity(
        action=ActivityAction.CREATE,
        user=recorded_by, request=request, branch=branch, obj=entry,
        model='Expense',
        summary=f'Expense {entry.voucher_no} · {entry.amount} ({entry.category.name})',
        summary_bn=f'ব্যয় {entry.voucher_no} · {entry.amount}',
        atomic=True,
    )
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# Auto-posting — the cross-module write (docs/06 #10)
# ─────────────────────────────────────────────────────────────────────────────

#: Where a collection lands when its fee category has no mapped income head.
#: Seeded by `branches.seeding`; an unmapped receipt in a null head would be
#: money the P&L cannot see.
FALLBACK_INCOME_CODE = 'INC-OTH'


def income_category_for(payment):
    """The income head this receipt posts to (docs/03 §8).

    Mapped by `IncomeCategory.fee_category`, which is exactly why that link is
    seeded. Falls back to the catch-all head rather than raising: refusing a
    guardian's payment because an income head was deactivated would be the
    system protecting its own bookkeeping at the counter's expense.
    """
    branch_id = payment.branch_id
    category_id = payment.fee.category_id

    head = IncomeCategory.objects.filter(
        branch_id=branch_id, fee_category_id=category_id, is_active=True,
    ).first()
    if head is not None:
        return head

    head = IncomeCategory.objects.filter(
        branch_id=branch_id, code=FALLBACK_INCOME_CODE,
    ).first()
    if head is not None:
        logger.warning(
            'No income head mapped to fee category %s in branch %s; posting to %s',
            category_id, branch_id, FALLBACK_INCOME_CODE,
        )
        return head

    # Nothing at all: the branch was created without seeding, which is a setup
    # failure and not something to paper over by posting into a null head.
    raise CodedError(
        'This institution has no income categories. Run seed_categories · '
        'এই প্রতিষ্ঠানের কোনো আয়ের খাত নেই।',
        'income_head_missing',
    )


def post_payment_income(payment):
    """Write the Income row for a receipt. **Called inside `collect_fee()`.**

    Not `@transaction.atomic` of its own, and that is the point: it joins the
    caller's transaction, so the receipt and the income row commit together or
    neither exists (docs/06 #10). Wrapping it in its own atomic block would make
    it a savepoint that could commit while the payment rolled back — the exact
    disagreement between the fee ledger and the accounts this design removes.
    """
    fee = payment.fee
    head = income_category_for(payment)

    return Income.objects.create(
        branch_id=payment.branch_id,
        category=head,
        voucher_no=next_income_voucher_no(payment.branch),
        amount=payment.amount,
        date=timezone.localtime(payment.paid_at).date(),
        method=payment.method,
        # The receipt number, so a row in the ledger can be traced to the paper
        # the guardian is holding without a join.
        reference=payment.transaction_id or payment.receipt_no,
        description=(f'{fee.category.name} · {payment.student.name} '
                     f'· receipt {payment.receipt_no}'),
        session=fee.session,
        source=EntrySource.FEE_PAYMENT,
        payment=payment,
        recorded_by=payment.collected_by,
        created_by=payment.collected_by,
    )


@transaction.atomic
def reverse_income(entry, *, reason, actor=None, request=None):
    """Mark a ledger row reversed. Never delete one.

    Called by `fees.services.reverse_payment()` for the auto-posted row. The row
    stays in the table with its reason attached, and every total excludes
    `is_reversed` — a deleted row would make last month's closed P&L change
    retrospectively with nothing to say why.
    """
    if entry.is_reversed:
        raise CodedError('This entry is already reversed · '
                         'এই এন্ট্রি ইতিমধ্যে বাতিল করা হয়েছে।', 'already_reversed')
    if not reason:
        raise CodedError('Give a reason for the reversal · '
                         'বাতিলের কারণ লিখুন।', 'reason_required')

    entry.is_reversed = True
    entry.reversed_at = timezone.now()
    entry.reversed_by = _actor(actor)
    entry.reverse_reason = reason
    entry.save(update_fields=['is_reversed', 'reversed_at', 'reversed_by',
                              'reverse_reason', 'updated_at'])

    log_activity(
        action=ActivityAction.UPDATE,
        user=actor, request=request, branch=entry.branch, obj=entry,
        model=entry.__class__.__name__,
        summary=f'Reversed {entry.voucher_no}: {reason}',
        summary_bn=f'{entry.voucher_no} বাতিল করা হয়েছে',
        atomic=True,
    )
    return entry


def _actor(user):
    """A saveable user, or None. AnonymousUser has no pk and cannot be an FK."""
    return user if getattr(user, 'is_authenticated', False) else None


__all__ = [
    'ExpenseCategory', 'IncomeCategory',
    'income_category_for', 'next_expense_voucher_no', 'next_income_voucher_no',
    'post_payment_income', 'record_expense', 'record_income', 'reverse_income',
]
