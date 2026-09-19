"""Shape and validation for the ledger API.

The important rule is negative: **`source`, `voucher_no` and `payment` are
read-only**. A client that could set `source='manual'` on an auto-posted row
could then edit it, and the fee ledger and the accounts would be able to
disagree — which is the one property docs/02 §4.6 buys by writing the income row
in the collection's transaction.
"""

from rest_framework import serializers

from core.serializers import BranchSafeSerializer

from .models import (Expense, ExpenseCategory, Income, IncomeCategory,
                     LedgerMethod)


class LedgerCategorySerializerMixin:
    def validate_code(self, value):
        return (value or '').strip().upper()


class IncomeCategorySerializer(LedgerCategorySerializerMixin,
                               BranchSafeSerializer):
    fee_category_code = serializers.CharField(
        source='fee_category.code', read_only=True, default='',
    )

    class Meta:
        model = IncomeCategory
        fields = ['id', 'code', 'name', 'name_bn', 'note', 'note_bn',
                  'fee_category', 'fee_category_code', 'is_system',
                  'display_order', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'is_system', 'created_at', 'updated_at']


class ExpenseCategorySerializer(LedgerCategorySerializerMixin,
                                BranchSafeSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ['id', 'code', 'name', 'name_bn', 'note', 'note_bn',
                  'is_system', 'display_order', 'is_active',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'is_system', 'created_at', 'updated_at']


class LedgerEntrySerializer(BranchSafeSerializer):
    """The fields Income and Expense share, and the ones neither may accept."""

    category_name = serializers.CharField(source='category.name', read_only=True)
    category_code = serializers.CharField(source='category.code', read_only=True)
    recorded_by_name = serializers.CharField(
        source='recorded_by.name', read_only=True, default='',
    )
    method = serializers.ChoiceField(choices=LedgerMethod.choices,
                                     default=LedgerMethod.CASH)

    class Meta:
        fields = [
            'id', 'category', 'category_code', 'category_name', 'voucher_no',
            'amount', 'date', 'method', 'reference', 'description',
            'attachment', 'session', 'source', 'recorded_by',
            'recorded_by_name', 'is_approved', 'approved_by', 'approved_at',
            'is_reversed', 'reversed_at', 'reversed_by', 'reverse_reason',
            'is_active', 'created_at', 'updated_at',
        ]
        # `is_approved` is read-only with the rest of the approval trio. It
        # was writable while `approved_by` and `approved_at` were not, so any
        # holder of `income.create` could post a voucher already approved, by
        # nobody, at no time — an approval step that recorded no approver is
        # worse than none, because the ledger claims one happened.
        read_only_fields = [
            'id', 'voucher_no', 'source', 'recorded_by', 'is_approved',
            'approved_by', 'approved_at', 'is_reversed', 'reversed_at',
            'reversed_by', 'reverse_reason', 'created_at', 'updated_at',
        ]


class IncomeSerializer(LedgerEntrySerializer):
    payment_receipt_no = serializers.CharField(
        source='payment.receipt_no', read_only=True, default='',
    )

    class Meta(LedgerEntrySerializer.Meta):
        model = Income
        fields = LedgerEntrySerializer.Meta.fields + ['payment', 'payment_receipt_no']
        # `payment` is read-only: the link is made by `post_payment_income()`
        # inside the collection's transaction. A client able to point an income
        # row at a receipt could post a second one against it.
        read_only_fields = LedgerEntrySerializer.Meta.read_only_fields + ['payment']


class ExpenseSerializer(LedgerEntrySerializer):
    class Meta(LedgerEntrySerializer.Meta):
        model = Expense


__all__ = ['ExpenseCategorySerializer', 'ExpenseSerializer',
           'IncomeCategorySerializer', 'IncomeSerializer']
