from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _after_migrate(sender, **kwargs):
    from .roles import sync_roles

    sync_roles()


class CoreConfig(AppConfig):
    name = "apps.core"
    verbose_name = "Hệ thống"

    def ready(self):
        post_migrate.connect(_after_migrate, sender=self)
