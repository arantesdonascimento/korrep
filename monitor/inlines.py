from django.contrib import admin

from .models import SentReply


class SentReplyInline(admin.TabularInline):
    """Read-only reply history on the subscriber's page."""

    model = SentReply
    extra = 0
    can_delete = False
    fields = ['sent_at', 'subject', 'body', 'sent_by']
    readonly_fields = ['sent_at', 'subject', 'body', 'sent_by']

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
