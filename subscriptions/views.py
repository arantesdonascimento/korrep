import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Subscriber
from .forms import SubscriptionForm

logger = logging.getLogger(__name__)


def subscribe(request):
    if request.method == 'POST':
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            phone = form.cleaned_data['phone']
            visitor_message = form.cleaned_data['message']
            subscriber, created = Subscriber.objects.get_or_create(
                email=email,
                defaults={'phone': phone, 'message': visitor_message, 'is_active': False}
            )
            if not created and subscriber.is_active:
                messages.info(request, 'This email is already subscribed.')
                return redirect('subscriptions:success')
            if not created and not subscriber.is_active:
                # Update phone and message if provided
                if phone:
                    subscriber.phone = phone
                if visitor_message:
                    subscriber.message = visitor_message
                if phone or visitor_message:
                    subscriber.save()
            confirmation_url = f"{settings.SITE_URL}/subscriptions/confirm/{subscriber.confirmation_token}/"
            subject = 'Confirm your subscription to Korrep'
            message = f'''Hello,

Thank you for subscribing to Korrep!

Please confirm your subscription by clicking the link below:
{confirmation_url}

If you did not request this subscription, please ignore this email.

Best regards,
The Korrep Team
'''
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [subscriber.email],
                    fail_silently=False,
                )
            except Exception:
                # The signup itself is saved; only the confirmation email failed.
                logger.exception('Confirmation email could not be sent (subscriber id=%s)', subscriber.pk)
                messages.error(
                    request,
                    'Your details were saved, but we could not send the confirmation email '
                    'right now. Please submit the form again in a few minutes.',
                )
                return redirect('subscriptions:success')
            messages.success(request, 'Please check your email to confirm your subscription.')
            return redirect('subscriptions:success')
    else:
        form = SubscriptionForm()
    return render(request, 'subscriptions/subscribe.html', {'form': form})


def confirm(request, token):
    subscriber = get_object_or_404(Subscriber, confirmation_token=token)
    if not subscriber.is_active:
        subscriber.is_active = True
        subscriber.activated_at = timezone.now()
        subscriber.save()
        messages.success(request, 'Your subscription has been confirmed!')
    else:
        messages.info(request, 'Your subscription is already confirmed.')
    return redirect('subscriptions:success')


def success(request):
    return render(request, 'subscriptions/success.html')
