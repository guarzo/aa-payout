"""App Tasks"""

# Standard Library
import logging

# Third Party
from celery import shared_task

# Django
from django.utils import timezone

# AA Payout
from aapayout import constants
from aapayout.helpers import create_loot_items_from_appraisal
from aapayout.models import LootPool
from aapayout.services.janice import JaniceAPIError, JaniceService

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def appraise_loot_pool(self, loot_pool_id: int = None):
    """
    Asynchronously appraise a loot pool via Janice API

    This task:
    1. Retrieves the loot pool by ID
    2. Calls the Janice API with the raw loot text
    3. Creates LootItem records from the appraisal
    4. Updates the loot pool status

    Args:
        loot_pool_id: ID of LootPool to appraise (or self when called directly)

    Returns:
        Dict with results or error information
    """
    # Handle both Celery execution (bind=True) and direct function call
    # When called via Celery: self=task instance, loot_pool_id=the ID
    # When called directly: self=the ID, loot_pool_id=None
    if loot_pool_id is None:
        # Direct call: self is actually the loot_pool_id
        actual_loot_pool_id = self
        task_id = "sync"
        is_celery = False
    else:
        # Celery call: self is task instance
        actual_loot_pool_id = loot_pool_id
        task_id = self.request.id if hasattr(self, "request") else "unknown"
        is_celery = True

    # DEBUGGING: Print to stdout (will show in worker logs if Celery)
    print("=" * 80)
    print(f"[TASK] Starting appraise_loot_pool for loot_pool_id={actual_loot_pool_id}")
    print(f"[TASK] Task ID: {task_id} (Celery: {is_celery})")
    print("=" * 80)

    logger.info(f"[Task {task_id}] TASK STARTED for loot pool {actual_loot_pool_id}")
    if is_celery and hasattr(self, "name"):
        logger.info(f"[Task {task_id}] Task name: {self.name}")

    try:
        logger.info(f"[Task {task_id}] Starting appraisal for loot pool {actual_loot_pool_id}")

        # Get loot pool
        loot_pool = LootPool.objects.get(id=actual_loot_pool_id)
        logger.info(f"[Task] Found loot pool {actual_loot_pool_id}: '{loot_pool.name}'")
        logger.info(f"[Task] Current status: {loot_pool.status}")

        # Update status to valuing
        loot_pool.status = constants.LOOT_STATUS_VALUING
        loot_pool.save()
        logger.info(f"[Task] Updated status to VALUING for loot pool {actual_loot_pool_id}")

        # Get raw loot text
        loot_text = loot_pool.raw_loot_text
        logger.info(f"[Task] Raw loot text length: {len(loot_text) if loot_text else 0} chars")

        if not loot_text or not loot_text.strip():
            error_msg = "Loot pool has no loot text to appraise"
            logger.error(f"[Task] {error_msg} for loot pool {actual_loot_pool_id}")
            raise ValueError(error_msg)

        # Log first 200 chars of loot text for debugging
        logger.debug(f"[Task] Loot text preview: {loot_text[:200]}")

        # Call Janice API
        logger.info(f"[Task] Calling Janice API for loot pool {actual_loot_pool_id}")
        appraisal_data = JaniceService.appraise(loot_text)
        logger.info(f"[Task] Janice API returned {len(appraisal_data.get('items', []))} items")

        # Create LootItem records
        logger.info("[Task] Creating loot items from appraisal data")
        items_created = create_loot_items_from_appraisal(loot_pool, appraisal_data)
        logger.info(f"[Task] Created {items_created} loot items")

        # Update valued_at timestamp
        loot_pool.valued_at = timezone.now()
        loot_pool.save()
        logger.info("[Task] Updated valued_at timestamp")

        # Automatically create payouts (no manual approval needed)
        logger.info("[Task] Auto-generating payouts after valuation")
        # AA Payout
        from aapayout.helpers import create_payouts

        payouts_created = create_payouts(loot_pool)
        logger.info(f"[Task] Auto-created {payouts_created} payouts")

        if payouts_created == 0:
            logger.warning(
                f"[Task] Created 0 payouts for loot pool {actual_loot_pool_id}. "
                f"This is normal if fleet has no participants yet. "
                f"Payouts will be auto-generated when participants are added."
            )

        # Mark as approved since payouts are generated
        loot_pool.status = constants.LOOT_STATUS_APPROVED
        loot_pool.approved_at = timezone.now()
        # Note: approved_by is None for auto-approval
        loot_pool.save()

        logger.info(
            f"[Task] Successfully appraised loot pool {actual_loot_pool_id}: "
            f"{items_created} items, "
            f"total value {loot_pool.total_value:,.2f} ISK, "
            f"{payouts_created} payouts auto-generated"
        )

        # DEBUGGING: Print success to stdout
        print(
            f"[TASK] SUCCESS: Appraised {items_created} items, total {loot_pool.total_value:,.2f} ISK, {payouts_created} payouts"
        )
        print("=" * 80)

        return {
            "success": True,
            "loot_pool_id": actual_loot_pool_id,
            "items_created": items_created,
            "total_value": float(loot_pool.total_value),
            "payouts_created": payouts_created,
        }

    except LootPool.DoesNotExist:
        error_msg = f"Loot pool {actual_loot_pool_id} does not exist"
        print(f"[TASK] ERROR: {error_msg}")
        logger.error(f"[Task] {error_msg}")
        return {"success": False, "error": error_msg}

    except JaniceAPIError as e:
        error_msg = f"Janice API error for loot pool {actual_loot_pool_id}: {str(e)}"
        print(f"[TASK] JANICE ERROR: {error_msg}")
        logger.error(f"[Task] {error_msg}")

        # Update loot pool status back to draft on API error
        try:
            loot_pool = LootPool.objects.get(id=actual_loot_pool_id)
            logger.info(f"[Task] Reverting loot pool {actual_loot_pool_id} status to DRAFT due to API error")
            loot_pool.status = constants.LOOT_STATUS_DRAFT
            loot_pool.save()
        except Exception as revert_error:
            logger.error(f"[Task] Failed to revert status for loot pool {actual_loot_pool_id}: {revert_error}")

        return {"success": False, "error": str(e)}

    except Exception as e:
        error_msg = f"Unexpected error appraising loot pool {actual_loot_pool_id}: {str(e)}"
        print(f"[TASK] UNEXPECTED ERROR: {error_msg}")
        print(f"[TASK] Exception type: {type(e)}")
        # Standard Library
        import traceback

        print(traceback.format_exc())
        logger.exception(f"[Task] {error_msg}")

        # Update loot pool status back to draft on unexpected error
        try:
            loot_pool = LootPool.objects.get(id=actual_loot_pool_id)
            logger.info(f"[Task] Reverting loot pool {actual_loot_pool_id} status to DRAFT due to unexpected error")
            loot_pool.status = constants.LOOT_STATUS_DRAFT
            loot_pool.save()
        except Exception as revert_error:
            logger.error(f"[Task] Failed to revert status for loot pool {actual_loot_pool_id}: {revert_error}")

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
    # Django
    from django.contrib.auth.models import User

    # Alliance Auth
    from esi.models import Token

    # AA Payout
    from aapayout.helpers import get_main_character_for_participant
    from aapayout.models import ESIFleetImport, Fleet, FleetParticipant
    from aapayout.services.esi_fleet import esi_fleet_service

    try:
        logger.info(f"Starting async fleet import for fleet {fleet_id} " f"from ESI fleet {esi_fleet_id}")

        # Get fleet
        fleet = Fleet.objects.get(id=fleet_id)

        # Get user
        user = User.objects.get(id=user_id)

        # Get user's ESI token
        token = (
            Token.objects.filter(
                user=user,
            )
            .require_scopes("esi-fleets.read_fleet.v1")
            .require_valid()
            .first()
        )

        if not token:
            raise ValueError("No valid ESI token found for user")

        # Import fleet composition from ESI
        member_data, error = esi_fleet_service.import_fleet_composition(esi_fleet_id, token)

        if error:
            raise ValueError(f"ESI import failed: {error}")

        # Create ESI import record
        # Convert member_data to JSON-serializable format
        serializable_data = []
        for member in member_data:
            serializable_member = member.copy()
            # Convert datetime to ISO format string
            if "join_time" in serializable_member and serializable_member["join_time"]:
                serializable_member["join_time"] = serializable_member["join_time"].isoformat()
            # Convert EveEntity to character ID and name
            if "character_entity" in serializable_member:
                char_entity = serializable_member.get("character_entity")
                if char_entity:
                    serializable_member["character_id"] = char_entity.id
                    serializable_member["character_name"] = char_entity.name
                serializable_member.pop("character_entity", None)
            serializable_data.append(serializable_member)

        esi_import = ESIFleetImport.objects.create(
            fleet=fleet,
            esi_fleet_id=esi_fleet_id,
            imported_by=user,
            characters_found=len(member_data),
            raw_data=serializable_data,
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
            existing = FleetParticipant.objects.filter(fleet=fleet, character=character_entity).first()

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
    # Django
    from django.contrib.auth.models import User

    # Alliance Auth
    from esi.models import Token

    # AA Payout
    from aapayout.models import LootPool
    from aapayout.services.esi_wallet import esi_wallet_service

    try:
        logger.info(f"Starting payment verification for loot pool {loot_pool_id}")

        # Get loot pool
        loot_pool = LootPool.objects.get(id=loot_pool_id)

        # Get user
        user = User.objects.get(id=user_id)

        # Get FC's main character ID
        fc_character = user.profile.main_character
        if not fc_character:
            raise ValueError("User has no main character set")

        # Get user's ESI token with wallet journal scope for the specific FC character
        # IMPORTANT: ESI requires the token to match the character ID being queried
        token = (
            Token.objects.filter(
                user=user,
                character_id=fc_character.character_id,  # Token must match the FC character
            )
            .require_scopes("esi-wallet.read_character_wallet.v1")
            .require_valid()
            .first()
        )

        if not token:
            raise ValueError(
                f"No valid ESI token found for FC character {fc_character.character_id} with wallet journal scope. "
                "Please link your FC character's ESI token with the required scope."
            )

        # Get all pending payouts for this loot pool
        pending_payouts = loot_pool.payouts.filter(status=constants.PAYOUT_STATUS_PENDING)

        if pending_payouts.count() == 0:
            logger.info(f"No pending payouts found for loot pool {loot_pool_id}")
            return {
                "success": True,
                "loot_pool_id": loot_pool_id,
                "verified_count": 0,
                "pending_count": 0,
                "errors": ["No pending payouts to verify"],
            }

        # Verify payouts via wallet journal
        verified_count, pending_count, errors = esi_wallet_service.verify_payouts(
            payouts=list(pending_payouts),
            fc_character_id=fc_character.character_id,
            token=token,
            time_window_hours=time_window_hours,
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
            "errors": errors,
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


@shared_task
def verify_fleet_payments(fleet_id: int, user_id: int, time_window_hours: int = 24):
    """
    Verify all payments for a fleet via ESI wallet journal

    This task is triggered when a fleet is finalized. It verifies all pending
    payouts across all loot pools in the fleet by checking the FC's wallet journal.

    Args:
        fleet_id: ID of Fleet to verify payments for
        user_id: ID of User (FC) who made the payments
        time_window_hours: Time window to search for payments (default 24 hours)

    Returns:
        Dict with verification results or error information
    """
    # Django
    from django.contrib.auth.models import User

    # Alliance Auth
    from esi.models import Token

    # AA Payout
    from aapayout.models import Fleet, Payout
    from aapayout.services.esi_wallet import esi_wallet_service

    try:
        logger.info(f"Starting fleet payment verification for fleet {fleet_id}")

        # Get fleet
        fleet = Fleet.objects.get(id=fleet_id)

        # Get user
        user = User.objects.get(id=user_id)

        # Get FC's main character
        fc_character = user.profile.main_character
        if not fc_character:
            raise ValueError("User has no main character set")

        # Get user's ESI token with wallet journal scope for the FC character
        token = (
            Token.objects.filter(
                user=user,
                character_id=fc_character.character_id,
            )
            .require_scopes("esi-wallet.read_character_wallet.v1")
            .require_valid()
            .first()
        )

        if not token:
            error_msg = (
                f"No valid ESI token found for FC character {fc_character.character_name} "
                f"with wallet journal scope. Please link your FC character's ESI token "
                f"with scope 'esi-wallet.read_character_wallet.v1' in the Alliance Auth dashboard."
            )
            logger.warning(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "requires_esi": True,
            }

        # Get all pending payouts for this fleet (across all loot pools)
        pending_payouts = Payout.objects.filter(
            loot_pool__fleet=fleet,
            status=constants.PAYOUT_STATUS_PENDING,
        )

        total_payouts = pending_payouts.count()

        if total_payouts == 0:
            logger.info(f"No pending payouts found for fleet {fleet_id}")
            return {
                "success": True,
                "fleet_id": fleet_id,
                "total_payouts": 0,
                "verified_count": 0,
                "pending_count": 0,
                "message": "No pending payouts to verify",
            }

        # Verify payouts via wallet journal
        verified_count, pending_count, errors = esi_wallet_service.verify_payouts(
            payouts=list(pending_payouts),
            fc_character_id=fc_character.character_id,
            token=token,
            time_window_hours=time_window_hours,
        )

        logger.info(
            f"Fleet payment verification complete for fleet {fleet_id}: "
            f"{verified_count}/{total_payouts} verified, {pending_count} still pending"
        )

        return {
            "success": True,
            "fleet_id": fleet_id,
            "total_payouts": total_payouts,
            "verified_count": verified_count,
            "pending_count": pending_count,
            "errors": errors,
            "verification_rate": f"{(verified_count / total_payouts * 100):.1f}%" if total_payouts > 0 else "0%",
        }

    except Fleet.DoesNotExist:
        error_msg = f"Fleet {fleet_id} does not exist"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    except User.DoesNotExist:
        error_msg = f"User {user_id} does not exist"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Unexpected error verifying fleet payments for fleet {fleet_id}: {str(e)}"
        logger.exception(error_msg)
        return {"success": False, "error": str(e)}
