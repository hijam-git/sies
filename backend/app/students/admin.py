"""Django admin registrations — for debugging, not for daily work.

The SPA is where students are admitted and edited. This exists so a developer
can see what a failed admission actually wrote, which is the first question when
a student appears with no enrolment.

Note what is deliberately read-only everywhere below: `student_id` and
`application_no`. They are allocated by `services` from a gapless series
(CLAUDE.md §4.4), and typing over one here would silently break the promise the
whole series exists to make.
"""

from django.contrib import admin

from .models import (Admission, Document, Guardian, Student,
                     StudentGuardian)


class StudentGuardianInline(admin.TabularInline):
    model = StudentGuardian
    extra = 0
    raw_id_fields = ['guardian', 'branch', 'created_by', 'updated_by']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['student_id', 'name', 'name_bn', 'branch', 'stream',
                    'status', 'is_active', 'admitted_on']
    list_filter = ['branch', 'stream', 'status', 'gender', 'is_active', 'district']
    search_fields = ['student_id', 'name', 'name_bn', 'phone',
                     'birth_certificate_no', 'nid', 'village', 'upazila']
    ordering = ['branch', 'name']
    readonly_fields = ['student_id', 'created_at', 'updated_at',
                       'created_by', 'updated_by']
    raw_id_fields = ['branch', 'stream', 'user', 'created_by', 'updated_by']
    inlines = [StudentGuardianInline]
    fieldsets = [
        ('Identity · পরিচয়', {
            'fields': ['student_id', 'branch', 'stream', 'user',
                       'name', 'name_bn', 'photo', 'date_of_birth', 'gender'],
        }),
        ('Documents & health · কাগজপত্র ও স্বাস্থ্য', {
            'fields': ['birth_certificate_no', 'nid', 'blood_group', 'religion_notes'],
        }),
        ('Contact · যোগাযোগ', {
            'fields': ['phone', 'email'],
        }),
        # The four structured boxes of the printed admission form (docs/07 §4),
        # grouped so they are filled in as the form asks for them.
        ('Address · ঠিকানা', {
            'fields': ['village', 'post_office', 'upazila', 'district',
                       'present_address', 'permanent_address'],
        }),
        ('Previous institution · পূর্ববর্তী প্রতিষ্ঠান', {
            'fields': ['previous_institution', 'previous_class'],
        }),
        ('Status · অবস্থা', {
            'fields': ['admitted_on', 'status', 'is_active'],
        }),
        ('Audit', {'fields': ['created_at', 'updated_at', 'created_by', 'updated_by']}),
    ]


@admin.register(Guardian)
class GuardianAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'relation', 'branch', 'occupation', 'is_active']
    list_filter = ['branch', 'relation', 'is_active']
    search_fields = ['name', 'name_bn', 'phone', 'alt_phone', 'nid', 'occupation']
    ordering = ['branch', 'name']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'user', 'created_by', 'updated_by']


@admin.register(StudentGuardian)
class StudentGuardianAdmin(admin.ModelAdmin):
    list_display = ['student', 'guardian', 'is_primary', 'branch']
    list_filter = ['branch', 'is_primary']
    search_fields = ['student__name', 'student__student_id',
                     'guardian__name', 'guardian__phone']
    ordering = ['student']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'student', 'guardian', 'created_by', 'updated_by']


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ['application_no', 'applicant_name', 'branch', 'session',
                    'academic_class', 'status', 'student', 'processed_at']
    list_filter = ['branch', 'session', 'status', 'stream', 'gender']
    search_fields = ['application_no', 'applicant_name', 'applicant_name_bn',
                     'guardian_name', 'guardian_phone']
    ordering = ['branch', '-created_at']
    readonly_fields = ['application_no', 'student', 'processed_by', 'processed_at',
                       'created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'session', 'stream', 'academic_class',
                     'created_by', 'updated_by']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'doc_type', 'owner_type', 'branch',
                    'issued_on', 'expires_on']
    list_filter = ['branch', 'owner_type', 'doc_type']
    search_fields = ['title', 'student__name', 'student__student_id']
    ordering = ['branch', '-created_at']
    readonly_fields = ['uploaded_by', 'created_at', 'updated_at',
                       'created_by', 'updated_by']
    raw_id_fields = ['branch', 'student', 'teacher', 'employee',
                     'created_by', 'updated_by']


