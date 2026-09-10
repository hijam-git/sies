"""Django admin — for debugging, not for daily work.

The SPA is where fees are collected. This exists so a developer can see what an
invoice or a receipt actually holds, which is the first question when a balance
looks wrong.

Every derived and issued column is read-only here too. The admin is a database
editor with no service behind it, so a `status` field editable from this screen
would be the one path in the system that can mark an invoice paid without money
arriving — the exact thing docs/06 #8 forbids.
"""

from django.contrib import admin

from .models import Fee, FeeCategory, Payment


@admin.register(FeeCategory)
class FeeCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'recurrence', 'is_mandatory',
                    'is_refundable', 'is_system', 'display_order', 'branch',
                    'is_active']
    list_filter = ['branch', 'recurrence', 'is_mandatory', 'is_system', 'is_active']
    search_fields = ['code', 'name', 'name_bn']
    ordering = ['branch', 'display_order']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'created_by', 'updated_by']


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ['receipt_no', 'amount', 'method', 'paid_at', 'collected_by',
              'is_reversed']
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        # A receipt written here would have no income row behind it. Collection
        # goes through `services.collect_fee()` or it does not happen.
        return False


@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ['invoice_no', 'student', 'category', 'period', 'amount',
                    'discount', 'fine', 'payable', 'paid_amount', 'status',
                    'due_date', 'branch']
    list_filter = ['branch', 'status', 'category', 'session', 'generated_by',
                   'is_active']
    search_fields = ['invoice_no', 'student__name', 'student__student_id', 'period']
    ordering = ['branch', '-due_date']
    date_hierarchy = 'due_date'
    inlines = [PaymentInline]
    readonly_fields = ['invoice_no', 'payable', 'paid_amount', 'status',
                       'waived_by', 'waived_at', 'created_at', 'updated_at',
                       'created_by', 'updated_by']
    raw_id_fields = ['branch', 'student', 'enrolment', 'category', 'session',
                     'waived_by', 'created_by', 'updated_by']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['receipt_no', 'student', 'amount', 'method', 'paid_at',
                    'collected_by', 'is_reversed', 'branch']
    list_filter = ['branch', 'method', 'is_reversed', 'is_active']
    search_fields = ['receipt_no', 'transaction_id', 'student__name',
                     'student__student_id']
    ordering = ['branch', '-paid_at']
    date_hierarchy = 'paid_at'
    readonly_fields = ['receipt_no', 'amount', 'income', 'is_reversed',
                       'reversed_at', 'reversed_by', 'created_at', 'updated_at',
                       'created_by', 'updated_by']
    raw_id_fields = ['branch', 'fee', 'student', 'collected_by', 'income',
                     'reversed_by', 'created_by', 'updated_by']

    def has_delete_permission(self, request, obj=None):
        # A wrong receipt is reversed, never deleted (docs/01 §9). Deleting one
        # here would destroy an accounting record and leave its income row
        # standing with nothing behind it.
        return False
