"""Admin models"""

# Django
from django.contrib import admin
from django.utils.html import format_html

# AA Payout
from aapayout.models import (
    ESIFleetImport,
    Fleet,
    FleetParticipant,
    LootItem,
    LootPool,
    Payout,
)


class FleetParticipantInline(admin.TabularInline):
    """Inline admin for payout participants"""

    model = FleetParticipant
    extra = 0
    fields = ("character", "role", "joined_at", "left_at")
    readonly_fields = ("created_at",)


class LootPoolInline(admin.TabularInline):
    """Inline admin for loot pools"""

    model = LootPool
    extra = 0
    fields = ("name", "status", "total_value", "created_at")
    readonly_fields = ("total_value", "created_at")
    show_change_link = True


@admin.register(Fleet)
class FleetAdmin(admin.ModelAdmin):
    """Admin for Payout model"""

    list_display = (
        "name",
        "fleet_commander",
        "fleet_time",
        "status",
        "participant_count",
        "total_value",
        "created_at",
    )
    list_filter = ("status", "fleet_time", "created_at")
    search_fields = ("name", "fleet_commander__username")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "fleet_time"
    inlines = [FleetParticipantInline, LootPoolInline]

    fieldsets = (
        ("Payout Information", {"fields": ("name", "fleet_commander", "fleet_time", "battle_report")}),
        ("Status", {"fields": ("status", "notes")}),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def participant_count(self, obj):
        """Get participant count"""
        return obj.get_participant_count()

    participant_count.short_description = "Participants"

    def total_value(self, obj):
        """Get total loot value"""
        value = obj.get_total_loot_value()
        return format_html("{:,.2f} ISK", value)

    total_value.short_description = "Total Loot Value"


@admin.register(FleetParticipant)
class FleetParticipantAdmin(admin.ModelAdmin):
    """Admin for Payout Participant model"""

    list_display = (
        "character",
        "fleet",
        "role",
        "joined_at",
        "left_at",
        "is_active",
    )
    list_filter = ("role", "joined_at")
    search_fields = ("character__name", "fleet__name")
    readonly_fields = ("created_at",)

    fieldsets = (
        ("Participant Information", {"fields": ("fleet", "character", "role")}),
        ("Timing", {"fields": ("joined_at", "left_at")}),
        (
            "Additional",
            {
                "fields": ("notes", "created_at"),
                "classes": ("collapse",),
            },
        ),
    )


class LootItemInline(admin.TabularInline):
    """Inline admin for loot items"""

    model = LootItem
    extra = 0
    fields = ("name", "quantity", "unit_price", "total_value", "price_source", "manual_override")
    readonly_fields = ("total_value",)


class PayoutInline(admin.TabularInline):
    """Inline admin for payouts"""

    model = Payout
    extra = 0
    fields = ("recipient", "amount", "status", "paid_at")
    readonly_fields = ("amount", "paid_at")
    show_change_link = True


@admin.register(LootPool)
class LootPoolAdmin(admin.ModelAdmin):
    """Admin for LootPool model"""

    list_display = (
        "name",
        "fleet",
        "status",
        "total_value_display",
        "corp_share_display",
        "participant_share_display",
        "valued_at",
        "approved_by",
    )
    list_filter = ("status", "pricing_method", "created_at", "valued_at")
    search_fields = ("name", "fleet__name")
    readonly_fields = (
        "total_value",
        "corp_share_amount",
        "participant_share_amount",
        "valued_at",
        "approved_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    inlines = [LootItemInline, PayoutInline]

    fieldsets = (
        ("Loot Pool Information", {"fields": ("fleet", "name", "raw_loot_text")}),
        ("Pricing", {"fields": ("pricing_method", "status", "janice_appraisal_code")}),
        (
            "Values",
            {
                "fields": (
                    "total_value",
                    "corp_share_percentage",
                    "corp_share_amount",
                    "participant_share_amount",
                )
            },
        ),
        (
            "Approval",
            {
                "fields": ("approved_by", "approved_at", "valued_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def total_value_display(self, obj):
        """Format total value"""
        return format_html("{:,.2f} ISK", obj.total_value)

    total_value_display.short_description = "Total Value"

    def corp_share_display(self, obj):
        """Format corp share"""
        return format_html("{:,.2f} ISK ({}%)", obj.corp_share_amount, obj.corp_share_percentage)

    corp_share_display.short_description = "Corp Share"

    def participant_share_display(self, obj):
        """Format participant share"""
        return format_html("{:,.2f} ISK", obj.participant_share_amount)

    participant_share_display.short_description = "Participant Share"


@admin.register(LootItem)
class LootItemAdmin(admin.ModelAdmin):
    """Admin for LootItem model"""

    list_display = (
        "name",
        "loot_pool",
        "quantity",
        "unit_price_display",
        "total_value_display",
        "price_source",
        "manual_override",
        "price_fetched_at",
    )
    list_filter = ("price_source", "manual_override", "price_fetched_at")
    search_fields = ("name", "loot_pool__name")
    readonly_fields = ("total_value", "price_fetched_at")

    fieldsets = (
        ("Item Information", {"fields": ("loot_pool", "type_id", "name", "quantity")}),
        (
            "Pricing",
            {
                "fields": (
                    "unit_price",
                    "total_value",
                    "price_source",
                    "manual_override",
                    "price_fetched_at",
                )
            },
        ),
        (
            "Additional",
            {
                "fields": ("notes",),
                "classes": ("collapse",),
            },
        ),
    )

    def unit_price_display(self, obj):
        """Format unit price"""
        return format_html("{:,.2f} ISK", obj.unit_price)

    unit_price_display.short_description = "Unit Price"

    def total_value_display(self, obj):
        """Format total value"""
        return format_html("{:,.2f} ISK", obj.total_value)

    total_value_display.short_description = "Total Value"


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    """Admin for Payout model"""

    list_display = (
        "recipient",
        "loot_pool",
        "amount_display",
        "status",
        "payment_method",
        "paid_by",
        "paid_at",
        "created_at",
    )
    list_filter = ("status", "payment_method", "paid_at", "created_at")
    search_fields = ("recipient__name", "loot_pool__name", "transaction_reference")
    readonly_fields = ("created_at", "paid_at")
    date_hierarchy = "created_at"

    fieldsets = (
        ("Payout Information", {"fields": ("loot_pool", "recipient", "amount")}),
        ("Payment Details", {"fields": ("status", "payment_method", "transaction_reference")}),
        (
            "Payment Tracking",
            {
                "fields": ("paid_by", "paid_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Additional",
            {
                "fields": ("notes", "created_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["mark_as_paid"]

    def amount_display(self, obj):
        """Format amount"""
        return format_html("{:,.2f} ISK", obj.amount)

    amount_display.short_description = "Amount"

    @admin.action(description="Mark selected payouts as paid")
    def mark_as_paid(self, request, queryset):
        """Admin action to mark payouts as paid"""
        # Django
        from django.utils import timezone

        # AA Payout
        from aapayout import constants

        count = queryset.update(
            status=constants.PAYOUT_STATUS_PAID,
            paid_by=request.user,
            paid_at=timezone.now(),
        )
        self.message_user(request, f"Marked {count} payout(s) as paid.")


@admin.register(ESIFleetImport)
class ESIFleetImportAdmin(admin.ModelAdmin):
    """Admin for ESI Payout Imports"""

    list_display = [
        "id",
        "fleet",
        "esi_fleet_id",
        "characters_found",
        "characters_added",
        "unique_players",
        "imported_by",
        "imported_at",
    ]
    list_filter = ["imported_at"]
    search_fields = ["fleet__name", "esi_fleet_id"]
    readonly_fields = [
        "imported_at",
        "characters_found",
        "characters_added",
        "characters_skipped",
        "unique_players",
        "raw_data",
    ]
    date_hierarchy = "imported_at"

    def has_add_permission(self, request):
        """Disable manual creation (should only be created via import view)"""
        return False
