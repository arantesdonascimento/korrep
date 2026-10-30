import logging

from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef
from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.text import Truncator

from monitor.inlines import SentReplyInline
from monitor.models import SentReply
from monitor.replies import ReplyForm, default_subject, send_reply
from monitor.services import get_subscriber_stats

from .models import Subscriber

logger = logging.getLogger(__name__)


class RepliedFilter(admin.SimpleListFilter):
    title = 'reply status'
    parameter_name = 'replied'

    def lookups(self, request, model_admin):
        return [('no', 'Not replied yet'), ('yes', 'Replied')]

    def queryset(self, request, queryset):
        if self.value() == 'no':
            return queryset.filter(has_reply=False)
        if self.value() == 'yes':
            return queryset.filter(has_reply=True)
        return queryset


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ['email', 'phone', 'short_message', 'replied', 'reply_link',
                    'is_active', 'created_at', 'activated_at']
    list_filter = ['is_active', RepliedFilter, 'created_at']
    search_fields = ['email', 'phone', 'message']
    readonly_fields = ['confirmation_token', 'message', 'created_at', 'activated_at']
    ordering = ['-created_at']
    inlines = [SentReplyInline]

    change_list_template = 'admin/subscriptions/subscriber/change_list.html'

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            has_reply=Exists(SentReply.objects.filter(subscriber=OuterRef('pk')))
        )

    @admin.display(description='Message')
    def short_message(self, obj):
        return Truncator(obj.message).chars(60)

    @admin.display(description='Replied', boolean=True, ordering='has_reply')
    def replied(self, obj):
        return obj.has_reply

    @admin.display(description='Reply')
    def reply_link(self, obj):
        url = reverse('admin:subscriptions_subscriber_reply', args=[obj.pk])
        return format_html('<a href="{}">✉ Reply</a>', url)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['monitor_stats'] = get_subscriber_stats()
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        # Custom URLs must come first: the built-in "<path>/" catch-all would swallow them.
        custom = [
            path(
                '<path:object_id>/reply/',
                self.admin_site.admin_view(self.reply_view),
                name='subscriptions_subscriber_reply',
            ),
        ]
        return custom + super().get_urls()

    def reply_view(self, request, object_id):
        subscriber = self.get_object(request, unquote(object_id))
        if subscriber is None:
            raise Http404('No such subscriber.')
        if not self.has_change_permission(request, subscriber):
            raise PermissionDenied

        if request.method == 'POST':
            form = ReplyForm(request.POST)
            if form.is_valid():
                try:
                    send_reply(subscriber, form.cleaned_data['subject'],
                               form.cleaned_data['body'], request.user)
                except Exception:
                    logger.exception('Reply email failed (subscriber id=%s)', subscriber.pk)
                    messages.error(
                        request,
                        'The reply could not be sent, nothing was recorded. '
                        'Check the SMTP settings and try again.',
                    )
                else:
                    messages.success(request, f'Reply sent to {subscriber.email}.')
                    return redirect('admin:subscriptions_subscriber_change', subscriber.pk)
        else:
            form = ReplyForm(initial={'subject': default_subject(subscriber)})

        context = {
            **self.admin_site.each_context(request),
            'title': f'Reply to {subscriber.email}',
            'subscriber': subscriber,
            'form': form,
            'opts': self.model._meta,
            'previous_replies': subscriber.replies.all()[:10],
        }
        return TemplateResponse(request, 'admin/subscriptions/subscriber/reply.html', context)
