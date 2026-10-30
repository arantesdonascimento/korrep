from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
import re
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import SimpleTestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from monitor.models import DailyReport, SentReply, SubscriberEvent
from monitor.siteconfig import LOCAL_SITE_URL, SERVER_SITE_URL, resolve_site_url
from monitor.services import (
    default_report_date,
    get_confirmed_count,
    get_day_bounds,
    get_public_stats,
    get_subscriber_stats,
)
from subscriptions.models import Subscriber

UTC = dt_timezone.utc
BUD = ZoneInfo('Europe/Budapest')
NOTIFY_SUBJECT = 'Új várólistás jelentkező'

# Tests never send real mail and never depend on the developer's .env.
monitor_settings = override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    MONITOR_NOTIFY_EMAIL='owner@example.test',
    MONITOR_REPORT_TIMEZONE='Europe/Budapest',
    SITE_URL='http://testserver',
    DEFAULT_FROM_EMAIL='owner@example.test',
)


def make_subscriber(email, created=None, confirmed_at=None, message=''):
    """Create a Subscriber with explicit timestamps (auto_now_add is bypassed)."""
    sub = Subscriber.objects.create(email=email, is_active=confirmed_at is not None, message=message)
    updates = {'activated_at': confirmed_at}
    if created is not None:
        updates['created_at'] = created
    Subscriber.objects.filter(pk=sub.pk).update(**updates)
    return sub


def notification_mails():
    return [m for m in mail.outbox if m.subject == NOTIFY_SUBJECT]


@monitor_settings
class StatsTests(TestCase):
    NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)

    def test_total_counts_confirmed_only(self):  # 1
        make_subscriber('a@example.com', confirmed_at=self.NOW)
        make_subscriber('b@example.com', confirmed_at=self.NOW)
        make_subscriber('c@example.com')
        make_subscriber('d@example.com')
        make_subscriber('e@example.com')
        stats = get_subscriber_stats(now=self.NOW)
        self.assertEqual(stats.total, 2)
        self.assertEqual(stats.unconfirmed, 3)
        self.assertEqual(get_confirmed_count(), 2)

    def test_rolling_24h_window(self):  # 2 + 3
        now = self.NOW
        make_subscriber('in1@example.com', created=now - timedelta(hours=1))
        make_subscriber('in2@example.com', created=now - timedelta(hours=23, minutes=59))
        make_subscriber('edge@example.com', created=now - timedelta(hours=24))  # boundary is included
        make_subscriber('out1@example.com', created=now - timedelta(hours=24, seconds=1))
        make_subscriber('out2@example.com', created=now - timedelta(hours=48))
        make_subscriber('c1@example.com', created=now - timedelta(hours=2),
                        confirmed_at=now - timedelta(hours=1))
        make_subscriber('c2@example.com', created=now - timedelta(hours=40),
                        confirmed_at=now - timedelta(hours=30))
        stats = get_subscriber_stats(now=now)
        self.assertEqual(stats.last_24h, 4)  # in1, in2, edge, c1
        self.assertEqual(stats.last_24h_confirmed, 1)  # c1 only; c2 confirmed 30h ago

    def test_window_is_rolling_not_calendar_day(self):  # 2
        now = datetime(2026, 10, 29, 0, 30, tzinfo=UTC)  # just after midnight
        make_subscriber('late@example.com', created=datetime(2026, 10, 28, 23, 0, tzinfo=UTC))
        self.assertEqual(get_subscriber_stats(now=now).last_24h, 1)

    def test_public_stats_count_confirmed_only_with_boundaries(self):
        now = self.NOW
        make_subscriber('c1@example.com', confirmed_at=now - timedelta(hours=1))
        make_subscriber('c2@example.com', confirmed_at=now - timedelta(hours=24))   # edge: included
        make_subscriber('c3@example.com', confirmed_at=now - timedelta(days=3))
        make_subscriber('c4@example.com', confirmed_at=now - timedelta(days=7))     # edge: included
        make_subscriber('c5@example.com', confirmed_at=now - timedelta(days=7, seconds=1))
        make_subscriber('u1@example.com', created=now - timedelta(hours=1))         # unconfirmed: never counted
        stats = get_public_stats(now=now)
        self.assertEqual((stats.total, stats.last_24h, stats.last_7d), (5, 2, 4))


