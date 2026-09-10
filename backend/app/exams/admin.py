"""Django admin registration — for debugging, not for daily work.

Marks are read-only here on purpose. The supported way to write one is
`services.save_marks`, which takes the subject-scope check and the transaction
with it; an admin form that bypassed both would be the second write path this
module deliberately does not have.
"""

from django.contrib import admin

from .models import Exam, ExamClass, ExamSchedule, Mark


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['name', 'branch', 'session', 'exam_type', 'status', 'starts_on']
    list_filter = ['branch', 'exam_type', 'status']
    search_fields = ['name', 'name_bn']
    raw_id_fields = ['branch', 'session', 'stream', 'published_by',
                     'created_by', 'updated_by']


@admin.register(ExamClass)
class ExamClassAdmin(admin.ModelAdmin):
    list_display = ['exam', 'academic_class']
    raw_id_fields = ['branch', 'exam', 'academic_class', 'created_by', 'updated_by']


@admin.register(ExamSchedule)
class ExamScheduleAdmin(admin.ModelAdmin):
    list_display = ['exam', 'academic_class', 'subject', 'date', 'full_marks']
    list_filter = ['branch', 'exam']
    raw_id_fields = ['branch', 'exam', 'academic_class', 'subject', 'invigilator',
                     'created_by', 'updated_by']


@admin.register(Mark)
class MarkAdmin(admin.ModelAdmin):
    list_display = ['exam', 'student', 'subject', 'obtained', 'is_absent', 'is_active']
    list_filter = ['branch', 'exam', 'is_absent', 'is_active']
    raw_id_fields = ['branch', 'exam', 'student', 'enrolment', 'subject',
                     'entered_by', 'created_by', 'updated_by']
    readonly_fields = ['obtained', 'practical_obtained', 'is_absent',
                       'entered_by', 'entered_at']
