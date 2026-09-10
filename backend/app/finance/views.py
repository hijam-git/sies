"""The ledger API (CLAUDE.md §5). Wrong-branch rows are 404, not 403.

One rule is enforced here and nowhere else in the HTTP layer: **a non-manual
entry is read-only**. A row with `source='fee_payment'` was written by
`fees.services.collect_fee()` in the receipt's transaction; letting anyone PATCH
its amount would break the property that makes the fee ledger and the accounts
unable to disagree (docs/02 §4.6). The refusal is a 400 naming the reason rather
than a silent no-op, because an accountant who cannot edit a row needs to know
that the *receipt* is what to correct — by reversing it.
"""

from decimal import Decimal

from django.db.models import Count, DecimalField, Sum
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import HasResourcePermission
from accounts.services import ActivityLogMixin
from core.viewsets import BranchScopedViewSet

from .models import (EntrySource, Expense, ExpenseCategory, Income,
                     IncomeCategory)
from .serializers import (ExpenseCategorySerializer, ExpenseSerializer,
                          IncomeCategorySerializer, IncomeSerializer)
from .services import reverse_income

MONEY_FIELD = DecimalField(max_digits=12, decimal_places=2)


class LedgerCategoryViewSet(ActivityLogMixin, BranchScopedViewSet):
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'finance'
    filterset_fields = ['is_active', 'is_system']
    search_fields = ['code', 'name', 'name_bn']
    ordering_fields = ['display_order', 'name', 'code']

    def perform_destroy(self, instance):
        if instance.is_system:
            raise ValidationError({
                'detail': 'A seeded category can be deactivated but not deleted · '
                          'পূর্বনির্ধারিত খাত মুছে ফেলা যাবে না, নিষ্ক্রিয় করুন।',
            })
        super().perform_destroy(instance)


class IncomeCategoryViewSet(LedgerCategoryViewSet):
    queryset = IncomeCategory.objects.select_related('branch', 'fee_category').all()
    serializer_class = IncomeCategorySerializer
    activity_model = 'IncomeCategory'


class ExpenseCategoryViewSet(LedgerCategoryViewSet):
    queryset = ExpenseCategory.objects.select_related('branch').all()
    serializer_class = ExpenseCategorySerializer
    activity_model = 'ExpenseCategory'


class LedgerEntryViewSet(ActivityLogMixin, BranchScopedViewSet):
    """Shared behaviour for Income and Expense — including the read-only rule."""

    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'finance'
    permission_action_map = {'summary': 'view', 'reverse': 'update'}
    filterset_fields = ['category', 'session', 'method', 'source',
                        'is_approved', 'is_reversed', 'is_active', 'date']
    search_fields = ['voucher_no', 'reference', 'description']
    ordering_fields = ['date', 'amount', 'voucher_no', 'created_at']

    def _refuse_if_posted(self, instance):
        """Auto-posted rows belong to the document they came from."""
        if instance.source != EntrySource.MANUAL:
            raise ValidationError({
                'source': (
                    'This entry was posted automatically and cannot be edited '
                    'here. Reverse the receipt or payslip instead · '
                    'এই এন্ট্রি স্বয়ংক্রিয়ভাবে তৈরি; সংশোধন করতে সংশ্লিষ্ট রসিদ বাতিল করুন।'
                ),
            })

    def perform_update(self, serializer):
        self._refuse_if_posted(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._refuse_if_posted(instance)
        # Soft delete. A ledger row that has been in a month's P&L is not
        # removed from the table (CLAUDE.md §4.2).
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])

    def perform_create(self, serializer):
        """Manual entry only. The voucher number comes from the branch counter.

        `source` is not accepted from the body (the serializer marks it
        read-only), so every row this endpoint writes is `manual` by
        construction — an auto-posted row can only come from a service.
        """
        from django.db import transaction

        from core.middleware import ALL_BRANCHES, get_branch

        branch = get_branch(self.request)
        if branch is None or branch == ALL_BRANCHES:
            raise ValidationError({
                'branch': ('Choose an institution before creating this. '
                           'Add ?branch=<id> to the request.'),
            })
        if isinstance(branch, str):
            from branches.models import Branch

            branch = Branch.objects.filter(pk=branch).first()
            if branch is None:
                raise ValidationError({'branch': 'No institution with that id.'})

        with transaction.atomic():
            serializer.save(
                branch=branch,
                voucher_no=self.next_voucher_no(branch),
                source=EntrySource.MANUAL,
                recorded_by=self.request.user,
                created_by=self.request.user,
            )

    def next_voucher_no(self, branch):
        raise NotImplementedError

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Totals over the current filters, excluding reversed rows.

        Reversed entries are excluded here and included in the list: a total
        that counted them would overstate the month, while a list that hid them
        would leave nobody able to see what was reversed and why.
        """
        queryset = self.filter_queryset(self.get_queryset()).filter(
            is_reversed=False, is_active=True,
        )
        rows = (
            queryset.values('category', 'category__name', 'category__code')
            .annotate(count=Count('id'),
                      total=Sum('amount', output_field=MONEY_FIELD))
            .order_by('category__code')
        )
        total = queryset.aggregate(
            total=Sum('amount', output_field=MONEY_FIELD))['total'] or Decimal('0.00')

        return Response({
            'total': str(total),
            'by_category': [
                {'category': row['category'],
                 'code': row['category__code'],
                 'name': row['category__name'],
                 'count': row['count'],
                 'total': str(row['total'] or Decimal('0.00'))}
                for row in rows
            ],
        })


class IncomeViewSet(LedgerEntryViewSet):
    queryset = Income.objects.select_related(
        'branch', 'category', 'session', 'recorded_by', 'payment',
    ).all()
    serializer_class = IncomeSerializer
    activity_model = 'Income'

    def next_voucher_no(self, branch):
        from .services import next_income_voucher_no

        return next_income_voucher_no(branch)

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """Reverse a manual income row (a returned donation, a mistaken entry).

        An auto-posted row is refused: reversing it means reversing the receipt
        it came from, at `POST /api/payments/<id>/reverse/`, which reverses both.
        """
        entry = self.get_object()
        self._refuse_if_posted(entry)

        reason = (request.data.get('reason') or '').strip()
        if not reason:
            raise ValidationError({'reason': 'Give a reason for the reversal.'})

        entry = reverse_income(entry, reason=reason, actor=request.user,
                               request=request)
        return Response(IncomeSerializer(entry).data, status=status.HTTP_200_OK)


class ExpenseViewSet(LedgerEntryViewSet):
    queryset = Expense.objects.select_related(
        'branch', 'category', 'session', 'recorded_by',
    ).all()
    serializer_class = ExpenseSerializer
    activity_model = 'Expense'

    def next_voucher_no(self, branch):
        from .services import next_expense_voucher_no

        return next_expense_voucher_no(branch)
