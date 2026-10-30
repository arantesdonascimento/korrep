import logging
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from monitor.models import DailyReport
from monitor.notifications import (
    get_notify_recipient,
    render_daily_report_email,
    send_daily_report_email,
)
from monitor.services import (
    default_report_date,
    get_day_bounds,
    get_period_stats,
    get_subscriber_stats,
)

logger = logging.getLogger('monitor.report')


class Command(BaseCommand):
    help = (
        'Record the daily subscriber report (previous calendar day in '
        'MONITOR_REPORT_TIMEZONE) and email it if MONITOR_NOTIFY_EMAIL is set. '
        'Safe to run repeatedly: one report per day, one email per report.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--date', help='Report day, YYYY-MM-DD (default: yesterday).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Print the numbers; write and send nothing.')
        parser.add_argument('--preview', metavar='FILE',
                            help='Write the report email as an HTML file you can open in a '
                                 'browser. Writes nothing to the database, sends nothing.')
        parser.add_argument('--force', action='store_true',
                            help='Recompute an existing report and send it again.')

    def handle(self, *args, **options):
        if options['date']:
            try:
                day = date.fromisoformat(options['date'])
            except ValueError:
                raise CommandError('--date must look like YYYY-MM-DD.')
        else:
            day = default_report_date()

        start, end = get_day_bounds(day)
        numbers = get_period_stats(start, end)
        stats = get_subscriber_stats()
        numbers['total_confirmed'] = stats.total
        numbers['unconfirmed'] = stats.unconfirmed

        summary = ', '.join(f'{k}={v}' for k, v in numbers.items())
        if options['preview']:
            _, text, html = render_daily_report_email(DailyReport(report_date=day, **numbers))
            path = Path(options['preview'])
            path.write_text(html, encoding='utf-8')
            self.stdout.write(text)
            self.stdout.write(f'HTML preview written to {path.resolve()}')
            return
        if options['dry_run']:
            self.stdout.write(f'[dry-run] {day}: {summary}')
            return

        report, created = DailyReport.objects.get_or_create(report_date=day, defaults=numbers)
        if not created and options['force']:
            for field, value in numbers.items():
                setattr(report, field, value)
            report.emailed_at = None
            report.email_error = ''
            report.save()
        elif not created:
            self.stdout.write(f'Report for {day} already recorded.')
        else:
            self.stdout.write(f'Report for {day} recorded: {summary}')
        logger.info('Daily report %s recorded (created=%s)', day, created)

        recipient = get_notify_recipient()
        if not recipient:
            self.stdout.write('MONITOR_NOTIFY_EMAIL is not set: email skipped (see Django admin > Monitor).')
            return

        # Claim the send atomically so two overlapping runs cannot both email.
        claimed = DailyReport.objects.filter(pk=report.pk, emailed_at__isnull=True).update(
            emailed_at=timezone.now()
        )
        if not claimed:
            self.stdout.write(f'Report for {day} was already emailed.')
            return
        report.refresh_from_db()
        try:
            send_daily_report_email(report, recipient)
        except Exception as exc:
            logger.exception('Daily report email failed (%s)', day)
            DailyReport.objects.filter(pk=report.pk).update(
                emailed_at=None, email_error=type(exc).__name__[:200]
            )
            raise CommandError(f'Email sending failed: {type(exc).__name__}. The report is saved; run again to retry.')
        DailyReport.objects.filter(pk=report.pk).update(email_error='')
        self.stdout.write(self.style.SUCCESS(f'Report for {day} emailed.'))
