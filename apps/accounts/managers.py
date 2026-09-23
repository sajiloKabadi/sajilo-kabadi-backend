from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Phone-number based user manager. No usable password by default."""

    use_in_migrations = True

    def _create_user(self, phone_number, **extra_fields):
        if not phone_number:
            raise ValueError("Users must have a phone number")
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone_number, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone_number, **extra_fields)

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        user = self._create_user(phone_number, **extra_fields)
        if password:
            user.set_password(password)
            user.save(using=self._db)
        return user
