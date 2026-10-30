"""Instant and daily notifications.

Database success and email delivery are deliberately separate: nothing in
here can undo or invalidate a saved subscription. Email is only attempted
when MONITOR_NOTIFY_EMAIL is set; otherwise the data stays in the admin.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Exists, OuterRef
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.text import Truncator
from django.utils import timezone

from subscriptions.models import Subscriber

from .models import SentReply, SubscriberEvent
from .services import (
    get_day_bounds,
    get_report_tzinfo,
    get_subscriber_stats,
    get_unanswered_count,
)

logger = logging.getLogger(__name__)

# The daily email lists at most this many signups; the rest is in the admin.
MAX_LISTED_SIGNUPS = 200


def get_notify_recipient():
    return (settings.MONITOR_NOTIFY_EMAIL or '').strip()


def admin_url(viewname, *args):
    return f"{settings.SITE_URL.rstrip('/')}{reverse(viewname, args=args)}"


def _local(dt):
    return timezone.localtime(dt, get_report_tzinfo()).strftime('%Y-%m-%d %H:%M:%S %Z')


def _unanswered_link():
    return admin_url('admin:subscriptions_subscriber_changelist') + '?replied=no'


def handle_new_subscriber(subscriber_pk):
    """Called after the subscriber's transaction committed. Never raises."""
    try:
        subscriber = Subscriber.objects.get(pk=subscriber_pk)
        stats = get_subscriber_stats()
        event = SubscriberEvent.objects.create(
            subscriber=subscriber,
            total_confirmed=stats.total,
            unconfirmed=stats.unconfirmed,
        )
    except Exception:
        logger.exception('Could not record new-subscriber event (subscriber id=%s)', subscriber_pk)
        return

    recipient = get_notify_recipient()
    if recipient:
        send_new_subscriber_email(event, recipient)


def render_new_subscriber_email(event):
    """Returns (subject, text, html) for the instant notification."""
    subscriber = event.subscriber
    context = {
        'email': subscriber.email,
        'message': subscriber.message,
        'when': _local(subscriber.created_at),
        'total_confirmed': event.total_confirmed,
        'unconfirmed': event.unconfirmed,
        'unanswered': get_unanswered_count(),
        'unanswered_link': _unanswered_link(),
        'reply_link': admin_url('admin:subscriptions_subscriber_reply', subscriber.pk),
        'admin_link': admin_url('admin:subscriptions_subscriber_change', subscriber.pk),
    }
    return (
        'Új várólistás jelentkező',
        render_to_string('monitor/email/new_subscriber.txt', context),
        render_to_string('monitor/email/new_subscriber.html', context),
    )


def send_new_subscriber_email(event, recipient):
    try:
        subject, text, html = render_new_subscriber_email(event)
        send_mail(
            subject,
            text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=html,
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception('New-subscriber notification failed (subscriber id=%s)', event.subscriber_id)
        SubscriberEvent.objects.filter(pk=event.pk).update(notify_error=type(exc).__name__[:200])
        return False
    SubscriberEvent.objects.filter(pk=event.pk).update(notified_at=timezone.now(), notify_error='')
    return True


def render_daily_report_email(report):
    """Returns (subject, text, html): statistics plus the list of that day's signups."""
    start, end = get_day_bounds(report.report_date)
    signups = Subscriber.objects.filter(
        created_at__gte=start, created_at__lt=end
    ).annotate(
        has_reply=Exists(SentReply.objects.filter(subscriber=OuterRef('pk')))
    ).order_by('created_at')[:MAX_LISTED_SIGNUPS]
    rows = [
        {
            'email': sub.email,
            'when': _local(sub.created_at),
            'confirmed': sub.is_active,
            'replied': sub.has_reply,
            'reply_link': admin_url('admin:subscriptions_subscriber_reply', sub.pk),
            # one line, shortened: the full text is in the admin
            'message': Truncator(' '.join(sub.message.split())).chars(200),
        }
        for sub in signups
    ]
    context = {
        'day': report.report_date,
        'report': report,
        'rows': rows,
        'more': max(0, report.new_submissions - len(rows)),
        'unanswered': get_unanswered_count(),
        'unanswered_link': _unanswered_link(),
        'tz': settings.MONITOR_REPORT_TIMEZONE,
        'admin_link': admin_url('admin:subscriptions_subscriber_changelist'),
    }
    return (
        f'Korrep napi összesítő – {report.report_date:%Y-%m-%d}',
        render_to_string('monitor/email/daily_report.txt', context),
        render_to_string('monitor/email/daily_report.html', context),
    )


def send_daily_report_email(report, recipient):
    """Raises on failure; the caller decides what to do with the report row."""
    subject, text, html = render_daily_report_email(report)
    send_mail(
        subject,
        text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        html_message=html,
        fail_silently=False,
    )
