from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import Truncator

from .models import DailyReport, SentReply, SubscriberEvent
from .services import get_subscriber_stats


class ReadOnlyAdmin(admin.ModelAdmin):
    """Collected data is never created or edited by hand."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SubscriberEvent)
class SubscriberEventAdmin(ReadOnlyAdmin):
    """The collector: newest signups first, with the live statistics on top."""

    change_list_template = 'admin/monitor/subscriberevent/change_list.html'
    list_display = ['created_at', 'subscriber_email', 'subscriber_message',
                    'subscriber_confirmed', 'total_confirmed', 'unconfirmed', 'notified_at']
    readonly_fields = ['subscriber_email', 'full_message', 'created_at']
    list_select_related = ['subscriber']
    list_filter = ['created_at']
    date_hierarchy = 'created_at'
    search_fields = ['subscriber__email', 'subscriber__message']

    @admin.display(description='Email (click to reply)', ordering='subscriber__email')
    def subscriber_email(self, obj):
        url = reverse('admin:subscriptions_subscriber_reply', args=[obj.subscriber_id])
        return format_html('<a href="{}">{}</a>', url, obj.subscriber.email)

    @admin.display(description='Message')
    def subscriber_message(self, obj):
        return Truncator(obj.subscriber.message).chars(60)

    @admin.display(description='Message (full)')
    def full_message(self, obj):
        return obj.subscriber.message

    @admin.display(description='Confirmed', boolean=True)
    def subscriber_confirmed(self, obj):
        return obj.subscriber.is_active

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['monitor_stats'] = get_subscriber_stats()
        extra_context['monitor_recent_reports'] = DailyReport.objects.all()[:7]
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(DailyReport)
class DailyReportAdmin(ReadOnlyAdmin):
    list_display = ['report_date', 'new_submissions', 'new_confirmed',
                    'total_confirmed', 'unconfirmed', 'emailed_at', 'email_error']
    date_hierarchy = 'report_date'


@admin.register(SentReply)
class SentReplyAdmin(ReadOnlyAdmin):
    list_display = ['sent_at', 'subscriber', 'subject', 'sent_by']
    list_select_related = ['subscriber', 'sent_by']
    date_hierarchy = 'sent_at'
    search_fields = ['subscriber__email', 'subject', 'body']

