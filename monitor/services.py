"""Statistics layer: the single place that computes subscriber numbers.

Everything is derived from subscriptions.Subscriber with the ORM; there is no
counter or statistics table to get out of sync.

Definitions (the existing flow is double opt-in):
  confirmed   -> Subscriber.is_active is True
  unconfirmed -> Subscriber.is_active is False (waiting for the email link)
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from subscriptions.models import Subscriber


@dataclass(frozen=True)
class SubscriberStats:
    total: int               # confirmed subscribers
    unconfirmed: int         # waiting for email confirmation
    last_24h: int            # signups submitted in the rolling last 24 hours
    last_24h_confirmed: int  # confirmations in the rolling last 24 hours
    unanswered: int          # subscribers who have not received a reply yet


def get_subscriber_stats(now=None):
    now = now or timezone.now()
    since = now - timedelta(hours=24)
    data = Subscriber.objects.aggregate(
        total=Count('pk', filter=Q(is_active=True)),
        unconfirmed=Count('pk', filter=Q(is_active=False)),
        last_24h=Count('pk', filter=Q(created_at__gte=since)),
        last_24h_confirmed=Count(
            'pk', filter=Q(is_active=True, activated_at__gte=since)
        ),
    )
    data['unanswered'] = get_unanswered_count()
    return SubscriberStats(**data)


def get_unanswered_count():
    return Subscriber.objects.filter(replies__isnull=True).count()


@dataclass(frozen=True)
class PublicStats:
    """The numbers shown on the public home page. Confirmed subscribers only,
    so the 24h and 7-day figures can never exceed the total."""
    total: int
    last_24h: int
    last_7d: int


def get_public_stats(now=None):
    now = now or timezone.now()
    data = Subscriber.objects.filter(is_active=True).aggregate(
        total=Count('pk'),
        last_24h=Count('pk', filter=Q(activated_at__gte=now - timedelta(hours=24))),
        last_7d=Count('pk', filter=Q(activated_at__gte=now - timedelta(days=7))),
    )
    return PublicStats(**data)


def get_confirmed_count():
    """The only number shown publicly on the home page."""
    return Subscriber.objects.filter(is_active=True).count()


# ---- daily report helpers -------------------------------------------------

def get_report_tzinfo():
    return ZoneInfo(settings.MONITOR_REPORT_TIMEZONE)


def default_report_date(now=None):
    """Yesterday, as a calendar date in the report time zone."""
    now = now or timezone.now()
    return timezone.localtime(now, get_report_tzinfo()).date() - timedelta(days=1)


def get_day_bounds(day: date):
    """[start, end) of a calendar day in the report time zone (aware)."""
    tz = get_report_tzinfo()
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start, end


def get_period_stats(start, end):
    return Subscriber.objects.aggregate(
        new_submissions=Count(
            'pk', filter=Q(created_at__gte=start, created_at__lt=end)
        ),
        new_confirmed=Count(
            'pk', filter=Q(activated_at__gte=start, activated_at__lt=end)
        ),
    )
