import os
from urllib.parse import urlparse

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.http.request import validate_host

from monitor.notifications import get_notify_recipient


class Command(BaseCommand):
    help = ('Show where the links in emails point and how email is sent, with warnings '
            'for typical mistakes. Optionally send one test email.')

    def add_arguments(self, parser):
        parser.add_argument('--send-test', action='store_true',
                            help='Send one test email to MONITOR_NOTIFY_EMAIL.')

    def handle(self, *args, **options):
        backend = settings.EMAIL_BACKEND
        is_smtp = backend.endswith('smtp.EmailBackend')
        host = urlparse(settings.SITE_URL).hostname or ''
        recipient = get_notify_recipient()

        rows = [
            ('SITE_MODE', settings.SITE_MODE),
            ('SITE_URL (linkek alapja)', settings.SITE_URL),
            ('DEBUG', settings.DEBUG),
            ('ALLOWED_HOSTS', ', '.join(settings.ALLOWED_HOSTS) or '(üres)'),
            ('EMAIL_BACKEND', backend),
        ]
        if is_smtp:
            rows += [
                ('SMTP szerver', f'{settings.EMAIL_HOST}:{settings.EMAIL_PORT} '
                                 f'(TLS={settings.EMAIL_USE_TLS}, SSL={settings.EMAIL_USE_SSL})'),
                ('SMTP felhasználó', settings.EMAIL_HOST_USER or '(üres)'),
                ('SMTP jelszó', 'be van állítva' if settings.EMAIL_HOST_PASSWORD else '(üres)'),
            ]
        rows += [
            ('DEFAULT_FROM_EMAIL (küldő)', settings.DEFAULT_FROM_EMAIL),
            ('MONITOR_NOTIFY_EMAIL (fogadó)', recipient or '(üres: nem megy értesítő)'),
        ]
        for label, value in rows:
            self.stdout.write(f'{label:32} {value}')

        warnings = []
        if host and not validate_host(host, settings.ALLOWED_HOSTS):
            warnings.append(f'A SITE_URL gépneve ({host}) nincs az ALLOWED_HOSTS-ban, '
                            'a linkre kattintva a Django elutasítaná a kérést.')
        if is_smtp and host in ('localhost', '127.0.0.1'):
            warnings.append('Valódi levelek mennek ki, de a bennük lévő linkek a localhost-ra '
                            'mutatnak: ez csak azon a gépen működik, ahol a szerver fut.')
        if is_smtp and not settings.EMAIL_HOST_PASSWORD:
            warnings.append('SMTP backend van, de az EMAIL_HOST_PASSWORD üres.')
        if not is_smtp:
            warnings.append('Nem SMTP backend: a levelek nem mennek ki, a terminálba '
                            'íródnak (vagy el sem küldődnek).')
        if settings.SITE_MODE == 'server' and settings.DEBUG:
            warnings.append('SITE_MODE=server mellett a DEBUG be van kapcsolva: élesben legyen False.')
        legacy = os.environ.get('SITE_URL')
        if legacy and settings.SITE_MODE != 'custom':
            warnings.append(f'A .env-ben van SITE_URL={legacy}, de SITE_MODE={settings.SITE_MODE} '
                            'mellett figyelmen kívül marad. Törölheted.')
        for warning in warnings:
            self.stdout.write(self.style.WARNING(f'FIGYELEM: {warning}'))

        if options['send_test']:
            if not recipient:
                raise CommandError('A teszthez állítsd be a MONITOR_NOTIFY_EMAIL-t.')
            try:
                send_mail(
                    'Korrep teszt email',
                    'Ha ezt a levelet látod, a küldés működik.\n'
                    f'A levelekben lévő linkek alapja: {settings.SITE_URL}\n',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
            except Exception as exc:
                raise CommandError(f'A teszt email küldése nem sikerült: {type(exc).__name__}: {exc}')
            self.stdout.write(self.style.SUCCESS(f'Teszt email elküldve: {recipient}'))
