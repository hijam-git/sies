"""Django admin registrations — for debugging, not for daily work.

The SPA administers the academic frame. This exists so a developer can see what
a routine row or an enrolment actually holds, which is the first question when a
teacher's scope or a class roster looks wrong.
"""

from django.contrib import admin

from .models import (AcademicClass, ClassRoutine, Enrolment, Period, Section,
                     Subject, SubjectAssignment)


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    raw_id_fields = ['branch', 'in_charge', 'created_by', 'updated_by']


@admin.register(AcademicClass)
class AcademicClassAdmin(admin.ModelAdmin):
    list_display = ['name', 'stream', 'session', 'year', 'level_order',
                    'class_teacher', 'branch', 'is_active']
    list_filter = ['branch', 'session', 'stream', 'year', 'is_active']
    search_fields = ['name', 'name_bn']
    ordering = ['branch', '-year', 'level_order']
    inlines = [SectionInline]
    readonly_fields = ['year', 'created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'stream', 'session', 'class_teacher',
                     'created_by', 'updated_by']


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'academic_class', 'room', 'capacity', 'in_charge', 'is_active']
    list_filter = ['branch', 'is_active']
    search_fields = ['name', 'name_bn', 'room', 'academic_class__name']
    ordering = ['branch', 'academic_class', 'name']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'academic_class', 'in_charge', 'created_by', 'updated_by']


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'academic_class', 'stream', 'full_marks',
                    'pass_marks', 'is_optional', 'has_practical', 'is_active']
    list_filter = ['branch', 'stream', 'is_optional', 'has_practical', 'is_active']
    search_fields = ['name', 'name_bn', 'code', 'academic_class__name']
    ordering = ['branch', 'academic_class', 'name']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'stream', 'academic_class', 'created_by', 'updated_by']


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ['order', 'name', 'stream', 'start_time', 'end_time',
                    'is_break', 'branch', 'is_active']
    list_filter = ['branch', 'stream', 'is_break', 'is_active']
    search_fields = ['name', 'name_bn']
    ordering = ['branch', 'stream', 'order']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'stream', 'created_by', 'updated_by']


@admin.register(ClassRoutine)
class ClassRoutineAdmin(admin.ModelAdmin):
    list_display = ['day_of_week', 'period', 'academic_class', 'section',
                    'subject', 'teacher', 'room', 'session', 'is_active']
    list_filter = ['branch', 'session', 'day_of_week', 'is_active']
    search_fields = ['room', 'subject__name', 'teacher__name', 'academic_class__name']
    ordering = ['branch', 'day_of_week', 'period']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'session', 'academic_class', 'section', 'subject',
                     'teacher', 'period', 'created_by', 'updated_by']


@admin.register(Enrolment)
class EnrolmentAdmin(admin.ModelAdmin):
    list_display = ['admission_number', 'roll', 'student', 'academic_class',
                    'section', 'session', 'status', 'is_active']
    list_filter = ['branch', 'session', 'status', 'is_hostel', 'is_transport',
                   'is_active']
    search_fields = ['admission_number', 'student__name', 'student__student_id']
    ordering = ['branch', '-session', 'academic_class', 'roll']
    # Issued under a row lock by `services.enrol_student()`. Typing over either
    # of them here re-issues a number already printed on a guardian's slip.
    readonly_fields = ['roll', 'admission_number',
                       'created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'student', 'session', 'academic_class', 'section',
                     'created_by', 'updated_by']


@admin.register(SubjectAssignment)
class SubjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'subject', 'academic_class', 'section', 'session',
                    'branch', 'is_active']
    list_filter = ['branch', 'session', 'is_active']
    search_fields = ['teacher__name', 'subject__name', 'academic_class__name']
    ordering = ['branch', '-session', 'academic_class']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['branch', 'session', 'teacher', 'subject', 'academic_class',
                     'section', 'created_by', 'updated_by']
