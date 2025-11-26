"""
App Models
"""

# Standard Library
from decimal import Decimal

# Django
from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone

# Alliance Auth (External Libs)
# EVE Universe
from eveuniverse.models import EveEntity

# AA Payout
# AA-Payout
from aapayout import constants


class General(models.Model):
    """Meta model for app permissions"""

    class Meta:
        """Meta definitions"""

        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access payout system"),
            ("create_fleet", "Can create fleets"),
            ("manage_own_fleets", "Can manage own fleets as FC"),
            ("manage_all_fleets", "Can manage all fleets"),
            ("approve_payouts", "Can approve payouts"),
            ("view_all_payouts", "Can view all payout history"),
            ("manage_payout_rules", "Can manage payout rules"),
        )


class Fleet(models.Model):
    """Represents a fleet operation"""

    name = models.CharField(max_length=200, help_text="Fleet name or operation name")
    fleet_commander = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="commanded_fleets",
        help_text="Fleet commander",
    )
    fleet_time = models.DateTimeField(default=timezone.now, help_text="Fleet operation time")
    battle_report = models.URLField(max_length=500, blank=True, help_text="Battle report URL (optional)")
    status = models.CharField(
        max_length=20,
        choices=constants.FLEET_STATUS_CHOICES,
        default=constants.FLEET_STATUS_DRAFT,
        help_text="Fleet status",
    )
    notes = models.TextField(blank=True, help_text="Additional notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Finalization tracking
    finalized = models.BooleanField(
        default=False, help_text="Whether this fleet has been finalized (triggers wallet verification)"
    )
    finalized_at = models.DateTimeField(null=True, blank=True, help_text="When this fleet was finalized")
    finalized_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="finalized_fleets",
        help_text="User who finalized this fleet",
    )

    class Meta:
        ordering = ["-fleet_time"]
        indexes = [
            models.Index(fields=["-fleet_time"]),
            models.Index(fields=["fleet_commander", "status"]),
            models.Index(fields=["finalized"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.fleet_time.strftime('%Y-%m-%d')}"

    def get_absolute_url(self):
        """Return URL to fleet detail page"""
        return reverse("aapayout:fleet_detail", kwargs={"pk": self.pk})

    def can_edit(self, user):
        """Check if user can edit this fleet"""
        return self.fleet_commander == user or user.has_perm("aapayout.manage_all_fleets")

    def can_delete(self, user):
        """Check if user can delete this fleet"""
        return self.fleet_commander == user or user.has_perm("aapayout.manage_all_fleets")

    def get_total_loot_value(self):
        """Calculate total loot value from all loot pools"""
        return self.loot_pools.aggregate(total=models.Sum("total_value"))["total"] or 0

    def get_participant_count(self):
        """Get number of participants"""
        return self.participants.count()


class FleetParticipant(models.Model):
    """Represents a participant in a fleet"""

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="participants")
    character = models.ForeignKey(
        EveEntity,
        on_delete=models.CASCADE,
        help_text="EVE character (main character)",
    )
    role = models.CharField(
        max_length=20,
        choices=constants.ROLE_CHOICES,
        default=constants.ROLE_REGULAR,
        help_text="Participant role",
    )
    joined_at = models.DateTimeField(default=timezone.now, help_text="Time joined fleet")
    left_at = models.DateTimeField(null=True, blank=True, help_text="Time left fleet (if applicable)")
    notes = models.TextField(blank=True, help_text="Additional notes")
    created_at = models.DateTimeField(auto_now_add=True)

    # Phase 2: Character Deduplication & Scout Bonus
    is_scout = models.BooleanField(default=False, help_text="If checked, this participant receives +10% scout bonus")
    excluded_from_payout = models.BooleanField(
        default=False, help_text="If checked, this participant will not receive a payout"
    )
    main_character = models.ForeignKey(
        EveEntity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alt_participants",
        help_text="Main character for this participant (from Alliance Auth)",
    )

    class Meta:
        unique_together = ["fleet", "character"]
        ordering = ["joined_at"]
        indexes = [
            models.Index(fields=["is_scout"]),
            models.Index(fields=["excluded_from_payout"]),
            models.Index(fields=["main_character"]),
        ]

    def __str__(self):
        return f"{self.character.name} - {self.fleet.name}"

    def save(self, *args, **kwargs):
        """
        Auto-sync is_scout with role for consistency.
        If role is set to 'scout', ensure is_scout is True.

        Note: This sync is one-way only - is_scout will not be cleared if role
        changes away from scout. Additionally, is_scout can be set manually
        independent of role, allowing intentional overrides.
        """
        if self.role == constants.ROLE_SCOUT:
            self.is_scout = True
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """Check if participant is still active in fleet"""
        return self.left_at is None


class LootPool(models.Model):
    """Represents a pool of loot from a fleet operation"""

    fleet = models.ForeignKey(Fleet, on_delete=models.CASCADE, related_name="loot_pools")
    name = models.CharField(max_length=200, default="Fleet Loot", help_text="Loot pool name")
    raw_loot_text = models.TextField(help_text="Raw loot paste from EVE client", blank=True)
    status = models.CharField(
        max_length=20,
        choices=constants.LOOT_STATUS_CHOICES,
        default=constants.LOOT_STATUS_DRAFT,
        help_text="Loot pool status",
    )
    pricing_method = models.CharField(
        max_length=20,
        choices=constants.PRICING_METHOD_CHOICES,
        default=constants.PRICING_JANICE_BUY,
        help_text="Pricing method used",
    )
    total_value = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=0,
        help_text="Total loot value in ISK",
    )
    corp_share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
        help_text="Corporation share percentage",
    )
    corp_share_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=0,
        help_text="Corporation share amount in ISK",
    )
    participant_share_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=0,
        help_text="Total participant share amount in ISK",
    )
    scout_shares = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=Decimal("1.5"),
        help_text="Number of shares scouts receive (1-5, step 0.5)",
    )
    janice_appraisal_code = models.CharField(max_length=50, blank=True, help_text="Janice appraisal code for linking")
    valued_at = models.DateTimeField(null=True, blank=True, help_text="Time when loot was valued")
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_loot_pools",
        help_text="User who approved this loot pool",
    )
    approved_at = models.DateTimeField(null=True, blank=True, help_text="Time when loot pool was approved")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.fleet.name}"

    def save(self, *args, **kwargs):
        """Auto-generate name if not provided"""
        if not self.name or self.name == "Fleet Loot":
            self.name = f"Loot for {self.fleet.name}"
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """Calculate total value from all loot items"""
        total = self.items.aggregate(total=models.Sum("total_value"))["total"] or 0
        self.total_value = total

        # Calculate corp share
        self.corp_share_amount = total * self.corp_share_percentage / 100

        # Calculate participant share
        self.participant_share_amount = total - self.corp_share_amount

        self.save()

    def is_approved(self):
        """Check if loot pool is approved"""
        return self.status == constants.LOOT_STATUS_APPROVED or self.status == constants.LOOT_STATUS_PAID

    def can_approve(self, user):
        """Check if user can approve this loot pool"""
        return user.has_perm("aapayout.approve_payouts") or self.fleet.fleet_commander == user


