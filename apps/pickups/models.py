from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Pickup(BaseModel):
    """A booking and its lifecycle (contract 8.1).

    Address parts are copied at booking so later edits never rewrite a
    pickup. Money fields are integer rupees computed by the server."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        MATCHED = "matched", "Matched"
        ON_THE_WAY = "on_the_way", "On the way"
        ARRIVED = "arrived", "Arrived"
        WEIGHING = "weighing", "Weighing"
        COMPLETED = "completed", "Completed"
        DISPUTED = "disputed", "Disputed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    class DeliveryOption(models.TextChoices):
        SELF_DROPOFF = "self_dropoff", "Self drop-off"
        COLLECTOR_PICKUP = "collector_pickup", "Collector pickup"
        TRUCK_HELPER = "truck_helper", "Truck + helper"

    class Settlement(models.TextChoices):
        PAID = "paid", "Paid"
        HELD = "held", "Held"

    class CancelReason(models.TextChoices):
        CHANGED_MIND = "changed_mind", "Changed mind"
        SOLD_ELSEWHERE = "sold_elsewhere", "Sold elsewhere"
        WRONG_TIME = "wrong_time", "Wrong time"
        OTHER = "other", "Other"

    ref = models.CharField(max_length=16, unique=True)
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pickups_as_seller")
    collector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pickups_as_collector",
    )
    address = models.ForeignKey("sellers.Address", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    area = models.CharField(max_length=80)
    address_line = models.CharField(max_length=255)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)

    delivery_option = models.CharField(max_length=20, choices=DeliveryOption.choices)
    scheduled_date = models.DateField()
    slot_start = models.DateTimeField(null=True, blank=True)
    slot_end = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)

    approx_weight_kg = models.DecimalField(max_digits=8, decimal_places=1)
    estimated_total = models.PositiveIntegerField()
    delivery_fee = models.PositiveIntegerField(default=0)
    estimated_payout = models.PositiveIntegerField()
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    collector_earning = models.PositiveIntegerField(default=0)

    final_total = models.PositiveIntegerField(null=True, blank=True)
    final_weight_kg = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    payout_method = models.CharField(max_length=10, blank=True)
    settlement_status = models.CharField(max_length=10, choices=Settlement.choices, blank=True)
    # Payout waiting on support while a dispute is open (wallet held_amount).
    held_payout = models.PositiveIntegerField(null=True, blank=True)

    matched_at = models.DateTimeField(null=True, blank=True)
    on_the_way_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    weighing_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    disputed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=20, choices=CancelReason.choices, blank=True)
    cancel_note = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "pickups_pickup"
        indexes = [
            models.Index(fields=["seller", "status", "slot_start"], name="pickup_seller_idx"),
            models.Index(fields=["collector", "status"], name="pickup_collector_idx"),
            models.Index(fields=["status", "slot_end"], name="pickup_status_slot_idx"),
            models.Index(fields=["status", "lat", "lng"], name="pickup_open_geo_idx"),
            models.Index(fields=["settlement_status", "seller"], name="pickup_settlement_idx"),
        ]

    def __str__(self):
        return f"{self.ref} ({self.status})"


# Seller's "active" list (contract 8.5): requested to weighing, plus disputed.
ACTIVE_STATUSES = (
    Pickup.Status.REQUESTED,
    Pickup.Status.MATCHED,
    Pickup.Status.ON_THE_WAY,
    Pickup.Status.ARRIVED,
    Pickup.Status.WEIGHING,
    Pickup.Status.DISPUTED,
)
# Home card (contract 5.1): requested to weighing only.
UPCOMING_STATUSES = ACTIVE_STATUSES[:-1]
# The collector owns the job and is still working it.
COLLECTOR_WORKING_STATUSES = (
    Pickup.Status.MATCHED,
    Pickup.Status.ON_THE_WAY,
    Pickup.Status.ARRIVED,
    Pickup.Status.WEIGHING,
)


class PickupItem(models.Model):
    """What the seller said they have, priced at booking time."""

    pickup = models.ForeignKey(Pickup, on_delete=models.CASCADE, related_name="items")
    material = models.ForeignKey("materials.Material", on_delete=models.PROTECT, related_name="+")
    approx_kg = models.DecimalField(max_digits=7, decimal_places=1)
    price_per_kg = models.PositiveIntegerField()

    class Meta:
        db_table = "pickups_item"
        ordering = ["id"]

    def __str__(self):
        return f"{self.material_id} ~{self.approx_kg} kg"


class PickupRefCounter(models.Model):
    """Single row handing out human refs (KB-2481). Locking it also
    serialises bookings so a slot's capacity can't be oversold."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_value = models.PositiveIntegerField(default=2400)

    class Meta:
        db_table = "pickups_ref_counter"

    def __str__(self):
        return f"Ref counter at {self.last_value}"


