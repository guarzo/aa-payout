"""
Helper functions for AA-Payout
"""

# Standard Library
from decimal import ROUND_DOWN, Decimal
from typing import Dict, List

# Django
from django.db import transaction

# Alliance Auth
from allianceauth.services.hooks import get_extension_logger

# AA Payout
from aapayout import app_settings, constants
from aapayout.models import LootItem, LootPool, Payout

logger = get_extension_logger(__name__)


def calculate_payouts(loot_pool: LootPool) -> List[Dict]:
    """
    Calculate payout distribution for a loot pool using share-based system.

    Calculation Order:
    1. Corporation tax is deducted from total loot (raw % of total)
    2. Calculate total shares: scouts get scout_shares each, regulars get 1 share each
    3. Calculate per-share value from participant pool
    4. Each participant receives shares × per-share value
    5. Individual shares round down to nearest 0.01 ISK
    6. Remainder from rounding goes to corporation

    Example:
        Total loot: 100M ISK
        Corp tax: 10%
        Scouts: 1 (with 2 shares)
        Regular participants: 2 (with 1 share each)

        Corp share: 100M * 10% = 10M ISK
        Participant pool: 100M - 10M = 90M ISK
        Total shares: 2 + 1 + 1 = 4 shares
        Per-share value: 90M / 4 = 22.5M ISK
        Scout payout: 2 × 22.5M = 45M ISK
        Regular payout: 1 × 22.5M = 22.5M ISK each

    Args:
        loot_pool: LootPool instance to calculate payouts for

    Returns:
        List of dicts with payout information:
        [
            {
                'character': EveEntity (main character),
                'amount': Decimal,
                'share_percentage': Decimal,
                'is_scout': bool,
                'alt_characters': [EveEntity, ...] (list of alt chars)
            },
            ...
        ]
    """
    # Get total loot value
    total_value = loot_pool.total_value

    if total_value <= 0:
        logger.warning(f"Loot pool {loot_pool.id} has zero or negative value")
        return []

    # Get active participants (not left the fleet)
    participants = loot_pool.fleet.participants.filter(left_at__isnull=True)

    if participants.count() == 0:
        logger.warning(f"Fleet {loot_pool.fleet.id} has no active participants")
        return []

    # Deduplicate participants by main character
    user_groups = deduplicate_participants(participants)

    # Count eligible players (not excluded)
    eligible_players = [group for group in user_groups.values() if not group["excluded"]]
    player_count = len(eligible_players)

    if player_count == 0:
        logger.warning(f"Fleet {loot_pool.fleet.id} has no eligible participants")
        return []

    # Count scouts and regular participants
    scout_players = [p for p in eligible_players if p["is_scout"]]
    regular_players = [p for p in eligible_players if not p["is_scout"]]
    scout_count = len(scout_players)
    regular_count = len(regular_players)

    # Get settings from loot pool
    corp_share_percentage = loot_pool.corp_share_percentage or Decimal("0.00")
    scout_shares = loot_pool.scout_shares or Decimal("1.5")

    # Step 1: Calculate corporation share (raw % of total)
    corp_share_amount = (total_value * corp_share_percentage / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_DOWN
    )

    # Step 2: Calculate participant pool
    participant_pool = total_value - corp_share_amount

    # Step 3: Calculate total shares
    # Scouts get scout_shares each, regulars get 1 share each
    total_shares = (scout_count * scout_shares) + (regular_count * Decimal("1"))

    if total_shares <= 0:
        logger.warning(f"Fleet {loot_pool.fleet.id} has zero total shares")
        return []

    # Step 4: Calculate per-share value
    per_share_value = (participant_pool / total_shares).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    # Calculate individual payouts
    base_share = per_share_value  # 1 share = per_share_value
    scout_payout = (per_share_value * scout_shares).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    # Check minimum per-participant threshold (default 100M ISK)
    minimum_per_participant = Decimal(str(app_settings.AAPAYOUT_MINIMUM_PER_PARTICIPANT))
    min_share = base_share  # Regular share is the minimum
    if min_share < minimum_per_participant and min_share > 0:
        logger.warning(
            f"Share per participant ({min_share:,.2f} ISK) is below minimum threshold "
            f"({minimum_per_participant:,.2f} ISK). All ISK ({total_value:,.2f}) goes to corporation. "
            f"No participant payouts will be created."
        )
        return []

    # Build payout list and calculate actual total distributed
    payouts = []
    total_distributed = Decimal("0.00")

    # Add participant payouts (one per unique player)
    for user_data in user_groups.values():
        # Skip excluded players
        if user_data["excluded"]:
            logger.info(f"Skipping excluded player {user_data['main_character'].name}")
            continue

        # Calculate payout amount based on whether they're a scout
        if user_data["is_scout"]:
            payout_amount = scout_payout
            payout_scout_bonus = scout_payout - base_share  # Bonus is the extra shares
        else:
            payout_amount = base_share
            payout_scout_bonus = Decimal("0.00")

        # Check minimum payout
        if payout_amount >= app_settings.AAPAYOUT_MINIMUM_PAYOUT:
            share_pct = (payout_amount / total_value * Decimal("100")).quantize(Decimal("0.01"))
            payouts.append(
                {
                    "character": user_data["main_character"],
                    "amount": payout_amount,
                    "base_share": base_share,
                    "scout_bonus": payout_scout_bonus,
                    "share_percentage": share_pct,
                    "is_scout": user_data["is_scout"],
                    "alt_characters": [p.character for p in user_data["participants"]],
                }
            )
            total_distributed += payout_amount
        else:
            logger.info(
                f"Skipping payout for {user_data['main_character'].name}: "
                f"{payout_amount} ISK is below minimum "
                f"({app_settings.AAPAYOUT_MINIMUM_PAYOUT} ISK)"
            )

    # Remainder goes to corporation (includes rounding differences)
    remainder = participant_pool - total_distributed
    corp_final_share = corp_share_amount + remainder

    logger.info(
        f"Calculated payouts for {len(payouts)} unique players "
        f"from {participants.count()} participants "
        f"(per-share: {per_share_value:,.2f} ISK, "
        f"scout payout: {scout_payout:,.2f} ISK ({scout_shares} shares), "
        f"regular payout: {base_share:,.2f} ISK (1 share), "
        f"scouts: {scout_count}, regulars: {regular_count}, "
        f"corp share: {corp_final_share:,.2f} ISK)"
    )

    return payouts