class LootItem(models.Model):
    """Represents an individual item in a loot pool"""

    loot_pool = models.ForeignKey(LootPool, on_delete=models.CASCADE, related_name="items")
    type_id = models.IntegerField(help_text="EVE type ID")
    name = models.CharField(max_length=200, help_text="Item name")
    quantity = models.IntegerField(help_text="Item quantity")
    unit_price = models.DecimalField(max_digits=20, decimal_places=2, help_text="Price per unit in ISK")
    total_value = models.DecimalField(max_digits=20, decimal_places=2, help_text="Total value (quantity * unit_price)")
    price_source = models.CharField(
        max_length=20,
        choices=constants.PRICE_SOURCE_CHOICES,
        default=constants.PRICE_SOURCE_JANICE,
        help_text="Source of price data",
    )
    price_fetched_at = models.DateTimeField(default=timezone.now, help_text="Time when price was fetched")
    manual_override = models.BooleanField(default=False, help_text="Whether price was manually overridden")
    notes = models.TextField(blank=True, help_text="Additional notes")

    class Meta:
        ordering = ["-total_value"]

    def __str__(self):
        return f"{self.name} x{self.quantity}"

    def save(self, *args, **kwargs):
        """Calculate total value before saving"""
        self.total_value = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class Payout(models.Model):
    """Represents a payout to a fleet participant"""

    loot_pool = models.ForeignKey(LootPool, on_delete=models.CASCADE, related_name="payouts")
    recipient = models.ForeignKey(EveEntity, on_delete=models.CASCADE, help_text="Payment recipient character")
    amount = models.DecimalField(max_digits=20, decimal_places=2, help_text="Payout amount in ISK")
    status = models.CharField(
        max_length=20,
        choices=constants.PAYOUT_STATUS_CHOICES,
        default=constants.PAYOUT_STATUS_PENDING,
        help_text="Payment status",
    )
    payment_method = models.CharField(
        max_length=20,
        choices=constants.PAYMENT_METHOD_CHOICES,
        default=constants.PAYMENT_METHOD_MANUAL,
        help_text="Payment method",
    )
    transaction_reference = models.CharField(max_length=200, blank=True, help_text="Transaction reference or note")
    paid_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts_made",
        help_text="User who marked this as paid",
    )
    paid_at = models.DateTimeField(null=True, blank=True, help_text="Time when marked as paid")
    notes = models.TextField(blank=True, help_text="Additional notes")
    created_at = models.DateTimeField(auto_now_add=True)

    # Phase 2: Scout Bonus & Payment Verification
    is_scout_payout = models.BooleanField(default=False, help_text="Whether this payout includes scout bonus")
    verified = models.BooleanField(default=False, help_text="Whether this payout was verified via ESI wallet journal")
    verified_at = models.DateTimeField(null=True, blank=True, help_text="When this payout was verified")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "status"]),
            models.Index(fields=["loot_pool", "status"]),
            models.Index(fields=["is_scout_payout"]),
            models.Index(fields=["verified"]),
        ]

    def __str__(self):
        return f"{self.recipient.name} - {self.amount:,.2f} ISK"

    def mark_paid(self, user, reference=""):
        """Mark this payout as paid"""
        self.status = constants.PAYOUT_STATUS_PAID
        self.paid_by = user
        self.paid_at = timezone.now()
        if reference:
            self.transaction_reference = reference
        self.save()

    def can_mark_paid(self, user):
        """Check if user can mark this payout as paid"""
        return user.has_perm("aapayout.approve_payouts") or self.loot_pool.fleet.fleet_commander == user


