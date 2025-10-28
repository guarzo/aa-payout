"""App Tasks"""

import logging

from celery import shared_task
from django.utils import timezone

from aapayout import constants
from aapayout.helpers import create_loot_items_from_appraisal
from aapayout.models import LootPool
from aapayout.services.janice import JaniceAPIError, JaniceService

logger = logging.getLogger(__name__)


@shared_task
def appraise_loot_pool(loot_pool_id: int):
    """
    Asynchronously appraise a loot pool via Janice API

    This task:
    1. Retrieves the loot pool by ID
    2. Calls the Janice API with the raw loot text
    3. Creates LootItem records from the appraisal
    4. Updates the loot pool status

    Args:
        loot_pool_id: ID of LootPool to appraise

    Returns:
        Dict with results or error information
    """
    try:
        logger.info(f"Starting appraisal for loot pool {loot_pool_id}")

        # Get loot pool
        loot_pool = LootPool.objects.get(id=loot_pool_id)

        # Update status to valuing
        loot_pool.status = constants.LOOT_STATUS_VALUING
        loot_pool.save()

        # Get raw loot text
        loot_text = loot_pool.raw_loot_text

        if not loot_text or not loot_text.strip():
            raise ValueError("Loot pool has no loot text to appraise")

        # Call Janice API
        logger.info(f"Calling Janice API for loot pool {loot_pool_id}")
        appraisal_data = JaniceService.appraise(loot_text)

        # Create LootItem records
        items_created = create_loot_items_from_appraisal(loot_pool, appraisal_data)

        # Update valued_at timestamp
        loot_pool.valued_at = timezone.now()
        loot_pool.save()

        logger.info(
            f"Successfully appraised loot pool {loot_pool_id}: "
            f"{items_created} items, "
            f"total value {loot_pool.total_value:,.2f} ISK"
        )

        return {
            "success": True,
            "loot_pool_id": loot_pool_id,
            "items_created": items_created,
            "total_value": float(loot_pool.total_value),
        }

    except LootPool.DoesNotExist:
        error_msg = f"Loot pool {loot_pool_id} does not exist"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    except JaniceAPIError as e:
        error_msg = f"Janice API error for loot pool {loot_pool_id}: {str(e)}"
        logger.error(error_msg)

        # Update loot pool status back to draft on API error
        try:
            loot_pool = LootPool.objects.get(id=loot_pool_id)
            loot_pool.status = constants.LOOT_STATUS_DRAFT
            loot_pool.save()
        except Exception:
            pass

        return {"success": False, "error": str(e)}

    except Exception as e:
        error_msg = f"Unexpected error appraising loot pool {loot_pool_id}: {str(e)}"
        logger.exception(error_msg)

        # Update loot pool status back to draft on unexpected error
        try:
            loot_pool = LootPool.objects.get(id=loot_pool_id)
            loot_pool.status = constants.LOOT_STATUS_DRAFT
            loot_pool.save()
        except Exception:
            pass

        return {"success": False, "error": str(e)}


