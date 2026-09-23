"""Registered for debugging (CLAUDE.md, definition of done)."""

from django.contrib import admin

from .models import ReportAnswer, ReportTemplate, StudentReport


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'branch', 'frequency', 'section', 'stream',
                    'academic_class', 'is_active']
    list_filter = ['frequency', 'is_active']


@admin.register(StudentReport)
class StudentReportAdmin(admin.ModelAdmin):
    list_display = ['student', 'template', 'period', 'filled_by', 'filled_at']
    list_filter = ['template', 'period']
    search_fields = ['student__name', 'student__name_bn']


admin.site.register(ReportAnswer)