class ESIFleetImport(models.Model):
    """Tracks ESI fleet composition imports"""

    fleet = models.ForeignKey(
        Fleet,
        on_delete=models.CASCADE,
        related_name="esi_imports",
        help_text="Fleet this import belongs to",
    )
    esi_fleet_id = models.BigIntegerField(help_text="ESI Fleet ID from EVE client")

    # Import metadata
    imported_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who initiated the import",
    )
    imported_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the import was performed",
    )

    # Results
    characters_found = models.IntegerField(
        default=0,
        help_text="Total characters in ESI fleet",
    )
    characters_added = models.IntegerField(
        default=0,
        help_text="New participants added",
    )
    characters_skipped = models.IntegerField(
        default=0,
        help_text="Already in fleet, skipped",
    )
    unique_players = models.IntegerField(
        default=0,
        help_text="Unique players after deduplication",
    )

    # Raw ESI response (for debugging)
    raw_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw ESI fleet data for debugging",
    )

    class Meta:
        ordering = ["-imported_at"]
        indexes = [
            models.Index(fields=["fleet", "-imported_at"]),
            models.Index(fields=["esi_fleet_id"]),
        ]

    def __str__(self):
        return f"ESI Import for {self.fleet.name} - {self.imported_at.strftime('%Y-%m-%d %H:%M')}"