@monitor_settings
class SignupNotificationTests(TestCase):
    def signup(self, email='new@example.com', message=''):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse('subscriptions:subscribe'),
                {'email': email, 'phone': '', 'message': message},
            )

    def test_new_signup_recorded_once(self):  # 4
        self.signup()
        self.assertEqual(Subscriber.objects.count(), 1)
        self.assertEqual(SubscriberEvent.objects.count(), 1)

    def test_duplicate_submission_creates_nothing_new(self):  # 5
        self.signup('same@example.com')
        self.signup('same@example.com')
        self.assertEqual(Subscriber.objects.count(), 1)
        self.assertEqual(SubscriberEvent.objects.count(), 1)

    def test_notification_sent_for_new_signup(self):  # 6
        self.signup('new@example.com')
        sent = notification_mails()
        self.assertEqual(len(sent), 1)
        message = sent[0]
        self.assertEqual(message.to, ['owner@example.test'])
        self.assertIn('new@example.com', message.body)
        self.assertIn('Megerősített feliratkozók száma: 0', message.body)
        subscriber = Subscriber.objects.get()
        self.assertIn(f'http://testserver/admin/subscriptions/subscriber/{subscriber.pk}/change/', message.body)
        self.assertIsNotNone(SubscriberEvent.objects.get().notified_at)
        self.assertEqual(message.alternatives[0][1], 'text/html')
        self.assertIn('new@example.com', message.alternatives[0][0])

    def test_no_notification_for_duplicate(self):  # 7
        self.signup('same@example.com')
        self.signup('same@example.com')
        self.assertEqual(len(notification_mails()), 1)

    def test_email_failure_keeps_the_subscription(self):  # 8
        with mock.patch('monitor.notifications.send_mail', side_effect=OSError('smtp down')):
            with self.assertLogs('monitor.notifications', level='ERROR'):
                self.signup('new@example.com')
        self.assertEqual(Subscriber.objects.count(), 1)
        event = SubscriberEvent.objects.get()
        self.assertIsNone(event.notified_at)
        self.assertEqual(event.notify_error, 'OSError')

    @override_settings(MONITOR_NOTIFY_EMAIL='')
    def test_without_recipient_data_is_collected_but_no_email(self):
        self.signup('new@example.com')
        self.assertEqual(SubscriberEvent.objects.count(), 1)
        self.assertEqual(notification_mails(), [])


