from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CustomUser, UserProfile


@receiver(post_save, sender=CustomUser)
def ensure_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                "full_name": instance.get_full_name() or instance.username or "FoodGuard User",
            },
        )
        return

    UserProfile.objects.get_or_create(
        user=instance,
        defaults={
            "full_name": instance.get_full_name() or instance.username or "FoodGuard User",
        },
    )
