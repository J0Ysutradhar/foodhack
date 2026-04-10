from django.apps import AppConfig


class FoodguardappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "foodguardapp"

    def ready(self):
        from . import signals  # noqa: F401
