"""Replying to a subscriber from the Django admin.

The message goes out through the same SMTP account as every other email
(DEFAULT_FROM_EMAIL), and is logged as a SentReply so the admin can see who
has already been answered.
"""
from django import forms
from django.conf import settings
from django.core.mail import send_mail

from .models import SentReply


class ReplyForm(forms.Form):
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'vTextField'}),
    )
    body = forms.CharField(
        label='Message',
        max_length=5000,
        widget=forms.Textarea(attrs={'class': 'vLargeTextField', 'rows': 12}),
    )

    def clean_subject(self):
        subject = self.cleaned_data['subject']
        if '\n' in subject or '\r' in subject:
            raise forms.ValidationError('The subject must be a single line.')
        return subject


def default_subject(subscriber):
    return 'Re: Korrep'


def send_reply(subscriber, subject, body, user):
    """Send the reply, then log it. Raises on failure and logs nothing then."""
    send_mail(
        subject,
        body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[subscriber.email],
        fail_silently=False,
    )
    return SentReply.objects.create(
        subscriber=subscriber,
        subject=subject,
        body=body,
        sent_by=user if getattr(user, 'pk', None) else None,
    )
