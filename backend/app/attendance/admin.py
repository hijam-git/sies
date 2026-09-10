"""Django admin registrations — for debugging, not for daily work.

The SPA's month grid is where attendance is taken. This exists so a developer
can see what a row actually holds, which is the first question when a teacher
says a cell they marked is not there — and the answer is usually that it was
written against a different enrolment, which only this view shows.
"""

from django.contrib import admin

from .models import ClassAttendance, DailyAttendance


@admin.register(DailyAttendance)
class DailyAttendanceAdmin(admin.ModelAdmin):
    list_display = ['date', 'person_type', 'person', 'status', 'branch',
                    'taken_by', 'taken_at', 'source']
    list_filter = ['branch', 'person_type', 'status', 'source', 'date']
    search_fields = ['student__name', 'student__student_id', 'teacher__name',
                     'employee__name', 'remarks']
    date_hierarchy = 'date'
    ordering = ['-date', 'person_type']
    # A branch has thousands of students and a year of enrolments; a raw id keeps
    # the change form from rendering every one of them into a <select>.
    raw_id_fields = ['branch', 'student', 'teacher', 'employee', 'enrolment',
                     'taken_by', 'created_by', 'updated_by']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ClassAttendance)
class ClassAttendanceAdmin(admin.ModelAdmin):
    list_display = ['date', 'academic_class', 'section', 'period', 'student',
                    'status', 'branch', 'taken_by', 'taken_at']
    list_filter = ['branch', 'status', 'source', 'date', 'period']
    search_fields = ['student__name', 'student__student_id', 'remarks']
    date_hierarchy = 'date'
    ordering = ['-date', 'period']
    raw_id_fields = ['branch', 'academic_class', 'section', 'subject', 'period',
                     'student', 'enrolment', 'taken_by', 'created_by',
                     'updated_by']
    readonly_fields = ['created_at', 'updated_at']
