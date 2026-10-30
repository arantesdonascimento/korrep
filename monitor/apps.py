from django.apps import AppConfig


class MonitorConfig(AppConfig):
    name = 'monitor'
    verbose_name = 'Monitor'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from . import signals  # noqa: F401  (connects the post_save receiver)
