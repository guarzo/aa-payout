"""App Settings"""

# Standard Library
import logging

# Django
from django.conf import settings

logger = logging.getLogger(__name__)

# Janice API Configuration
AAPAYOUT_JANICE_API_KEY = getattr(settings, "AAPAYOUT_JANICE_API_KEY", "")
# Market name (string): "jita", "amarr", "perimeter", "r1o-gn", etc. See https://janice.e-351.com/api/rest/v2/markets
AAPAYOUT_JANICE_MARKET = getattr(settings, "AAPAYOUT_JANICE_MARKET", "jita")  # Default: Jita

# Runtime check: Warn if user is using deprecated integer market IDs
if isinstance(AAPAYOUT_JANICE_MARKET, int):
    # Map common integer IDs to string names for migration guidance
    market_id_map = {
        1: "amarr",
        2: "jita",
        3: "dodixie",
        4: "rens",
        5: "hek",
    }
    suggested_name = market_id_map.get(AAPAYOUT_JANICE_MARKET, "jita")
    logger.warning(
        f"DEPRECATION WARNING: AAPAYOUT_JANICE_MARKET is set to integer value {AAPAYOUT_JANICE_MARKET}. "
        f"Integer market IDs are deprecated and will be removed in a future version. "
        f"Please update your settings to use the string market name instead: "
        f'AAPAYOUT_JANICE_MARKET = "{suggested_name}". '
        f"Valid market names: 'jita', 'amarr', 'perimeter', 'dodixie', 'rens', 'hek', etc. "
        f"See https://janice.e-351.com/api/rest/v2/markets for all supported markets."
    )
    # Auto-convert for backward compatibility (temporary)
    AAPAYOUT_JANICE_MARKET = suggested_name

AAPAYOUT_JANICE_PRICE_TYPE = getattr(settings, "AAPAYOUT_JANICE_PRICE_TYPE", "buy")
AAPAYOUT_JANICE_TIMEOUT = getattr(settings, "AAPAYOUT_JANICE_TIMEOUT", 30)
AAPAYOUT_JANICE_CACHE_HOURS = getattr(settings, "AAPAYOUT_JANICE_CACHE_HOURS", 1)

# Payout Configuration
AAPAYOUT_CORP_SHARE_PERCENTAGE = getattr(settings, "AAPAYOUT_CORP_SHARE_PERCENTAGE", 10)
AAPAYOUT_MINIMUM_PAYOUT = getattr(settings, "AAPAYOUT_MINIMUM_PAYOUT", 1000000)
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
    "esi-wallet.read_character_wallet.v1",  # Check FC wallet balance (optional)
    "esi-wallet.read_character_journal.v1",  # Verify payments post-transfer
    "esi-mail.send_mail.v1",  # Send payout notifications (optional)
]

# Scout Bonus Configuration
AAPAYOUT_SCOUT_BONUS_PERCENTAGE = getattr(settings, "AAPAYOUT_SCOUT_BONUS_PERCENTAGE", 10)  # +10% ISK bonus

# Express Mode Configuration
AAPAYOUT_EXPRESS_MODE_ENABLED = getattr(settings, "AAPAYOUT_EXPRESS_MODE_ENABLED", True)

# Payment Verification Configuration
AAPAYOUT_VERIFICATION_TIME_WINDOW_HOURS = getattr(settings, "AAPAYOUT_VERIFICATION_TIME_WINDOW_HOURS", 24)
AAPAYOUT_AUTO_VERIFY_AFTER_PAYMENT = getattr(settings, "AAPAYOUT_AUTO_VERIFY_AFTER_PAYMENT", True)
