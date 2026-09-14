from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveModelBackend(ModelBackend):
    """
    Username lookup is case-insensitive at login — 'Cashier1' and 'cashier1'
    authenticate the same account. Uniqueness is still enforced
    case-insensitively at account-creation time (see
    StaffUserCreateSerializer.validate_username), so there's never more than
    one account this could ambiguously match. Storage keeps whatever case the
    Owner typed when creating the account — only the lookup is relaxed.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None
        try:
            user = UserModel._default_manager.get(username__iexact=username)
        except UserModel.DoesNotExist:
            # Hash the password anyway — mirrors ModelBackend's own behavior —
            # so a nonexistent username doesn't respond measurably faster
            # than a wrong password (timing side-channel).
            UserModel().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