@shared_task
def import_fleet_async(fleet_id: int, esi_fleet_id: int, user_id: int):
    """
    Asynchronously import fleet composition from ESI

    This task is used for large fleets (50+ members) to avoid blocking
    the web request. For smaller fleets, the import is done synchronously
    in the view.

    Phase 2: Week 3-4 - ESI Fleet Import

    Args:
        fleet_id: ID of Fleet to import participants into
        esi_fleet_id: ESI fleet ID to import from
        user_id: ID of User who initiated the import

    Returns:
        Dict with results or error information
    """
    from django.contrib.auth.models import User
    from esi.models import Token

    from aapayout.helpers import get_main_character_for_participant
    from aapayout.models import ESIFleetImport, Fleet, FleetParticipant
    from aapayout.services.esi_fleet import esi_fleet_service

    try:
        logger.info(
            f"Starting async fleet import for fleet {fleet_id} "
            f"from ESI fleet {esi_fleet_id}"
        )

        # Get fleet
        fleet = Fleet.objects.get(id=fleet_id)

        # Get user
        user = User.objects.get(id=user_id)

        # Get user's ESI token
        token = Token.objects.filter(
            user=user,
        ).require_scopes("esi-fleets.read_fleet.v1").require_valid().first()

        if not token:
            raise ValueError("No valid ESI token found for user")

        # Import fleet composition from ESI
        member_data, error = esi_fleet_service.import_fleet_composition(
            esi_fleet_id, token
        )

        if error:
            raise ValueError(f"ESI import failed: {error}")

        # Create ESI import record
        esi_import = ESIFleetImport.objects.create(
            fleet=fleet,
            esi_fleet_id=esi_fleet_id,
            imported_by=user,
            characters_found=len(member_data),
            raw_data=member_data,
        )

        # Process members and add as participants
        characters_added = 0
        characters_skipped = 0
        unique_players_set = set()

        for member in member_data:
            character_entity = member.get("character_entity")
            join_time = member.get("join_time")

            if not character_entity:
                logger.warning(f"Skipping member with no character entity: {member}")
                characters_skipped += 1
                continue

            # Check if participant already exists
            existing = FleetParticipant.objects.filter(
                fleet=fleet,
                character=character_entity
            ).first()

            if existing:
                characters_skipped += 1
                main_char = get_main_character_for_participant(existing)
                unique_players_set.add(main_char.id)
                continue

            # Create new participant
            participant = FleetParticipant.objects.create(
                fleet=fleet,
                character=character_entity,
                role=constants.ROLE_REGULAR,
                joined_at=join_time or timezone.now(),
            )

            # Set main character
            main_char = get_main_character_for_participant(participant)
            participant.main_character = main_char
            participant.save()

            unique_players_set.add(main_char.id)
            characters_added += 1

        # Update ESI import record
        esi_import.characters_added = characters_added
        esi_import.characters_skipped = characters_skipped
        esi_import.unique_players = len(unique_players_set)
        esi_import.save()

        logger.info(
            f"Successfully imported {characters_added} new participants "
            f"({len(unique_players_set)} unique players) "
            f"for fleet {fleet_id}"
        )

        return {
            "success": True,
            "fleet_id": fleet_id,
            "esi_import_id": esi_import.id,
            "characters_added": characters_added,
            "characters_skipped": characters_skipped,
            "unique_players": len(unique_players_set),
        }

    except Fleet.DoesNotExist:
        error_msg = f"Fleet {fleet_id} does not exist"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Unexpected error importing fleet {fleet_id}: {str(e)}"
        logger.exception(error_msg)
        return {"success": False, "error": str(e)}


@shared_task
def verify_payments_async(loot_pool_id: int, user_id: int, time_window_hours: int = 24):
    """
    Asynchronously verify payments via ESI wallet journal

    This task verifies pending payouts by checking the FC's wallet journal
    for matching ISK transfers.

    Phase 2: Week 7 - Payment Verification

    Args:
        loot_pool_id: ID of LootPool to verify payouts for
        user_id: ID of User (FC) who made the payments
        time_window_hours: Time window to search for payments (default 24 hours)

    Returns:
        Dict with verification results or error information
    """
    from django.contrib.auth.models import User
    from esi.models import Token

    from aapayout.models import LootPool
    from aapayout.services.esi_wallet import esi_wallet_service

    try:
        logger.info(
            f"Starting payment verification for loot pool {loot_pool_id}"
        )

        # Get loot pool
        loot_pool = LootPool.objects.get(id=loot_pool_id)

        # Get user
        user = User.objects.get(id=user_id)

        # Get FC's main character ID
        fc_character = user.profile.main_character
        if not fc_character:
            raise ValueError("User has no main character set")

        # Get user's ESI token with wallet journal scope
        token = Token.objects.filter(
            user=user,
        ).require_scopes("esi-wallet.read_character_journal.v1").require_valid().first()

        if not token:
            raise ValueError(
                "No valid ESI token found with wallet journal scope. "
                "Please link your ESI token with the required scope."
            )

        # Get all pending payouts for this loot pool
        pending_payouts = loot_pool.payouts.filter(
            status=constants.PAYOUT_STATUS_PENDING
        )

        if pending_payouts.count() == 0:
            logger.info(f"No pending payouts found for loot pool {loot_pool_id}")
            return {
                "success": True,
                "loot_pool_id": loot_pool_id,
                "verified_count": 0,
                "pending_count": 0,
                "errors": ["No pending payouts to verify"]
            }

        # Verify payouts via wallet journal
        verified_count, pending_count, errors = esi_wallet_service.verify_payouts(
            payouts=list(pending_payouts),
            fc_character_id=fc_character.character_id,
            token=token,
            time_window_hours=time_window_hours
        )

        logger.info(
            f"Payment verification complete for loot pool {loot_pool_id}: "
            f"{verified_count} verified, {pending_count} still pending"
        )

        return {
            "success": True,
            "loot_pool_id": loot_pool_id,
            "verified_count": verified_count,
            "pending_count": pending_count,
            "errors": errors
        }

    except LootPool.DoesNotExist:
        error_msg = f"Loot pool {loot_pool_id} does not exist"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    except User.DoesNotExist:
        error_msg = f"User {user_id} does not exist"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Unexpected error verifying payments for loot pool {loot_pool_id}: {str(e)}"
        logger.exception(error_msg)
        return {"success": False, "error": str(e)}
