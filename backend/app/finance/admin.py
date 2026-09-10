"""Django admin — for debugging, not for daily work.

Auto-posted rows are read-only here for the same reason they are in the API: an
income row edited away from the receipt it was posted from is the disagreement
between the fee ledger and the accounts that docs/02 §4.6 removes.
"""

from django.contrib import admin

from .models import EntrySource, Expense, ExpenseCategory, Income, IncomeCategory


@admin.register(IncomeCategory)
class IncomeCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'fee_category', 'is_system',
                    'display_order', 'branch', 'is_active']
    list_filter = ['branch', 'is_system', 'is_active']
    search_fields = ['code', 'name', 'name_bn']
    ordering = ['branch', 'display_order']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'fee_category', 'created_by', 'updated_by']


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_system', 'display_order', 'branch',
                    'is_active']
    list_filter = ['branch', 'is_system', 'is_active']
    search_fields = ['code', 'name', 'name_bn']
    ordering = ['branch', 'display_order']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'created_by', 'updated_by']


class LedgerEntryAdmin(admin.ModelAdmin):
    list_filter = ['branch', 'source', 'method', 'is_approved', 'is_reversed',
                   'is_active']
    search_fields = ['voucher_no', 'reference', 'description']
    ordering = ['branch', '-date']
    date_hierarchy = 'date'
    readonly_fields = ['voucher_no', 'source', 'is_reversed', 'reversed_at',
                       'reversed_by', 'created_at', 'updated_at', 'created_by',
                       'updated_by']

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.source != EntrySource.MANUAL:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # A ledger row that has been in a month's P&L is reversed, not removed.
        return False


@admin.register(Income)
class IncomeAdmin(LedgerEntryAdmin):
    list_display = ['voucher_no', 'date', 'category', 'amount', 'method',
                    'source', 'payment', 'is_reversed', 'branch']
    raw_id_fields = ['branch', 'category', 'session', 'payment', 'recorded_by',
                     'approved_by', 'reversed_by', 'created_by', 'updated_by']


@admin.register(Expense)
class ExpenseAdmin(LedgerEntryAdmin):
    list_display = ['voucher_no', 'date', 'category', 'amount', 'method',
                    'source', 'is_approved', 'is_reversed', 'branch']
    raw_id_fields = ['branch', 'category', 'session', 'recorded_by',
                     'approved_by', 'reversed_by', 'created_by', 'updated_by']
