"""Registered for debugging (CLAUDE.md, definition of done)."""

from django.contrib import admin

from .models import NotificationTemplate, SmsMessage


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['branch', 'event', 'channel', 'language', 'is_active']
    list_filter = ['event', 'channel', 'language', 'is_active']
    search_fields = ['body']


@admin.register(SmsMessage)
class SmsMessageAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'branch', 'event', 'to_phone', 'status', 'parts']
    list_filter = ['event', 'status', 'provider']
    search_fields = ['to_phone', 'body', 'recipient_label']
    # An outbox row is a record of something that happened. Editing one in the
    # admin would make the audit trail agree with itself about a message that
    # never went anywhere.
    readonly_fields = [f.name for f in SmsMessage._meta.fields]