class PickupDecline(models.Model):
    """Hides a job from one collector's feed (contract 12.6)."""

    class Reason(models.TextChoices):
        TOO_FAR = "too_far", "Too far"
        WRONG_TIME = "wrong_time", "Wrong time"
        NOT_WORTH_IT = "not_worth_it", "Not worth it"
        OTHER = "other", "Other"

    pickup = models.ForeignKey(Pickup, on_delete=models.CASCADE, related_name="declines")
    collector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    reason = models.CharField(max_length=20, choices=Reason.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pickups_decline"
        constraints = [models.UniqueConstraint(fields=["pickup", "collector"], name="unique_decline")]

    def __str__(self):
        return f"{self.collector_id} declined {self.pickup_id}"


class PickupRating(models.Model):
    """One rating per side per pickup (contract 8.8)."""

    pickup = models.ForeignKey(Pickup, on_delete=models.CASCADE, related_name="ratings")
    rater = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ratings_given")
    ratee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ratings_received")
    stars = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pickups_rating"
        constraints = [models.UniqueConstraint(fields=["pickup", "rater"], name="unique_rating_per_side")]
        indexes = [models.Index(fields=["ratee"], name="rating_ratee_idx")]

    def __str__(self):
        return f"{self.stars}★ for {self.ratee_id}"


class WeighSheet(models.Model):
    """The collector's weights, mirrored live to the seller (contract 9, 12.9)."""

    class Status(models.TextChoices):
        LIVE = "live", "Live"
        SUBMITTED = "submitted", "Submitted"
        ACCEPTED = "accepted", "Accepted"
        DISPUTED = "disputed", "Disputed"

    pickup = models.OneToOneField(Pickup, on_delete=models.CASCADE, primary_key=True, related_name="weigh_sheet")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.LIVE)
    version = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pickups_weigh_sheet"

    def __str__(self):
        return f"Weigh sheet v{self.version} ({self.status})"


class WeighLine(models.Model):
    """One material on the sheet. The line id the API shows is `l<material_id>`,
    so it stays stable across saves and flags keep pointing at it."""

    sheet = models.ForeignKey(WeighSheet, on_delete=models.CASCADE, related_name="lines")
    material = models.ForeignKey("materials.Material", on_delete=models.PROTECT, related_name="+")
    rate_per_kg = models.PositiveIntegerField()
    kg = models.DecimalField(max_digits=7, decimal_places=1)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "pickups_weigh_line"
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["sheet", "material"], name="unique_line_per_material")]

    def __str__(self):
        return f"{self.line_id}: {self.kg} kg @ {self.rate_per_kg}"

    @property
    def line_id(self) -> str:
        return f"l{self.material_id}"


class Dispute(BaseModel):
    """Help & disputes (contract 13). Flags create one automatically."""

    class Type(models.TextChoices):
        WEIGHT_DISAGREEMENT = "weight_disagreement", "Weight disagreement"
        MISSED_PICKUP = "missed_pickup", "Missed pickup"
        PAYMENT = "payment", "Payment"
        BEHAVIOUR = "behaviour", "Behaviour"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    pickup = models.ForeignKey(Pickup, on_delete=models.CASCADE, related_name="disputes")
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="disputes_opened")
    type = models.CharField(max_length=30, choices=Type.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    note = models.CharField(max_length=500, blank=True)
    resolution_note = models.CharField(max_length=500, blank=True)
    adjusted_amount = models.PositiveIntegerField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pickups_dispute"
        indexes = [models.Index(fields=["pickup", "status"], name="dispute_pickup_idx")]

    def __str__(self):
        return f"{self.get_type_display()} on {self.pickup.ref}"


class WeighFlag(BaseModel):
    """The seller's objection to one line (contract 9.2)."""

    class Reason(models.TextChoices):
        WEIGHT_TOO_HIGH = "weight_too_high", "Weight too high"
        WRONG_MATERIAL_OR_RATE = "wrong_material_or_rate", "Wrong material or rate"
        SOMETHING_ELSE = "something_else", "Something else"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    sheet = models.ForeignKey(WeighSheet, on_delete=models.CASCADE, related_name="flags")
    material = models.ForeignKey("materials.Material", on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=30, choices=Reason.choices)
    expected = models.CharField(max_length=40, blank=True)
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    dispute = models.ForeignKey(Dispute, on_delete=models.SET_NULL, null=True, blank=True, related_name="flags")

    class Meta:
        db_table = "pickups_weigh_flag"
        indexes = [models.Index(fields=["sheet", "status"], name="flag_sheet_idx")]

    @property
    def line_id(self) -> str:
        return f"l{self.material_id}"
