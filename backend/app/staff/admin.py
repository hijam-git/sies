"""Django admin registrations — for debugging, not for daily work.

The SPA is where staff are administered. This exists so a developer can see what
a Teacher row actually holds, which is the first question when a teacher's
scoping behaves oddly.
"""

from django.contrib import admin

from .models import Employee, Teacher, TeacherQualification


class TeacherQualificationInline(admin.TabularInline):
    model = TeacherQualification
    extra = 0
    raw_id_fields = ['branch', 'created_by', 'updated_by']


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['teacher_id', 'name', 'name_bn', 'branch', 'designation',
                    'employment_status', 'is_class_teacher', 'is_active']
    list_filter = ['branch', 'employment_status', 'is_active', 'is_class_teacher']
    search_fields = ['teacher_id', 'name', 'name_bn', 'phone', 'nid', 'designation']
    ordering = ['branch', 'name']
    filter_horizontal = ['streams']
    inlines = [TeacherQualificationInline]
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    # A branch has hundreds of users; a raw id keeps the change form from
    # rendering every one of them into a <select>.
    raw_id_fields = ['branch', 'user', 'created_by', 'updated_by']
    fieldsets = [
        ('Identity · পরিচয়', {
            'fields': ['branch', 'teacher_id', 'user', 'name', 'name_bn', 'photo',
                       'dob', 'gender', 'nid', 'blood_group'],
        }),
        ('Contact · যোগাযোগ', {
            'fields': ['phone', 'alt_phone', 'email', 'village', 'post_office',
                       'upazila', 'district', 'address'],
        }),
        ('Employment · চাকরি', {
            'fields': ['designation', 'joining_date', 'leaving_date',
                       'employment_status', 'is_active'],
        }),
        ('Teaching · শিক্ষকতা', {
            'fields': ['streams', 'is_class_teacher', 'specialization',
                       'max_weekly_periods'],
        }),
        ('Pay · বেতন', {
            'fields': ['basic_salary', 'allowances', 'deductions',
                       'bank_account', 'mobile_banking'],
        }),
        ('Emergency · জরুরি', {
            'fields': ['emergency_contact_name', 'emergency_contact_phone'],
        }),
        ('Audit', {'fields': ['created_at', 'updated_at', 'created_by', 'updated_by']}),
    ]


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_id', 'name', 'name_bn', 'branch', 'department',
                    'designation', 'employment_status', 'is_active']
    list_filter = ['branch', 'employment_status', 'is_active', 'department']
    search_fields = ['employee_id', 'name', 'name_bn', 'phone', 'nid', 'department']
    ordering = ['branch', 'name']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'user', 'created_by', 'updated_by']


@admin.register(TeacherQualification)
class TeacherQualificationAdmin(admin.ModelAdmin):
    list_display = ['degree', 'teacher', 'institution', 'year', 'result']
    list_filter = ['branch', 'year']
    search_fields = ['degree', 'institution', 'result', 'teacher__name']
    ordering = ['teacher', '-year']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'teacher', 'created_by', 'updated_by']


