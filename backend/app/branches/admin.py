"""Django admin registrations — for debugging, not for daily work.

The SPA is where an institution is administered. This exists so a developer can
look at what actually got seeded, which is the first question when a branch
behaves oddly.
"""

from django.contrib import admin

from .models import Branch, Session, Stream


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'name_bn', 'institution_type', 'district',
                    'current_session', 'is_active', 'created_at']
    list_filter = ['institution_type', 'is_active', 'district', 'default_language']
    search_fields = ['name', 'name_bn', 'name_ar', 'code', 'phone', 'email', 'district']
    ordering = ['name']
    # Everything else about an institution is edited on one screen; the audit
    # columns are written by services and must not be typed over here.
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    # A branch has hundreds of users and dozens of sessions; a raw id keeps the
    # change form from rendering every one of them into a <select>.
    raw_id_fields = ['head', 'current_session', 'created_by', 'updated_by']
    fieldsets = [
        ('Identity · পরিচয়', {
            'fields': ['name', 'name_bn', 'name_ar', 'institution_type', 'code',
                       'established_year', 'logo', 'is_active'],
        }),
        ('Contact · যোগাযোগ', {
            'fields': ['address', 'address_bn', 'district', 'thana',
                       'phone', 'alt_phone', 'email'],
        }),
        ('People and session · দায়িত্ব ও শিক্ষাবর্ষ', {
            'fields': ['head', 'current_session'],
        }),
        ('Policy · নীতিমালা', {
            'fields': ['fine_rule', 'attendance_window_minutes',
                       'restrict_teachers_to_assigned_classes',
                       'activity_retention_days', 'weekly_off_days',
                       'sms_sender_id', 'default_language'],
        }),
        ('Audit', {'fields': ['created_at', 'updated_at', 'created_by', 'updated_by']}),
    ]


@admin.register(Stream)
class StreamAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'name_bn', 'branch', 'order', 'is_active']
    list_filter = ['branch', 'is_active']
    search_fields = ['code', 'name', 'name_bn', 'branch__name', 'branch__code']
    ordering = ['branch', 'order']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'created_by', 'updated_by']


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['name', 'branch', 'starts_on', 'ends_on', 'is_current']
    list_filter = ['branch', 'is_current']
    search_fields = ['name', 'branch__name', 'branch__code']
    ordering = ['branch', '-starts_on']
    filter_horizontal = ['streams']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'created_by', 'updated_by']
