"""The fees API (CLAUDE.md §5). Thin — every write goes through `services.py`.

Branch scoping is `BranchScopedViewSet`'s, so another institution's invoice is
**404, not 403**: 403 would confirm it exists, which is exactly what a probe is
looking for.

Permissions come from the catalogue resource `fees`, whose actions are
`view / create / update / collect / waive` (`accounts/permissions.py`). Note the
`permission_action_map` on `FeeViewSet`: a custom `@action` that POSTs is an
*update*, not a create (`POST_IS_AN_UPDATE`, worklog F1) — so without declaring
`collect` explicitly, `fees.create` would authorise taking money, which is a
different and much larger decision than raising an invoice.
"""

from decimal import Decimal

from django.db.models import Count, DecimalField, Sum
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import HasResourcePermission
from accounts.services import ActivityLogMixin
from core.middleware import ALL_BRANCHES, get_branch
from core.viewsets import BranchScopedViewSet

from .models import Fee, FeeCategory, Payment
from .serializers import (CollectSerializer, FeeCategorySerializer,
                          FeeSerializer, PaymentSerializer, ReasonSerializer)
from .services import collect_fee, recalculate_fee, reverse_payment, waive_fee

MONEY_FIELD = DecimalField(max_digits=12, decimal_places=2)


def writable_branch(request):
    """The Branch a service call belongs to, or a 400 naming what is missing.

    `get_branch()` rather than `request.branch`: the lazy proxy makes an
    `is None` check pass for everyone, silently, every time (CLAUDE.md §5).
    """
    from branches.models import Branch

    branch = get_branch(request)
    if branch is None or branch == ALL_BRANCHES:
        raise ValidationError({
            'branch': ('Choose an institution before doing this. '
                       'Add ?branch=<id> to the request.'),
        })
    if isinstance(branch, str):
        resolved = Branch.objects.filter(pk=branch).first()
        if resolved is None:
            raise ValidationError({'branch': 'No institution with that id.'})
        return resolved
    return branch


class FeeCategoryViewSet(ActivityLogMixin, BranchScopedViewSet):
    """The heads of charge. Seeded per branch; the institution may add its own.

    No `destroy` of a seeded row: `is_system` categories are deactivated, never
    deleted (docs/03 §7), and an invoice points at them with PROTECT anyway.
    """

    queryset = FeeCategory.objects.select_related('branch').all()
    serializer_class = FeeCategorySerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'fees'
    activity_model = 'FeeCategory'
    filterset_fields = ['recurrence', 'is_active', 'is_mandatory', 'is_system']
    search_fields = ['code', 'name', 'name_bn']
    ordering_fields = ['display_order', 'name', 'code', 'created_at']

    def perform_destroy(self, instance):
        if instance.is_system:
            raise ValidationError({
                'detail': 'A seeded category can be deactivated but not deleted · '
                          'পূর্বনির্ধারিত খাত মুছে ফেলা যাবে না, নিষ্ক্রিয় করুন।',
            })
        super().perform_destroy(instance)