@monitor_settings
class DailyReportTests(TestCase):
    DAY = date(2026, 10, 28)

    def setUp(self):
        # A: before the day, B: first second of the day, C: last second of the day,
        # D: first second of the next day, E: old signup confirmed during the day.
        make_subscriber('a@example.com', created=datetime(2026, 10, 27, 23, 59, 59, tzinfo=BUD))
        make_subscriber('b@example.com', created=datetime(2026, 10, 28, 0, 0, 0, tzinfo=BUD),
                        confirmed_at=datetime(2026, 10, 28, 8, 0, tzinfo=BUD))
        make_subscriber('c@example.com', created=datetime(2026, 10, 28, 23, 59, 59, tzinfo=BUD),
                        confirmed_at=datetime(2026, 10, 29, 9, 0, tzinfo=BUD))
        make_subscriber('d@example.com', created=datetime(2026, 10, 29, 0, 0, 0, tzinfo=BUD))
        make_subscriber('e@example.com', created=datetime(2026, 10, 20, 10, 0, tzinfo=BUD),
                        confirmed_at=datetime(2026, 10, 28, 12, 0, tzinfo=BUD))

    def run_report(self, *args):
        call_command('send_daily_report', f'--date={self.DAY}', *args, stdout=StringIO())

    def test_date_range_and_numbers(self):  # 9
        self.run_report()
        report = DailyReport.objects.get(report_date=self.DAY)
        self.assertEqual(report.new_submissions, 2)   # b, c
        self.assertEqual(report.new_confirmed, 2)     # b, e
        self.assertEqual(report.total_confirmed, 3)   # b, c, e
        self.assertEqual(report.unconfirmed, 2)       # a, d
        sent = [m for m in mail.outbox if 'napi összesítő' in m.subject]
        self.assertEqual(len(sent), 1)
        self.assertIn('Új feliratkozások aznap: 2', sent[0].body)
        self.assertIn('Összes megerősített feliratkozó: 3', sent[0].body)
        self.assertIn('Megerősítésre váró jelentkezések: 2', sent[0].body)
        self.assertIn('http://testserver/admin/subscriptions/subscriber/', sent[0].body)

    def test_email_lists_that_days_signups_only(self):
        self.run_report()
        message = [m for m in mail.outbox if 'napi összesítő' in m.subject][0]
        html, mimetype = message.alternatives[0][0], message.alternatives[0][1]
        self.assertEqual(mimetype, 'text/html')
        for body in (message.body, html):
            self.assertIn('b@example.com', body)
            self.assertIn('c@example.com', body)
            for other in ('a@example.com', 'd@example.com', 'e@example.com'):
                self.assertNotIn(other, body)
        self.assertIn('[megerősítve]', message.body)             # b and c are both confirmed now
        self.assertNotIn('[megerősítésre vár]', message.body)
        self.assertNotIn('Nem volt új jelentkező', html)

    def test_email_escapes_html_but_not_plain_text(self):
        make_subscriber('a&b@example.com', created=datetime(2026, 10, 28, 10, 0, tzinfo=BUD))
        self.run_report()
        message = mail.outbox[0]
        self.assertIn('a&b@example.com', message.body)
        self.assertIn('[megerősítésre vár]', message.body)       # the extra signup is unconfirmed
        self.assertIn('a&amp;b@example.com', message.alternatives[0][0])

    def test_day_without_signups_says_so(self):
        call_command('send_daily_report', '--date=2026-10-15', stdout=StringIO())
        message = mail.outbox[0]
        self.assertIn('(nem volt új jelentkező)', message.body)
        self.assertIn('Nem volt új jelentkező', message.alternatives[0][0])

    def test_preview_writes_html_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'preview.html'
            self.run_report(f'--preview={target}')
            html = target.read_text(encoding='utf-8')
        self.assertIn('b@example.com', html)
        self.assertEqual(DailyReport.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_running_twice_does_not_duplicate(self):
        self.run_report()
        self.run_report()
        self.assertEqual(DailyReport.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_force_recomputes_and_resends(self):
        self.run_report()
        self.run_report('--force')
        self.assertEqual(DailyReport.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_dry_run_writes_and_sends_nothing(self):
        self.run_report('--dry-run')
        self.assertEqual(DailyReport.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    @override_settings(MONITOR_NOTIFY_EMAIL='')
    def test_report_recorded_without_recipient(self):
        self.run_report()
        self.assertEqual(DailyReport.objects.count(), 1)
        self.assertEqual(mail.outbox, [])

    def test_email_failure_is_reported_and_retryable(self):
        target = 'monitor.management.commands.send_daily_report.send_daily_report_email'
        with mock.patch(target, side_effect=OSError('smtp down')):
            with self.assertLogs('monitor.report', level='ERROR'):
                with self.assertRaises(CommandError):
                    self.run_report()
        report = DailyReport.objects.get()
        self.assertIsNone(report.emailed_at)
        self.assertEqual(report.email_error, 'OSError')
        self.run_report()  # retry succeeds
        report.refresh_from_db()
        self.assertIsNotNone(report.emailed_at)
        self.assertEqual(report.email_error, '')
        self.assertEqual(len(mail.outbox), 1)

    def test_invalid_date_is_a_clear_error(self):
        with self.assertRaises(CommandError):
            call_command('send_daily_report', '--date=nem-datum', stdout=StringIO())

    def test_default_day_is_yesterday_in_budapest(self):
        # 23:30 UTC on the 28th is already 00:30 on the 29th in Budapest (CET, UTC+1).
        self.assertEqual(default_report_date(datetime(2026, 10, 28, 23, 30, tzinfo=UTC)), date(2026, 10, 28))
        # 22:30 UTC on the 28th is still 23:30 on the 28th in Budapest.
        self.assertEqual(default_report_date(datetime(2026, 10, 28, 22, 30, tzinfo=UTC)), date(2026, 10, 27))

    def test_day_with_dst_change_is_25_hours_long(self):
        start, end = get_day_bounds(date(2026, 10, 25))  # clocks go back on this Sunday
        self.assertEqual(end.astimezone(UTC) - start.astimezone(UTC), timedelta(hours=25))


@monitor_settings
class PublicCounterTests(TestCase):
    def setUp(self):
        now = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
        make_subscriber('secret1@example.com', confirmed_at=now)
        make_subscriber('secret2@example.com', confirmed_at=now)
        make_subscriber('secret3@example.com', message='private note')

    def test_home_shows_confirmed_total(self):  # 10
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['public_stats'].total, 2)
        self.assertContains(response, '<span>ÖSSZESEN</span><span>2</span>')
        self.assertNotContains(response, 'confirmed subscribers')  # no counter in the subscribe section

    def test_home_exposes_no_internal_data(self):  # 11
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'secret')
        self.assertNotContains(response, '@example.com')
        self.assertNotContains(response, 'private note')
        self.assertNotIn('monitor_stats', response.context)
        text = response.content.decode().lower()
        for word in ('unconfirmed', 'pending'):
            self.assertNotIn(word, text)

    def test_signup_page_does_not_list_subscribers(self):  # 11
        response = self.client.get(reverse('subscriptions:subscribe'))
        self.assertNotContains(response, '@example.com')


@monitor_settings
class AdminAccessTests(TestCase):  # 12
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser('root', 'root@example.test', 'pw')
        self.plain_staff = User.objects.create_user('staff', 's@example.test', 'pw', is_staff=True)
        self.viewer = User.objects.create_user('viewer', 'v@example.test', 'pw', is_staff=True)
        self.viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label='subscriptions', codename='view_subscriber'))
        make_subscriber('a@example.com')
        DailyReport.objects.create(report_date=date(2026, 10, 28), new_submissions=1,
                                   new_confirmed=0, total_confirmed=0, unconfirmed=1)
        self.subscriber_list = reverse('admin:subscriptions_subscriber_changelist')
        self.event_list = reverse('admin:monitor_subscriberevent_changelist')
        self.report_list = reverse('admin:monitor_dailyreport_changelist')

    def test_anonymous_is_redirected_to_login(self):
        for url in (self.subscriber_list, self.event_list, self.report_list):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse('admin:login'), response['Location'])

    def test_staff_without_permission_is_denied(self):
        self.client.force_login(self.plain_staff)
        for url in (self.subscriber_list, self.event_list, self.report_list):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_subscriber_viewer_sees_stats_on_subscriber_list_only(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self.subscriber_list)
        self.assertContains(response, 'Confirmed subscribers (public counter)')
        self.assertEqual(self.client.get(self.event_list).status_code, 403)

    def test_superuser_sees_collector_with_stats_and_reports(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self.event_list)
        self.assertContains(response, 'Confirmed subscribers (public counter)')
        self.assertContains(response, 'Latest daily reports')
        self.assertEqual(self.client.get(self.report_list).status_code, 200)

    def test_collected_data_cannot_be_added_by_hand(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse('admin:monitor_subscriberevent_add')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:monitor_dailyreport_add')).status_code, 403)


@monitor_settings
class MessageFieldTests(TestCase):
    TEXT = 'Hello <b>there</b>'
    ESCAPED = 'Hello &lt;b&gt;there&lt;/b&gt;'

    def signup(self, message, email='new@example.com'):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse('subscriptions:subscribe'),
                {'email': email, 'phone': '', 'message': message},
            )

    def test_message_is_stored(self):
        self.signup(self.TEXT)
        self.assertEqual(Subscriber.objects.get().message, self.TEXT)

    def test_message_is_optional(self):
        response = self.signup('')
        self.assertEqual(Subscriber.objects.get().message, '')
        self.assertEqual(response.status_code, 302)

    def test_too_long_message_is_rejected(self):
        response = self.signup('x' * 1001)
        self.assertEqual(response.status_code, 200)  # form shown again with an error
        self.assertEqual(Subscriber.objects.count(), 0)

    def test_signup_form_has_a_message_field(self):
        response = self.client.get(reverse('subscriptions:subscribe'))
        self.assertContains(response, 'name="message"')

    def test_instant_email_contains_the_message(self):
        self.signup(self.TEXT)
        message = notification_mails()[0]
        self.assertIn(self.TEXT, message.body)
        self.assertIn(self.ESCAPED, message.alternatives[0][0])

    def test_instant_email_without_message_has_no_message_block(self):
        self.signup('')
        self.assertNotIn('Üzenet', notification_mails()[0].body)

    def test_visible_everywhere_in_admin(self):
        self.signup(self.TEXT)
        subscriber = Subscriber.objects.get()
        event = SubscriberEvent.objects.get()
        admin_user = get_user_model().objects.create_superuser('root', 'root@example.test', 'pw')
        self.client.force_login(admin_user)
        pages = {
            'subscriber list': reverse('admin:subscriptions_subscriber_changelist'),
            'subscriber detail': reverse('admin:subscriptions_subscriber_change', args=[subscriber.pk]),
            'collector list': reverse('admin:monitor_subscriberevent_changelist'),
            'collector detail': reverse('admin:monitor_subscriberevent_change', args=[event.pk]),
        }
        for name, url in pages.items():
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertContains(response, self.ESCAPED)  # shown, and HTML-escaped

    def test_admin_search_finds_by_message(self):
        self.signup('a very particular phrase')
        admin_user = get_user_model().objects.create_superuser('root', 'root@example.test', 'pw')
        self.client.force_login(admin_user)
        url = reverse('admin:subscriptions_subscriber_changelist')
        self.assertContains(self.client.get(url, {'q': 'particular'}), 'new@example.com')
        self.assertNotContains(self.client.get(url, {'q': 'nothing-like-this'}), 'new@example.com')

    def test_daily_report_lists_the_message(self):
        make_subscriber('m@example.com', created=datetime(2026, 10, 28, 10, 0, tzinfo=BUD),
                        message='Line one\nline two')
        call_command('send_daily_report', '--date=2026-10-28', stdout=StringIO())
        report_mail = mail.outbox[0]
        self.assertIn('Üzenet: Line one line two', report_mail.body)  # collapsed to one line
        self.assertIn('Line one line two', report_mail.alternatives[0][0])


