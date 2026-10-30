from django.conf import settings
from django.db import models


class SubscriberEvent(models.Model):
    """Inbox entry created once for every newly saved Subscriber.

    This is the "collector" the admin can open. It is created even when no
    notification email address is configured. Deleting a Subscriber deletes
    its event too, so no personal data outlives the subscriber row.
    """

    subscriber = models.OneToOneField(
        'subscriptions.Subscriber',
        on_delete=models.CASCADE,
        related_name='monitor_event',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    total_confirmed = models.PositiveIntegerField(
        help_text='Confirmed subscribers at the moment of the signup.'
    )
    unconfirmed = models.PositiveIntegerField(
        help_text='Unconfirmed subscribers at the moment of the signup.'
    )
    notified_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the notification email was sent. Empty = not emailed.',
    )
    notify_error = models.CharField(
        max_length=200, blank=True,
        help_text='Error class of a failed notification email (no addresses).',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'subscriber notification'
        verbose_name_plural = 'subscriber notifications'

    def __str__(self):
        return f'Signup #{self.subscriber_id} at {self.created_at:%Y-%m-%d %H:%M}'


class DailyReport(models.Model):
    """One row per reported calendar day (in MONITOR_REPORT_TIMEZONE).

    The unique report_date makes the daily job idempotent. The two totals are
    a snapshot taken when the report was generated.
    """

    report_date = models.DateField(unique=True)
    new_submissions = models.PositiveIntegerField(
        help_text='Signups submitted on report_date.'
    )
    new_confirmed = models.PositiveIntegerField(
        help_text='Subscribers who confirmed their email on report_date.'
    )
    total_confirmed = models.PositiveIntegerField(
        help_text='All confirmed subscribers when the report was generated.'
    )
    unconfirmed = models.PositiveIntegerField(
        help_text='Subscribers waiting for email confirmation when generated.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    emailed_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the report email was sent. Empty = not emailed.',
    )
    email_error = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-report_date']
        verbose_name = 'daily report'
        verbose_name_plural = 'daily reports'

    def __str__(self):
        return f'Report {self.report_date}'


class SentReply(models.Model):
    """A reply the admin sent to a subscriber from the Django admin.

    Kept so the admin can see who has not been answered yet and what was
    said. Deleting the Subscriber deletes its replies too.
    """

    subscriber = models.ForeignKey(
        'subscriptions.Subscriber',
        on_delete=models.CASCADE,
        related_name='replies',
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'sent reply'
        verbose_name_plural = 'sent replies'

    def __str__(self):
        return f'Reply to #{self.subscriber_id}: {self.subject}'
