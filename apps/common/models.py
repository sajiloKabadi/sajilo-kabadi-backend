import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Base class every domain model should inherit from."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDPrimaryKeyModel(models.Model):
    """Use UUID public ids instead of leaking sequential integer ids."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel):
    class Meta:
        abstract = True


class IdempotencyKey(models.Model):
    """First response to a POST sent with an `Idempotency-Key` header, replayed
    for any repeat of the same key by the same user on the same path."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    key = models.CharField(max_length=64)
    scope = models.CharField(max_length=200)
    status_code = models.PositiveSmallIntegerField()
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "common_idempotency_key"
        constraints = [models.UniqueConstraint(fields=["user", "key", "scope"], name="unique_idempotency_key")]

    def __str__(self):
        return f"{self.scope} [{self.key}]"