@monitor_settings
class NodeBoxTests(TestCase):
    """The three numbers in the home page's NODE telemetry box."""

    def test_node_box_shows_total_24h_and_7_days(self):
        now = timezone.now()
        make_subscriber('c1@example.com', confirmed_at=now - timedelta(hours=1))
        make_subscriber('c2@example.com', confirmed_at=now - timedelta(days=3))
        make_subscriber('c3@example.com', confirmed_at=now - timedelta(days=10))
        make_subscriber('u1@example.com', created=now - timedelta(hours=1))  # unconfirmed
        response = self.client.get(reverse('home'))
        self.assertContains(response, '<span>ÖSSZESEN</span><span>3</span>')
        self.assertContains(response, '<span>ELMÚLT 24h</span><span>1</span>')
        self.assertContains(response, '<span>ELMÚLT 7 NAP</span><span>2</span>')
        self.assertNotContains(response, '125')
        self.assertNotContains(response, ' 12 C')

    def test_node_box_with_no_subscribers(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, '<span>ÖSSZESEN</span><span>0</span>')
        self.assertContains(response, '<span>ELMÚLT 24h</span><span>0</span>')


CONFIRM_SUBJECT = 'Confirm your subscription to Korrep'


def confirmation_mails():
    return [m for m in mail.outbox if m.subject == CONFIRM_SUBJECT]