class FeeViewSet(ActivityLogMixin, BranchScopedViewSet):
    """Invoices, and the two actions that change what they say happened.

    `collect` and `waive` are `@action`s rather than PATCHes on purpose: both
    are multi-step writes that span two models, so they belong in a service
    inside a transaction, and neither may be reachable by editing a field
    (CLAUDE.md §4.3).
    """

    queryset = Fee.objects.select_related(
        'branch', 'student', 'category', 'session', 'enrolment',
    ).all()
    serializer_class = FeeSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'fees'
    permission_action_map = {
        # The whole reason this map exists. A custom POST infers `update`
        # (POST_IS_AN_UPDATE); collecting money is its own checkbox in the
        # catalogue and must be checked for itself.
        'collect': 'collect',
        'waive': 'waive',
        'payments': 'view',
        'summary': 'view',
    }
    activity_model = 'Fee'
    filterset_fields = ['student', 'category', 'session', 'status', 'period',
                        'enrolment', 'generated_by', 'is_active']
    search_fields = ['invoice_no', 'student__name', 'student__student_id',
                     'category__code', 'category__name']
    ordering_fields = ['due_date', 'created_at', 'payable', 'paid_amount', 'status']

    def perform_create(self, serializer):
        """A manual invoice — the counter raising a book or uniform charge.

        The invoice number comes from the same per-branch counter the monthly
        job draws from, inside this request's transaction, so a number reserved
        and then lost to a failed save is not a hole in the series.
        """
        from django.db import transaction

        from .services import next_invoice_no

        branch = writable_branch(self.request)
        with transaction.atomic():
            fee = serializer.save(
                branch=branch,
                invoice_no=next_invoice_no(branch),
                created_by=self.request.user,
            )
            recalculate_fee(fee, save=True)

    def perform_update(self, serializer):
        """Editing `amount` or `discount` changes what is owed — recompute.

        Without this an accountant could correct a ৳500 invoice to ৳300 and
        leave `payable` at 500, which the dues report would go on believing.
        """
        from django.db import transaction

        with transaction.atomic():
            fee = serializer.save(updated_by=self.request.user)
            recalculate_fee(fee, save=True)

    @action(detail=True, methods=['post'])
    def collect(self, request, pk=None):
        """`POST /api/fees/<id>/collect/` — the most-used endpoint (docs/06 #10).

        One transaction inside the service: receipt number, Payment, invoice
        recompute, and the `finance.Income` row. The response is the receipt
        payload the SPA prints.
        """
        fee = self.get_object()
        body = CollectSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        payment = collect_fee(
            fee=fee,
            amount=body.validated_data['amount'],
            method=body.validated_data['method'],
            transaction_id=body.validated_data['transaction_id'],
            paid_at=body.validated_data.get('paid_at'),
            note=body.validated_data['note'],
            collected_by=request.user,
            request=request,
        )
        fee.refresh_from_db()

        return Response(
            {'payment': PaymentSerializer(payment).data,
             'fee': FeeSerializer(fee).data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def waive(self, request, pk=None):
        """`POST /api/fees/<id>/waive/` — write off the balance, with a reason."""
        fee = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        fee = waive_fee(fee, reason=body.validated_data['reason'],
                        actor=request.user, request=request)
        return Response(FeeSerializer(fee).data)

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        """Every receipt against this invoice, reversed ones included.

        Reversed receipts are shown, not hidden: the counter has to be able to
        explain to a guardian why the balance changed back.
        """
        fee = self.get_object()
        queryset = fee.payments.select_related('collected_by').order_by('-paid_at')
        return Response(PaymentSerializer(queryset, many=True).data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Totals per status for the dues screen, over the current filters.

        `output_field=DecimalField` on both sums, or the totals can come back as
        floats and the dues figure on the dashboard stops matching the sum of
        the rows below it (CLAUDE.md §1).
        """
        queryset = self.filter_queryset(self.get_queryset())
        rows = (
            queryset.values('status')
            .annotate(
                count=Count('id'),
                payable=Sum('payable', output_field=MONEY_FIELD),
                paid=Sum('paid_amount', output_field=MONEY_FIELD),
            )
            .order_by('status')
        )

        out = []
        for row in rows:
            payable = row['payable'] or Decimal('0.00')
            paid = row['paid'] or Decimal('0.00')
            out.append({
                'status': row['status'],
                'count': row['count'],
                'payable': str(payable),
                'paid': str(paid),
                'balance': str(payable - paid),
            })
        return Response(out)


class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    """Receipts. Read-only, plus `reverse`.

    Deliberately **not** a `ModelViewSet`. There is no create route — a receipt
    is written by `fees/<id>/collect/` so it can never exist without its income
    row — and no update or destroy route, because a wrong receipt is reversed,
    never edited or deleted (docs/01 §9).

    `BranchScopedMixin` is not inherited here for the same reason: it stamps
    branch on create, and there is no create. The queryset is scoped explicitly
    below, which is the whole of what this viewset needs.
    """

    queryset = Payment.objects.select_related(
        'branch', 'fee', 'fee__category', 'student', 'collected_by', 'income',
    ).all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_resource = 'fees'
    permission_action_map = {
        # Reversing a receipt un-takes money. It costs the same permission
        # taking it did, not a lesser `update`.
        'reverse': 'collect',
    }
    filterset_fields = ['fee', 'student', 'method', 'is_reversed']
    search_fields = ['receipt_no', 'transaction_id', 'student__name',
                     'student__student_id']
    ordering_fields = ['paid_at', 'amount', 'receipt_no']

    def get_queryset(self):
        return super().get_queryset().for_branch(get_branch(self.request))

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        """`POST /api/payments/<id>/reverse/` — reverses, never deletes.

        The income row is reversed in the same transaction, and the invoice's
        `paid_amount` and status fall back out on their own because
        `paid_total()` excludes reversed receipts.
        """
        payment = self.get_object()
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        payment = reverse_payment(payment, reason=body.validated_data['reason'],
                                  actor=request.user, request=request)
        payment.refresh_from_db()
        return Response(PaymentSerializer(payment).data)
