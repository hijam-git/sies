"""Django admin registration — for debugging, not for daily work.

`PrintedForm` is read-only here: its snapshot is the record of what was signed,
and an admin form able to edit it would make that record editable, which is the
one property it exists to have.
"""

from django.contrib import admin

from .models import AdmissionAnswer, FormTemplate, PrintedForm, Question


@admin.register(FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'branch', 'form_type', 'is_default', 'is_active']
    list_filter = ['branch', 'form_type', 'is_active']
    search_fields = ['name', 'name_bn']
    raw_id_fields = ['branch', 'created_by', 'updated_by']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['text_bn', 'branch', 'section', 'type', 'maps_to', 'order']
    list_filter = ['branch', 'section', 'type', 'is_active']
    search_fields = ['text', 'text_bn']
    raw_id_fields = ['branch', 'template', 'created_by', 'updated_by']


@admin.register(AdmissionAnswer)
class AdmissionAnswerAdmin(admin.ModelAdmin):
    list_display = ['admission', 'question', 'answered_at']
    raw_id_fields = ['branch', 'admission', 'question', 'created_by', 'updated_by']


@admin.register(PrintedForm)
class PrintedFormAdmin(admin.ModelAdmin):
    list_display = ['form_no', 'branch', 'admission', 'printed_at', 'reprint_count']
    list_filter = ['branch', 'template']
    search_fields = ['form_no']
    raw_id_fields = ['branch', 'admission', 'template', 'printed_by',
                     'created_by', 'updated_by']
    readonly_fields = ['form_no', 'snapshot', 'printed_by', 'printed_at']