def calculate_payout_summary(loot_pool: LootPool, participant_groups: Dict) -> Dict:
    """
    Calculate payout summary for display purposes using share-based system.

    This extracts the summary calculation logic used in views to maintain DRY principles
    and ensure consistency with the main calculate_payouts function.

    Calculation Order (matching calculate_payouts):
    1. Corporation tax is deducted from total loot (raw % of total)
    2. Calculate total shares: scouts get scout_shares each, regulars get 1 share each
    3. Calculate per-share value from participant pool
    4. Each participant receives shares × per-share value

    Args:
        loot_pool: LootPool instance with approved/paid status
        participant_groups: Dictionary of participant groups (from deduplicate_participants)

    Returns:
        Dictionary with payout summary information:
        {
            'total_loot': Decimal,
            'corp_share_pct': Decimal,
            'corp_share': Decimal,
            'participant_pool': Decimal,
            'eligible_count': int,
            'scout_count': int,
            'regular_count': int,
            'total_shares': Decimal,
            'per_share_value': Decimal,
            'base_share': Decimal,
            'scout_share': Decimal,
            'scout_shares': Decimal,
            'scout_bonus': Decimal,
            'total_payouts': Decimal,
            'remainder': Decimal,
            'corp_final': Decimal,
        }
    """
    total_value = loot_pool.total_value
    corp_share_pct = loot_pool.corp_share_percentage or Decimal("0.00")
    scout_shares = loot_pool.scout_shares or Decimal("1.5")

    # Count eligible participants
    eligible_count = len([g for g in participant_groups.values() if not g["excluded"]])
    scout_count = len([g for g in participant_groups.values() if g["is_scout"] and not g["excluded"]])
    regular_count = eligible_count - scout_count

    # Step 1: Corp share (raw % of total)
    corp_share = (total_value * corp_share_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    # Step 2: Participant pool
    participant_pool = total_value - corp_share

    # Step 3: Calculate total shares
    total_shares_value = (scout_count * scout_shares) + (regular_count * Decimal("1"))

    # Step 4: Calculate per-share value and individual payouts
    per_share_value = Decimal("0.00")
    base_share = Decimal("0.00")
    scout_share = Decimal("0.00")

    if total_shares_value > 0:
        per_share_value = (participant_pool / total_shares_value).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        base_share = per_share_value  # 1 share
        scout_share = (per_share_value * scout_shares).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    # Scout bonus is the extra ISK from having more shares
    scout_bonus = scout_share - base_share if scout_count > 0 else Decimal("0.00")

    # Total distributed (actual payouts from database)
    total_payouts = sum(p.amount for p in loot_pool.payouts.all())

    # Remainder calculation based on actual payouts, not theoretical splits
    # This ensures consistency when participants are skipped (minimum thresholds)
    # or when rounding differences occur
    remainder = total_value - corp_share - total_payouts
    corp_final = corp_share + remainder

    return {
        "total_loot": total_value,
        "corp_share_pct": corp_share_pct,
        "corp_share": corp_share,
        "participant_pool": participant_pool,
        "eligible_count": eligible_count,
        "scout_count": scout_count,
        "regular_count": regular_count,
        "total_shares": total_shares_value,
        "per_share_value": per_share_value,
        "base_share": base_share,
        "scout_share": scout_share,
        "scout_shares": scout_shares,
        "scout_bonus": scout_bonus,
        "total_payouts": total_payouts,
        "remainder": remainder,
        "corp_final": corp_final,
    }


@transaction.atomic
def create_payouts(loot_pool: LootPool) -> int:
    """
    Create Payout records for a loot pool

    Deletes any existing payouts for the loot pool and creates new ones
    based on the current calculation.

    Args:
        loot_pool: LootPool instance

    Returns:
        Number of payouts created
    """
    # Delete existing payouts
    existing_count = loot_pool.payouts.count()
    if existing_count > 0:
        logger.info(f"Deleting {existing_count} existing payouts for loot pool {loot_pool.id}")
        loot_pool.payouts.all().delete()

    # Calculate new payouts
    payout_data = calculate_payouts(loot_pool)

    # Create Payout records
    payouts_created = 0
    for data in payout_data:
        Payout.objects.create(
            loot_pool=loot_pool,
            recipient=data["character"],
            amount=data["amount"],
            status=constants.PAYOUT_STATUS_PENDING,
            payment_method=constants.PAYMENT_METHOD_MANUAL,
            is_scout_payout=data.get("is_scout", False),
        )
        payouts_created += 1

    logger.info(f"Created {payouts_created} payouts for loot pool {loot_pool.id}")

    return payouts_created


def format_isk(amount: Decimal) -> str:
    """
    Format ISK amount for display

    Args:
        amount: ISK amount as Decimal

    Returns:
        Formatted string with commas and 2 decimal places
    """
    return f"{amount:,.2f}"


def format_isk_abbreviated(amount: Decimal) -> str:
    """
    Format ISK amount in abbreviated format for display.

    Formats large ISK values with K/M/B/T suffixes for better readability.

    Examples:
        500 -> "500 ISK"
        1,500 -> "1.5K ISK"
        1,500,000 -> "1.5M ISK"
        1,500,000,000 -> "1.5B ISK"
        1,500,000,000,000 -> "1.5T ISK"

    Args:
        amount: ISK amount as Decimal, int, or float

    Returns:
        Formatted string with K/M/B/T suffix and "ISK"
    """
    if amount is None:
        return "0 ISK"

    # Convert to Decimal for consistent handling
    try:
        if isinstance(amount, (int, float)):
            value = Decimal(str(amount))
        elif isinstance(amount, Decimal):
            value = amount
        else:
            return f"{amount} ISK"
    except (ValueError, TypeError):
        return f"{amount} ISK"

    # Handle negative values
    is_negative = value < 0
    value = abs(value)

    # Determine the appropriate suffix and divisor
    if value >= Decimal("1000000000000"):  # 1 trillion+
        divisor = Decimal("1000000000000")
        suffix = "T"
    elif value >= Decimal("1000000000"):  # 1 billion+
        divisor = Decimal("1000000000")
        suffix = "B"
    elif value >= Decimal("1000000"):  # 1 million+
        divisor = Decimal("1000000")
        suffix = "M"
    elif value >= Decimal("1000"):  # 1 thousand+
        divisor = Decimal("1000")
        suffix = "K"
    else:
        # Less than 1,000 - show as integer
        result = str(int(value))
        if is_negative:
            result = f"-{result}"
        return f"{result} ISK"

    # Calculate the formatted value
    formatted_amount = value / divisor

    # Format with 1 decimal place, but drop .0 if it's a round number
    if formatted_amount == int(formatted_amount):
        result = f"{int(formatted_amount)}{suffix}"
    else:
        result = f"{formatted_amount:.1f}{suffix}"

    if is_negative:
        result = f"-{result}"

    return f"{result} ISK"


def search_characters(query: str, limit: int = 20):
    """
    Search for EVE characters by name

    This will search the EveEntity table for characters.
    For MVP, we search any character in the AA database.

    Args:
        query: Search query string
        limit: Maximum number of results

    Returns:
        QuerySet of EveEntity objects
    """
    # Alliance Auth (External Libs)
    from eveuniverse.models import EveEntity

    if not query or len(query) < 2:
        return EveEntity.objects.none()

    # Search for characters (category_id 1 = character in EVE)
    return EveEntity.objects.filter(
        name__icontains=query,
        category_id=1,  # Characters only
    ).order_by(
        "name"
    )[:limit]


def get_main_character(user):
    """
    Get user's main character

    Args:
        user: Django User instance

    Returns:
        EveCharacter instance or None
    """
    try:
        # Get main character via Alliance Auth's profile system
        if hasattr(user, "profile") and user.profile.main_character:
            return user.profile.main_character
    except Exception as e:
        logger.warning(f"Failed to get main character for user {user.id}: {e}")

    return None


def get_main_character_for_participant(participant):
    """
    Get the main character for a fleet participant

    Uses Alliance Auth's character ownership system to identify the main character.
    Falls back to the participant's character itself if ownership cannot be determined.

    Args:
        participant: FleetParticipant instance

    Returns:
        EveEntity: Main character (EveEntity instance)
    """
    # Alliance Auth
    from allianceauth.authentication.models import OwnershipRecord
    from allianceauth.eveonline.models import EveCharacter

    # Alliance Auth (External Libs)
    from eveuniverse.models import EveEntity

    # If main_character is already set, use it
    if participant.main_character:
        return participant.main_character

    try:
        # Try to get the EveCharacter for this entity
        eve_character = EveCharacter.objects.filter(character_id=participant.character.id).first()

        if eve_character:
            # Get the user who owns this character via OwnershipRecord
            ownership = OwnershipRecord.objects.filter(character=eve_character).first()

            if ownership and ownership.user:
                # Get the user's main character
                main_character = get_main_character(ownership.user)

                if main_character:
                    # Convert EveCharacter to EveEntity
                    main_entity = EveEntity.objects.get_or_create_esi(id=main_character.character_id)[0]
                    return main_entity

    except Exception as e:
        logger.warning(f"Failed to get main character for participant {participant.id}: {e}")

    # Fallback: return the participant's character itself
    logger.debug(f"Using participant character as main for {participant.character.name}")
    return participant.character


def deduplicate_participants(participants):
    """
    Group participants by main character (one payout per human)

    This function ensures that each human player receives only one payout,
    regardless of how many characters (alts) they brought to the fleet.

    Rules:
    - If ANY alt is marked scout, the main character receives scout bonus
    - If ANY alt is excluded, the entire player is excluded
    - Payouts are sent to the main character

    Args:
        participants: QuerySet or list of FleetParticipant instances

    Returns:
        dict: Mapping of main character ID to participant data
        {
            main_character_id: {
                'main_character': EveEntity,
                'participants': [FleetParticipant, ...],
                'is_scout': bool,
                'excluded': bool
            },
            ...
        }
    """
    user_groups = {}

    for participant in participants:
        # Get main character for this participant
        main_char = get_main_character_for_participant(participant)

        # Create group if not exists
        if main_char.id not in user_groups:
            user_groups[main_char.id] = {
                "main_character": main_char,
                "participants": [],
                "is_scout": False,
                "excluded": False,
            }

        # Add participant to group
        user_groups[main_char.id]["participants"].append(participant)

        # If ANY alt is marked scout, main gets scout bonus
        if participant.is_scout:
            user_groups[main_char.id]["is_scout"] = True

        # If ANY alt is excluded, entire player excluded
        if participant.excluded_from_payout:
            user_groups[main_char.id]["excluded"] = True

    logger.info(f"Deduplicated {len(participants)} participants into " f"{len(user_groups)} unique players")

    return user_groups


def create_loot_items_from_appraisal(loot_pool: LootPool, appraisal_data: Dict) -> int:
    """
    Create LootItem records from Janice API appraisal data

    Args:
        loot_pool: LootPool instance
        appraisal_data: Dict from JaniceService.appraise()

    Returns:
        Number of LootItems created
    """
    items_created = 0

    for item_data in appraisal_data.get("items", []):
        LootItem.objects.create(
            loot_pool=loot_pool,
            type_id=item_data["type_id"],
            name=item_data["name"],
            quantity=item_data["quantity"],
            unit_price=item_data["unit_price"],
            total_value=item_data["total_value"],
            price_source=constants.PRICE_SOURCE_JANICE,
            manual_override=False,
        )
        items_created += 1

    # Update loot pool totals
    loot_pool.calculate_totals()

    # Update status to valued
    loot_pool.status = constants.LOOT_STATUS_VALUED
    loot_pool.save()

    logger.info(f"Created {items_created} loot items for pool {loot_pool.id}")

    return items_created


def reappraise_loot_pool(loot_pool: LootPool) -> str:
    """
    Clear existing items and re-appraise a loot pool asynchronously

    This helper function encapsulates the common re-appraisal logic used by
    both the loot_edit and loot_reappraise views.

    Steps:
    1. Clear all existing loot items
    2. Reset loot pool status to DRAFT
    3. Queue Janice API appraisal task asynchronously via Celery
    4. Return AsyncResult task ID for status tracking

    Args:
        loot_pool: LootPool instance to re-appraise

    Returns:
        str: Celery AsyncResult task ID for tracking appraisal status
    """
    # AA Payout
    from aapayout.tasks import appraise_loot_pool as appraise_task

    # Clear existing items
    deleted_count = loot_pool.items.count()
    loot_pool.items.all().delete()
    logger.info(f"Cleared {deleted_count} existing items from loot pool {loot_pool.id}")

    # Reset status to draft
    loot_pool.status = constants.LOOT_STATUS_DRAFT
    loot_pool.save()

    # Queue appraisal asynchronously using Celery
    logger.info(f"Queueing async appraisal task for loot pool {loot_pool.id}")
    async_result = appraise_task.delay(loot_pool.id)

    logger.info(f"Appraisal task queued with ID: {async_result.id}")

    return async_result.id