@monitor_settings
class ConfirmationEmailTests(TestCase):
    def post(self, email='new@example.com', **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse('subscriptions:subscribe'),
                {'email': email, 'phone': '', 'message': '', **extra},
            )

    def test_confirmation_link_in_the_email_activates_the_subscriber(self):
        self.post('new@example.com')
        body = confirmation_mails()[0].body
        match = re.search(r'http://testserver(/subscriptions/confirm/[0-9a-f-]{36}/)', body)
        self.assertIsNotNone(match, body)
        response = self.client.get(match.group(1), follow=True)
        self.assertContains(response, 'Your subscription has been confirmed!')
        subscriber = Subscriber.objects.get()
        self.assertTrue(subscriber.is_active)
        self.assertIsNotNone(subscriber.activated_at)

    def test_resubmitting_an_unconfirmed_email_resends_the_confirmation(self):
        self.post('new@example.com')
        self.post('new@example.com')
        self.assertEqual(Subscriber.objects.count(), 1)
        self.assertEqual(SubscriberEvent.objects.count(), 1)
        self.assertEqual(len(confirmation_mails()), 2)
        self.assertEqual(len(notification_mails()), 1)  # the owner is told once

    def test_resubmission_can_add_a_message(self):
        self.post('new@example.com')
        self.post('new@example.com', message='Late addition')
        self.assertEqual(Subscriber.objects.get().message, 'Late addition')

    def test_confirmed_email_is_refused_and_gets_no_mail(self):
        make_subscriber('done@example.com', confirmed_at=datetime(2026, 10, 1, tzinfo=UTC))
        response = self.post('done@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already subscribed')
        self.assertEqual(confirmation_mails(), [])

    def test_smtp_failure_keeps_the_signup_and_tells_the_visitor(self):
        with mock.patch('subscriptions.views.send_mail', side_effect=OSError('smtp down')):
            with self.assertLogs('subscriptions.views', level='ERROR'):
                response = self.client.post(
                    reverse('subscriptions:subscribe'),
                    {'email': 'new@example.com', 'phone': '', 'message': ''},
                    follow=True,
                )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'could not send the confirmation email')
        self.assertEqual(Subscriber.objects.count(), 1)


