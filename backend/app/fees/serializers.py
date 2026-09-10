"""Shape and validation for the fees API (CLAUDE.md §4.3 — no writes here).

Three things this file refuses to expose, each for the same reason:

* **`branch`** — stamped server-side from `request.branch`; a `branch` in a POST
  body is ignored (CLAUDE.md §1).
* **`status`, `payable`, `paid_amount`** — derived. There is no request body
  that can mark an invoice paid without money arriving (docs/06 #8).
* **`invoice_no`, `receipt_no`** — issued from the per-branch counter inside the
  service's transaction, never chosen by a client (CLAUDE.md §4.4).

`DecimalField` on every amount, with the same 12/2 the model uses, so a JSON
number never becomes a float on the way in.
"""

from decimal import Decimal

from rest_framework import serializers

from .models import (Fee, FeeCategory, FeeStatus, Payment, PaymentMethod,
                     Recurrence)

MONEY = {'max_digits': 12, 'decimal_places': 2}


class FeeCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeCategory
        fields = [
            'id', 'code', 'name', 'name_bn', 'note', 'note_bn', 'recurrence',
            # default_amount is what an invoice for this head costs. It was on
            # the model but missing here, so a PATCH carrying it was silently
            # dropped and every head stayed unpriced — and an unpriced head
            # cannot raise an invoice at all.
            'default_amount',
            'is_refundable', 'is_mandatory', 'applies_to', 'is_system',
            'display_order', 'is_active', 'created_at', 'updated_at',
        ]
        # `is_system` is read-only: a seeded head must not be able to make
        # itself deletable by flipping a boolean through the API.
        read_only_fields = ['id', 'is_system', 'created_at', 'updated_at']

    def validate_code(self, value):
        return (value or '').strip().upper()


class FeeSerializer(serializers.ModelSerializer):
    """One invoice. `amount`, `discount` and `due_date` are the writable half."""

    student_name = serializers.CharField(source='student.name', read_only=True)
    student_admission_no = serializers.CharField(
        source='enrolment.admission_number', read_only=True, default='',
    )
    category_code = serializers.CharField(source='category.code', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    # A `SerializerMethodField` rather than the model property directly, so the
    # decimal reaches the SPA as a string and not as a float in JSON.
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Fee
        fields = [
            'id', 'student', 'student_name', 'student_admission_no', 'enrolment',
            'category', 'category_code', 'category_name', 'session', 'period',
            'invoice_no', 'amount', 'discount', 'fine', 'payable', 'paid_amount',
            'balance', 'due_date', 'status', 'waived_by', 'waived_at',
            'waive_reason', 'generated_by', 'note', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'invoice_no', 'fine', 'payable', 'paid_amount', 'balance',
            'status', 'waived_by', 'waived_at', 'waive_reason', 'generated_by',
            'created_at', 'updated_at',
        ]

    def get_balance(self, fee):
        return str(fee.balance)

    def validate(self, attrs):
        amount = attrs.get('amount', getattr(self.instance, 'amount', None))
        discount = attrs.get('discount', getattr(self.instance, 'discount', None))
        if amount is not None and discount is not None and discount > amount:
            raise serializers.ValidationError({
                'discount': 'The discount cannot be more than the fee · '
                            'ছাড় ফি-এর চেয়ে বেশি হতে পারে না।',
            })
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    """A receipt. Entirely read-only — it is written by `collect_fee()` only."""

    student_name = serializers.CharField(source='student.name', read_only=True)
    invoice_no = serializers.CharField(source='fee.invoice_no', read_only=True)
    category_name = serializers.CharField(source='fee.category.name', read_only=True)
    collected_by_name = serializers.CharField(
        source='collected_by.name', read_only=True, default='',
    )

    class Meta:
        model = Payment
        fields = [
            'id', 'fee', 'invoice_no', 'student', 'student_name', 'category_name',
            'receipt_no', 'amount', 'method', 'transaction_id', 'paid_at',
            'collected_by', 'collected_by_name', 'income', 'note',
            'is_reversed', 'reversed_at', 'reversed_by', 'reverse_reason',
            'created_at',
        ]
        # Every field. A receipt is not editable: a wrong one is reversed and a
        # new one issued, which is the only version of this that leaves an
        # audit trail (docs/06 #8).
        read_only_fields = fields


class CollectSerializer(serializers.Serializer):
    """The body of `POST /api/fees/<id>/collect/`.

    A plain Serializer, not a ModelSerializer: the request is an *instruction*,
    not a Payment. The receipt number, the branch, the student and the income
    row are all decided by the service, and a ModelSerializer would invite a
    client to send them.
    """

    # A Decimal, not 0 - DRF compares against it directly and an int min_value
    # warns and mixes types on a money field.
    amount = serializers.DecimalField(**MONEY, min_value=Decimal('0.01'))
    method = serializers.ChoiceField(
        choices=PaymentMethod.choices, default=PaymentMethod.CASH,
    )
    transaction_id = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default='',
    )
    paid_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        method = attrs.get('method')
        txn = (attrs.get('transaction_id') or '').strip()
        # A mobile-wallet collection with no transaction id cannot be
        # reconciled against the wallet's statement, which is the only reason
        # the id exists. Cash and cheque legitimately have none.
        if method in (PaymentMethod.BKASH, PaymentMethod.NAGAD,
                      PaymentMethod.ROCKET) and not txn:
            raise serializers.ValidationError({
                'transaction_id': 'A mobile payment needs its transaction id · '
                                  'মোবাইল পেমেন্টের লেনদেন আইডি দিন।',
            })
        attrs['transaction_id'] = txn
        return attrs


class ReasonSerializer(serializers.Serializer):
    """A reversal or a waiver. The reason is mandatory, and that is the point.

    Both actions rewrite what the institution's books say happened. An
    unexplained one is indistinguishable from a mistake or a theft six months
    later, so there is no path through the API that performs either silently.
    """

    reason = serializers.CharField(max_length=500, allow_blank=False)


class FeeSummarySerializer(serializers.Serializer):
    """Read-only totals for the dues screen. Strings, so nothing becomes a float."""

    status = serializers.CharField()
    count = serializers.IntegerField()
    payable = serializers.CharField()
    paid = serializers.CharField()
    balance = serializers.CharField()


__all__ = [
    'CollectSerializer', 'FeeCategorySerializer', 'FeeSerializer',
    'FeeStatus', 'FeeSummarySerializer', 'PaymentSerializer',
    'ReasonSerializer', 'Recurrence',
]
