"""
Constants for AA-Payout
"""

# Fleet Status Choices
FLEET_STATUS_DRAFT = "draft"
FLEET_STATUS_ACTIVE = "active"
FLEET_STATUS_COMPLETED = "completed"
FLEET_STATUS_PAID = "paid"

FLEET_STATUS_CHOICES = [
    (FLEET_STATUS_DRAFT, "Draft"),
    (FLEET_STATUS_ACTIVE, "Active"),
    (FLEET_STATUS_COMPLETED, "Completed"),
    (FLEET_STATUS_PAID, "Paid"),
]

# Fleet Participant Role Choices
ROLE_REGULAR = "regular"
ROLE_SCOUT = "scout"

ROLE_CHOICES = [
    (ROLE_REGULAR, "Regular"),
    (ROLE_SCOUT, "Scout"),
]

# Loot Pool Status Choices
LOOT_STATUS_DRAFT = "draft"
LOOT_STATUS_VALUING = "valuing"
LOOT_STATUS_VALUED = "valued"
LOOT_STATUS_APPROVED = "approved"
LOOT_STATUS_PAID = "paid"

LOOT_STATUS_CHOICES = [
    (LOOT_STATUS_DRAFT, "Draft"),
    (LOOT_STATUS_VALUING, "Valuing"),
    (LOOT_STATUS_VALUED, "Valued"),
    (LOOT_STATUS_APPROVED, "Approved"),
    (LOOT_STATUS_PAID, "Paid"),
]

# Pricing Method Choices
PRICING_JANICE_BUY = "janice_buy"
PRICING_JANICE_SELL = "janice_sell"

PRICING_METHOD_CHOICES = [
    (PRICING_JANICE_BUY, "Janice - Jita Buy"),
    (PRICING_JANICE_SELL, "Janice - Jita Sell"),
]

# Price Source Choices
PRICE_SOURCE_JANICE = "janice"
PRICE_SOURCE_MANUAL = "manual"

PRICE_SOURCE_CHOICES = [
    (PRICE_SOURCE_JANICE, "Janice API"),
    (PRICE_SOURCE_MANUAL, "Manual Override"),
]

# Payout Status Choices
PAYOUT_STATUS_PENDING = "pending"
PAYOUT_STATUS_PAID = "paid"
PAYOUT_STATUS_FAILED = "failed"

PAYOUT_STATUS_CHOICES = [
    (PAYOUT_STATUS_PENDING, "Pending"),
    (PAYOUT_STATUS_PAID, "Paid"),
    (PAYOUT_STATUS_FAILED, "Failed"),
]

# Payment Method Choices
PAYMENT_METHOD_MANUAL = "manual"
PAYMENT_METHOD_CONTRACT = "contract"
PAYMENT_METHOD_DIRECT_TRADE = "direct_trade"

PAYMENT_METHOD_CHOICES = [
    (PAYMENT_METHOD_MANUAL, "Manual"),
    (PAYMENT_METHOD_CONTRACT, "Contract"),
    (PAYMENT_METHOD_DIRECT_TRADE, "Direct Trade"),
]
