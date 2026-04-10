from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameModelBackend(ModelBackend):
    """Allow authentication with either email or username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = kwargs.get("email") or username
        if not identifier or not password:
            return None

        user_model = get_user_model()
        user = None
        if "@" in identifier:
            try:
                user = user_model._default_manager.get(email__iexact=identifier)
            except user_model.DoesNotExist:
                user = None
        else:
            try:
                user = user_model._default_manager.get(username__iexact=identifier)
            except user_model.DoesNotExist:
                user = None

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