@monitor_settings
class ReplyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser('root', 'root@example.test', 'pw')
        self.viewer = User.objects.create_user('viewer', 'v@example.test', 'pw', is_staff=True)
        self.viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label='subscriptions', codename='view_subscriber'))
        self.editor = User.objects.create_user('editor', 'e@example.test', 'pw', is_staff=True)
        self.editor.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='subscriptions',
            codename__in=['view_subscriber', 'change_subscriber']))
        self.subscriber = make_subscriber('guest@example.com', message='Please call <me>',
                                          confirmed_at=datetime(2026, 10, 1, tzinfo=UTC))
        self.url = reverse('admin:subscriptions_subscriber_reply', args=[self.subscriber.pk])
        self.payload = {'subject': 'Welcome to Korrep', 'body': 'Thanks for writing!'}

    # --- access
    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('admin:login'), response['Location'])

    def test_view_only_staff_cannot_reply(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.post(self.url, self.payload)
        self.assertEqual(mail.outbox, [])

    def test_unknown_subscriber_is_404(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:subscriptions_subscriber_reply', args=[99999]))
        self.assertEqual(response.status_code, 404)

    # --- form
    def test_form_shows_recipient_and_their_message_escaped(self):
        self.client.force_login(self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'guest@example.com')
        self.assertContains(response, 'Please call &lt;me&gt;')
        self.assertContains(response, 'name="subject"')
        self.assertContains(response, 'name="body"')
        self.assertNotContains(response, 'not confirmed yet')

    def test_unconfirmed_address_gets_a_warning(self):
        other = make_subscriber('unknown@example.com')
        self.client.force_login(self.superuser)
        url = reverse('admin:subscriptions_subscriber_reply', args=[other.pk])
        self.assertContains(self.client.get(url), 'not confirmed yet')

    # --- sending
    def test_reply_is_sent_and_logged(self):
        self.client.force_login(self.superuser)
        before = get_subscriber_stats().unanswered
        response = self.client.post(self.url, self.payload)
        self.assertRedirects(response, reverse('admin:subscriptions_subscriber_change',
                                               args=[self.subscriber.pk]))
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ['guest@example.com'])
        self.assertEqual(sent.from_email, 'owner@example.test')
        self.assertEqual(sent.subject, 'Welcome to Korrep')
        self.assertEqual(sent.body, 'Thanks for writing!')
        reply = SentReply.objects.get()
        self.assertEqual((reply.subscriber, reply.sent_by), (self.subscriber, self.superuser))
        self.assertEqual(get_subscriber_stats().unanswered, before - 1)

    def test_failed_send_records_nothing_and_keeps_the_text(self):
        self.client.force_login(self.superuser)
        with mock.patch('monitor.replies.send_mail', side_effect=OSError('smtp down')):
            with self.assertLogs('subscriptions.admin', level='ERROR'):
                response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'could not be sent')
        self.assertContains(response, 'Thanks for writing!')  # not lost
        self.assertEqual(SentReply.objects.count(), 0)

    def test_header_injection_in_subject_is_rejected(self):
        self.client.force_login(self.superuser)
        response = self.client.post(self.url, {'subject': 'Hi\nBcc: evil@example.com', 'body': 'x'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'single line')
        self.assertEqual(mail.outbox, [])
        self.assertEqual(SentReply.objects.count(), 0)

    def test_empty_body_is_rejected(self):
        self.client.force_login(self.superuser)
        response = self.client.post(self.url, {'subject': 'Hi', 'body': '   '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox, [])

    # --- admin visibility of the reply state
    def test_list_filter_and_history(self):
        other = make_subscriber('other@example.com')
        self.client.force_login(self.superuser)
        self.client.post(self.url, self.payload)
        listing = reverse('admin:subscriptions_subscriber_changelist')
        not_replied = self.client.get(listing, {'replied': 'no'})
        self.assertContains(not_replied, 'other@example.com')
        self.assertNotContains(not_replied, 'guest@example.com')
        replied = self.client.get(listing, {'replied': 'yes'})
        self.assertContains(replied, 'guest@example.com')
        self.assertNotContains(replied, 'other@example.com')
        detail = self.client.get(reverse('admin:subscriptions_subscriber_change', args=[self.subscriber.pk]))
        self.assertContains(detail, 'Welcome to Korrep')
        self.assertContains(detail, 'Thanks for writing!')
        self.assertContains(detail, self.url)  # the Reply button
        self.assertEqual(other.replies.count(), 0)

    def test_unanswered_count_in_stats(self):
        make_subscriber('second@example.com')
        self.assertEqual(get_subscriber_stats().unanswered, 2)
        self.client.force_login(self.superuser)
        self.client.post(self.url, self.payload)
        self.assertEqual(get_subscriber_stats().unanswered, 1)

    # --- links in the emails and in the collector
    def signup(self, email='fresh@example.com'):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('subscriptions:subscribe'),
                             {'email': email, 'phone': '', 'message': ''})
        return Subscriber.objects.get(email=email)

    def test_instant_email_links_the_address_to_the_reply_form(self):
        fresh = self.signup()
        reply_url = f'http://testserver/admin/subscriptions/subscriber/{fresh.pk}/reply/'
        message = notification_mails()[0]
        self.assertIn(reply_url, message.body)
        self.assertIn(f'href="{reply_url}"', message.alternatives[0][0])
        self.assertIn('Még nem kapott választ: 2 jelentkező', message.body)  # guest + fresh
        self.assertIn('?replied=no', message.body)

    def test_collector_email_column_links_to_the_reply_form(self):
        fresh = self.signup()
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:monitor_subscriberevent_changelist'))
        self.assertContains(response, reverse('admin:subscriptions_subscriber_reply', args=[fresh.pk]))

    def test_daily_email_has_reply_links_and_reply_state(self):
        answered = make_subscriber('answered@example.com',
                                   created=datetime(2026, 10, 28, 9, 0, tzinfo=BUD))
        waiting = make_subscriber('waiting@example.com',
                                  created=datetime(2026, 10, 28, 10, 0, tzinfo=BUD))
        SentReply.objects.create(subscriber=answered, subject='Hi', body='Hello')
        call_command('send_daily_report', '--date=2026-10-28', stdout=StringIO())
        message = mail.outbox[0]
        waiting_url = f'http://testserver/admin/subscriptions/subscriber/{waiting.pk}/reply/'
        answered_url = f'http://testserver/admin/subscriptions/subscriber/{answered.pk}/reply/'
        self.assertIn(waiting_url, message.body)
        self.assertNotIn(answered_url, message.body)       # already answered: no reply link
        self.assertIn('Válasz: elküldve', message.body)
        self.assertIn('Még nem kapott választ: 2 jelentkező', message.body)  # guest + waiting
        self.assertIn(f'href="{waiting_url}"', message.alternatives[0][0])


class SiteModeTests(SimpleTestCase):
    """The SITE_MODE switch that decides where email links point."""

    def test_local_mode_points_at_localhost(self):
        self.assertEqual(resolve_site_url('local'), 'http://localhost:8000')
        self.assertEqual(LOCAL_SITE_URL, 'http://localhost:8000')

    def test_server_mode_points_at_pythonanywhere(self):
        self.assertEqual(resolve_site_url('server'), 'https://korrep.pythonanywhere.com')
        self.assertEqual(SERVER_SITE_URL, 'https://korrep.pythonanywhere.com')

    def test_mode_is_case_and_space_insensitive(self):
        self.assertEqual(resolve_site_url('  SERVER '), SERVER_SITE_URL)

    def test_old_site_url_is_ignored_unless_mode_is_custom(self):
        # a leftover SITE_URL=http://localhost:8000 in .env must not defeat the switch
        self.assertEqual(resolve_site_url('server', custom_url='http://localhost:8000'), SERVER_SITE_URL)
        self.assertEqual(resolve_site_url('custom', custom_url='https://example.org/'), 'https://example.org')

    def test_trailing_slash_is_removed(self):
        self.assertEqual(resolve_site_url('local', local_url='http://localhost:8000/'), 'http://localhost:8000')

    def test_custom_mode_needs_an_address(self):
        with self.assertRaises(ValueError):
            resolve_site_url('custom')

    def test_unknown_mode_is_an_error(self):
        for bad in ('', 'prod', 'sever', None):
            with self.subTest(mode=bad):
                with self.assertRaises(ValueError):
                    resolve_site_url(bad)

    def test_address_needs_a_scheme(self):
        with self.assertRaises(ValueError):
            resolve_site_url('custom', custom_url='korrep.pythonanywhere.com')


@monitor_settings
class CheckEmailSetupTests(TestCase):
    def run_check(self, *args):
        out = StringIO()
        call_command('check_email_setup', *args, stdout=out)
        return out.getvalue()

    @override_settings(SITE_MODE='server', SITE_URL='https://korrep.pythonanywhere.com',
                       ALLOWED_HOSTS=['korrep.pythonanywhere.com'])
    def test_shows_mode_and_link_base(self):
        output = self.run_check()
        self.assertIn('server', output)
        self.assertIn('https://korrep.pythonanywhere.com', output)
        self.assertNotIn('ALLOWED_HOSTS-ban', output)  # host is allowed: no warning

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                       EMAIL_HOST_PASSWORD='s3cret-app-password')
    def test_never_prints_the_password(self):
        output = self.run_check()
        self.assertNotIn('s3cret-app-password', output)
        self.assertIn('be van állítva', output)

    @override_settings(SITE_URL='https://korrep.pythonanywhere.com', ALLOWED_HOSTS=['localhost'])
    def test_warns_when_the_link_host_is_not_allowed(self):
        self.assertIn('ALLOWED_HOSTS-ban', self.run_check())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                       SITE_URL='http://localhost:8000', EMAIL_HOST_PASSWORD='x')
    def test_warns_about_localhost_links_in_real_emails(self):
        self.assertIn('localhost-ra', self.run_check())

    def test_warns_when_email_is_not_really_sent(self):
        self.assertIn('Nem SMTP backend', self.run_check())  # locmem in tests

    @override_settings(SITE_MODE='server', DEBUG=True)
    def test_warns_about_debug_on_the_server(self):
        self.assertIn('DEBUG', self.run_check())

    def test_send_test_sends_one_mail_to_the_recipient(self):
        output = self.run_check('--send-test')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner@example.test'])
        self.assertIn('http://testserver', mail.outbox[0].body)
        self.assertIn('Teszt email elküldve', output)

    @override_settings(MONITOR_NOTIFY_EMAIL='')
    def test_send_test_needs_a_recipient(self):
        with self.assertRaises(CommandError):
            self.run_check('--send-test')
        self.assertEqual(mail.outbox, [])

    def test_send_test_failure_is_reported(self):
        target = 'monitor.management.commands.check_email_setup.send_mail'
        with mock.patch(target, side_effect=OSError('no route')):
            with self.assertRaises(CommandError) as ctx:
                self.run_check('--send-test')
        self.assertIn('OSError', str(ctx.exception))
