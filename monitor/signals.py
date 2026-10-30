from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from subscriptions.models import Subscriber

from .notifications import handle_new_subscriber


@receiver(post_save, sender=Subscriber, dispatch_uid='monitor_new_subscriber')
def on_subscriber_saved(sender, instance, created, raw=False, **kwargs):
    # Only genuinely new rows. A duplicate submission never creates a row, so
    # it never reaches this point. on_commit => runs only after the commit.
    if not created or raw:
        return
    pk = instance.pk
    transaction.on_commit(lambda: handle_new_subscriber(pk))
