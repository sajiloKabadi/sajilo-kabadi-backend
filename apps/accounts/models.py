from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """Phone number is the credential; there is no separate username.

    `phone_number` is the 10-digit national number ("9841234471"); the
    country code is stored separately, matching the API contract.
    """

    class Role(models.TextChoices):
        SELLER = "seller", "Seller"
        COLLECTOR = "collector", "Collector"
        ADMIN = "admin", "Admin"

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        NEPALI = "ne", "Nepali"

    phone_number = models.CharField(max_length=20, unique=True, db_index=True)
    country_code = models.CharField(max_length=5, default="+977")
    full_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(null=True, blank=True)  # noqa: DJ001 - contract returns "email": null
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SELLER)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.ENGLISH)
    is_phone_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "accounts_user"

    def __str__(self):
        return self.full_name or self.phone_number

    @property
    def first_name(self) -> str | None:
        parts = self.full_name.split()
        return parts[0] if parts else None

    @property
    def initials(self) -> str | None:
        parts = self.full_name.split()
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0][0].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def is_profile_complete(self) -> bool:
        return bool(self.full_name.strip())


class OTPRequest(BaseModel):
    """A single OTP challenge. Its UUID `id` is the `otp_request_id` the
    client sends back on verify and resend.

    Only an HMAC of the code is stored (see apps.accounts.otp), never the
    code itself. Each SMS sent is one row, so resends create a new row and
    invalidate the old one; rate limits count rows.
    """

    class Purpose(models.TextChoices):
        LOGIN = "login", "Login / signup"
        WITHDRAW = "withdraw", "Wallet withdrawal confirmation"

    phone_number = models.CharField(max_length=20, db_index=True)
    country_code = models.CharField(max_length=5, default="+977")
    role = models.CharField(max_length=20, choices=User.Role.choices, default=User.Role.SELLER)
    # null = the client did not send a language, so the user's saved one is kept
    language = models.CharField(max_length=2, choices=User.Language.choices, null=True, blank=True)  # noqa: DJ001
    code_hash = models.CharField(max_length=64)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.LOGIN)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "accounts_otp_request"
        indexes = [
            models.Index(fields=["phone_number", "purpose"]),
            models.Index(fields=["phone_number", "created_at"]),
        ]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_open(self) -> bool:
        return self.consumed_at is None and self.invalidated_at is None and self.locked_at is None


class UserDevice(BaseModel):
    """Device reported on sign-in, for push notifications and the session list."""

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    platform = models.CharField(max_length=10, choices=Platform.choices, blank=True)
    device_id = models.CharField(max_length=255, blank=True)
    fcm_token = models.TextField(null=True, blank=True)  # noqa: DJ001 - contract: may be null
    app_version = models.CharField(max_length=32, blank=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "accounts_user_device"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "device_id"],
                condition=~models.Q(device_id=""),
                name="unique_device_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.platform or 'unknown'} {self.device_id}"
