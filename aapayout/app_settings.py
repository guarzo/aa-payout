"""App Settings"""

# Django
from django.conf import settings

# Alliance Auth
from allianceauth.services.hooks import get_extension_logger

logger = get_extension_logger(__name__)

# Janice API Configuration
AAPAYOUT_JANICE_API_KEY = getattr(settings, "AAPAYOUT_JANICE_API_KEY", "")
# Market ID (integer): 2=Jita, 1=Amarr, 3=Dodixie, 4=Rens, 5=Hek
# The Janice API requires integer market IDs, not string names
AAPAYOUT_JANICE_MARKET = getattr(settings, "AAPAYOUT_JANICE_MARKET", 2)  # Default: 2 (Jita)

AAPAYOUT_JANICE_PRICE_TYPE = getattr(settings, "AAPAYOUT_JANICE_PRICE_TYPE", "buy")
AAPAYOUT_JANICE_TIMEOUT = getattr(settings, "AAPAYOUT_JANICE_TIMEOUT", 30)
AAPAYOUT_JANICE_CACHE_HOURS = getattr(settings, "AAPAYOUT_JANICE_CACHE_HOURS", 1)

# Payout Configuration
AAPAYOUT_CORP_SHARE_PERCENTAGE = getattr(settings, "AAPAYOUT_CORP_SHARE_PERCENTAGE", 10)
AAPAYOUT_MINIMUM_PAYOUT = getattr(settings, "AAPAYOUT_MINIMUM_PAYOUT", 1000000)  # 1M ISK
AAPAYOUT_MINIMUM_PER_PARTICIPANT = getattr(settings, "AAPAYOUT_MINIMUM_PER_PARTICIPANT", 100000000)  # 100M ISK
AAPAYOUT_REQUIRE_APPROVAL = getattr(settings, "AAPAYOUT_REQUIRE_APPROVAL", True)

# Holding Corporation Configuration
AAPAYOUT_HOLDING_CORP_ID = getattr(settings, "AAPAYOUT_HOLDING_CORP_ID", None)

# Phase 2: ESI Integration
AAPAYOUT_ESI_FLEET_IMPORT_ENABLED = getattr(settings, "AAPAYOUT_ESI_FLEET_IMPORT_ENABLED", True)
AAPAYOUT_ESI_CACHE_HOURS = getattr(settings, "AAPAYOUT_ESI_CACHE_HOURS", 1)

# Required ESI Scopes
AAPAYOUT_ESI_SCOPES = [
    "esi-ui.open_window.v1",  # Open character windows (Express Mode)
    "esi-fleets.read_fleet.v1",  # Import fleet composition
    "esi-wallet.read_character_wallet.v1",  # Check FC wallet balance & verify payments
    "esi-mail.send_mail.v1",  # Send payout notifications (optional)
]

# Scout Bonus Configuration
AAPAYOUT_SCOUT_BONUS_PERCENTAGE = getattr(settings, "AAPAYOUT_SCOUT_BONUS_PERCENTAGE", 10)  # +10% ISK bonus

# Express Mode Configuration
AAPAYOUT_EXPRESS_MODE_ENABLED = getattr(settings, "AAPAYOUT_EXPRESS_MODE_ENABLED", True)

# Payment Verification Configuration
AAPAYOUT_VERIFICATION_TIME_WINDOW_HOURS = getattr(settings, "AAPAYOUT_VERIFICATION_TIME_WINDOW_HOURS", 24)
AAPAYOUT_AUTO_VERIFY_AFTER_PAYMENT = getattr(settings, "AAPAYOUT_AUTO_VERIFY_AFTER_PAYMENT", True)
