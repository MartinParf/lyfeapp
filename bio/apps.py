from django.apps import AppConfig


class BioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bio"

    def ready(self):
        from . import tasks  # noqa: F401