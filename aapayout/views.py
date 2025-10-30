"""
Views for AA-Payout
"""

# Standard Library
import logging

# Django
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

# Alliance Auth (External Libs)
from eveuniverse.models import EveEntity

# AA Payout
from aapayout import constants
from aapayout.forms import (
    FleetCreateForm,
    FleetEditForm,
    LootItemEditForm,
    LootPoolApproveForm,
    LootPoolCreateForm,
    ParticipantAddForm,
    ParticipantEditForm,
    PayoutMarkPaidForm,
)
from aapayout.helpers import calculate_payouts, create_payouts, deduplicate_participants
from aapayout.models import Fleet, FleetParticipant, LootItem, LootPool, Payout
from aapayout.tasks import appraise_loot_pool

logger = logging.getLogger(__name__)


# ============================================================================
# FC Character Selection
# ============================================================================


@login_required
@permission_required("aapayout.basic_access")
def set_fc_character(request, character_id):
    """
    Set the FC character for the current session

    This allows users to select which of their characters to use as the FC
    for fleet operations and ESI interactions.
    """
    # Alliance Auth
    from allianceauth.authentication.models import CharacterOwnership

    # Verify the character belongs to the user
    try:
        ownership = CharacterOwnership.objects.get(user=request.user, character__character_id=character_id)

        # Store in session
        request.session["fc_character_id"] = ownership.character.character_id
        request.session["fc_character_name"] = ownership.character.character_name

        logger.info(f"User {request.user.username} set FC character to {ownership.character.character_name}")
        messages.success(request, f"FC character set to {ownership.character.character_name}")

    except CharacterOwnership.DoesNotExist:
        logger.warning(f"User {request.user.username} tried to set FC character {character_id} they don't own")
        messages.error(request, "You don't own that character")

    # Redirect back to referrer or dashboard
    return redirect(request.META.get("HTTP_REFERER", "aapayout:dashboard"))


# ============================================================================
# Dashboard
# ============================================================================


@login_required
@permission_required("aapayout.basic_access")
def dashboard(request):
    """
    Main dashboard view
    """
    # Get user's pending payouts
    main_character = request.user.profile.main_character if hasattr(request.user, "profile") else None

    pending_payouts = []
    if main_character:
        pending_payouts = Payout.objects.filter(
            recipient__id=main_character.character_id,
            status=constants.PAYOUT_STATUS_PENDING,
        ).select_related("loot_pool", "loot_pool__fleet")[:10]

    # Get recent fleets (if user is FC)
    recent_fleets = Fleet.objects.none()
    if request.user.has_perm("aapayout.create_fleet"):
        recent_fleets = Fleet.objects.filter(fleet_commander=request.user).order_by("-fleet_time")[:5]

    # Calculate stats
    total_pending = sum(p.amount for p in pending_payouts)

    context = {
        "pending_payouts": pending_payouts,
        "total_pending": total_pending,
        "recent_fleets": recent_fleets,
    }

    return render(request, "aapayout/dashboard.html", context)


# ============================================================================
# Fleet Management
# ============================================================================


@login_required
@permission_required("aapayout.basic_access")
def fleet_list(request):
    """List all fleets"""
    fleets = Fleet.objects.all().select_related("fleet_commander").order_by("-fleet_time")

    # Filter by status if provided
    status_filter = request.GET.get("status")
    if status_filter:
        fleets = fleets.filter(status=status_filter)

    # Pagination
    paginator = Paginator(fleets, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "status_filter": status_filter,
        "status_choices": constants.FLEET_STATUS_CHOICES,
    }

    return render(request, "aapayout/fleet_list.html", context)


@login_required
@permission_required("aapayout.create_fleet")
def fleet_create(request):
    """Create a new fleet"""
    if request.method == "POST":
        form = FleetCreateForm(request.POST)
        if form.is_valid():
            fleet = form.save(commit=False)
            fleet.fleet_commander = request.user
            fleet.status = constants.FLEET_STATUS_DRAFT
            fleet.save()

            messages.success(request, f"Fleet '{fleet.name}' created successfully!")
            return redirect("aapayout:fleet_detail", pk=fleet.pk)
    else:
        form = FleetCreateForm()

    context = {"form": form}
    return render(request, "aapayout/fleet_create.html", context)


@login_required
@permission_required("aapayout.basic_access")
def fleet_detail(request, pk):
    """View fleet details"""
    # Alliance Auth
    from esi.models import Token

    # AA Payout
    from aapayout import app_settings
    from aapayout.helpers import get_main_character_for_participant

    fleet = get_object_or_404(
        Fleet.objects.select_related("fleet_commander").prefetch_related(
            "participants", "loot_pools", "loot_pools__payouts"
        ),
        pk=pk,
    )

    # Get participants
    participants = fleet.participants.all().select_related("character", "main_character").order_by("joined_at")

    # Populate main_character field if not already set (Phase 2)
    updated_participants = []
    for participant in participants:
        if not participant.main_character:
            participant.main_character = get_main_character_for_participant(participant)
            participant.save()
        updated_participants.append(participant)

    # Deduplicate participants for display (group by main character)
    participant_groups = deduplicate_participants(updated_participants)

    # Get loot pools
    loot_pools = fleet.loot_pools.all().order_by("-created_at")

    # Calculate totals
    total_loot_value = fleet.get_total_loot_value()

    # Calculate payout amounts for inline display (payouts auto-created after valuation)
    payout_map = {}  # Maps main_character.id to payout amount
    existing_payouts = {}  # Maps recipient.id to Payout instance (for status tracking)
    if loot_pools.exists():
        loot_pool = loot_pools.first()

        # Payouts are automatically created when loot is valued (no approval step)
        if loot_pool.status in [constants.LOOT_STATUS_APPROVED, constants.LOOT_STATUS_PAID]:
            for payout in loot_pool.payouts.all():
                existing_payouts[payout.recipient.id] = payout
                payout_map[payout.recipient.id] = payout.amount

    # Check ESI fleet import status (Phase 2)
    # CRITICAL: Token must belong to the specific FC character, not just any character
    esi_status = {
        "enabled": app_settings.AAPAYOUT_ESI_FLEET_IMPORT_ENABLED,
        "has_scope": False,
        "can_import": False,
        "message": None,
        "fc_character_id": None,
        "fc_character_name": None,
    }

    if esi_status["enabled"] and fleet.can_edit(request.user):
        # Get FC character ID from session or use main character
        fc_character_id = request.session.get("fc_character_id")
        fc_character_name = request.session.get("fc_character_name", "Unknown")

        if not fc_character_id:
            # Fall back to main character
            fc_character = request.user.profile.main_character if hasattr(request.user, "profile") else None
            if fc_character:
                fc_character_id = fc_character.character_id
                fc_character_name = fc_character.character_name
            else:
                esi_status["message"] = "Select FC character from dropdown above"
                fc_character_id = None

        esi_status["fc_character_id"] = fc_character_id
        esi_status["fc_character_name"] = fc_character_name

        if fc_character_id:
            # CRITICAL: Check if user has valid token for THIS specific character
            token = (
                Token.objects.filter(
                    user=request.user,
                    character_id=fc_character_id,  # Must match exactly!
                )
                .require_scopes("esi-fleets.read_fleet.v1")
                .require_valid()
                .first()
            )

            if token:
                esi_status["has_scope"] = True
                esi_status["can_import"] = True
            else:
                esi_status["has_scope"] = False
                esi_status["message"] = f"ESI token required for {fc_character_name}"

    context = {
        "fleet": fleet,
        "participants": updated_participants,
        "participant_groups": participant_groups,  # Deduplicated groups for display
        "loot_pools": loot_pools,
        "total_loot_value": total_loot_value,
        "can_edit": fleet.can_edit(request.user),
        "can_delete": fleet.can_delete(request.user),
        "esi_status": esi_status,
        "payout_map": payout_map,
        "existing_payouts": existing_payouts,
    }

    return render(request, "aapayout/fleet_detail.html", context)


@login_required
@permission_required("aapayout.basic_access")
def fleet_edit(request, pk):
    """Edit a fleet"""
    fleet = get_object_or_404(Fleet, pk=pk)

    # Check permissions
    if not fleet.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this fleet")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    if request.method == "POST":
        form = FleetEditForm(request.POST, instance=fleet)
        if form.is_valid():
            form.save()
            messages.success(request, "Fleet updated successfully!")
            return redirect("aapayout:fleet_detail", pk=fleet.pk)
    else:
        form = FleetEditForm(instance=fleet)

    context = {"form": form, "fleet": fleet}
    return render(request, "aapayout/fleet_edit.html", context)


@login_required
@permission_required("aapayout.basic_access")
@require_POST
def fleet_delete(request, pk):
    """Delete a fleet"""
    fleet = get_object_or_404(Fleet, pk=pk)

    # Check permissions
    if not fleet.can_delete(request.user):
        messages.error(request, "You don't have permission to delete this fleet")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    fleet_name = fleet.name
    fleet.delete()

    messages.success(request, f"Fleet '{fleet_name}' deleted successfully!")
    return redirect("aapayout:fleet_list")


@login_required
@permission_required("aapayout.basic_access")
@require_POST
def fleet_finalize(request, pk):
    """Finalize a fleet and trigger ESI wallet verification for all payouts"""
    # Alliance Auth
    from esi.models import Token

    fleet = get_object_or_404(Fleet, pk=pk)

    # Check permissions
    if not fleet.can_edit(request.user):
        messages.error(request, "You don't have permission to finalize this fleet")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    # Check if already finalized
    if fleet.finalized:
        messages.warning(request, "This fleet has already been finalized")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    # Check if there are any payouts
    total_payouts = 0
    for loot_pool in fleet.loot_pools.all():
        total_payouts += loot_pool.payouts.count()

    if total_payouts == 0:
        messages.error(request, "Cannot finalize fleet: no payouts found")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    # Check if user has ESI token with wallet journal scope (pre-check for better UX)
    fc_character = request.user.profile.main_character
    has_esi_token = False
    if fc_character:
        token = (
            Token.objects.filter(
                user=request.user,
                character_id=fc_character.character_id,
            )
            .require_scopes("esi-wallet.read_character_journal.v1")
            .require_valid()
            .first()
        )
        has_esi_token = token is not None

    # Mark fleet as finalized
    fleet.finalized = True
    fleet.finalized_at = timezone.now()
    fleet.finalized_by = request.user
    fleet.save()

    # Trigger ESI wallet verification for all payouts
    if not has_esi_token:
        messages.warning(
            request,
            f"Fleet '{fleet.name}' has been finalized, but automatic wallet verification is not available. "
            f"You need to add an ESI token for {fc_character.character_name if fc_character else 'your main character'} "
            f"with scope 'esi-wallet.read_character_journal.v1' to enable automatic verification. "
            f"Payouts will remain as 'Pending' until verified manually or via ESI.",
        )
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    # AA Payout
    from aapayout.tasks import verify_fleet_payments

    try:
        # Launch verification task asynchronously
        task = verify_fleet_payments.delay(fleet_id=fleet.pk, user_id=request.user.pk, time_window_hours=24)
        logger.info(f"Started wallet verification task {task.id} for fleet {fleet.pk}")

        messages.success(
            request,
            f"Fleet '{fleet.name}' has been finalized! "
            f"Wallet verification is running in the background. "
            f"Verified payments will be marked automatically within a few moments. "
            f"({total_payouts} payout{'s' if total_payouts != 1 else ''} to verify)",
        )
    except Exception as e:
        logger.error(f"Failed to start verification task for fleet {fleet.pk}: {e}")
        messages.warning(
            request,
            f"Fleet '{fleet.name}' has been finalized, but automatic wallet verification could not be started. "
            f"Error: {str(e)}",
        )

    return redirect("aapayout:fleet_detail", pk=fleet.pk)


# ============================================================================
# Participant Management
# ============================================================================


@login_required
@permission_required("aapayout.basic_access")
def participant_add(request, fleet_id):
    """Add a participant to a fleet"""
    fleet = get_object_or_404(Fleet, pk=fleet_id)

    # Check permissions
    if not fleet.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this fleet")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    if request.method == "POST":
        form = ParticipantAddForm(request.POST)
        if not form.is_valid():
            # Form validation errors - show error and redirect back
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return redirect("aapayout:fleet_detail", pk=fleet.pk)

        # Get character by name
        character_name = form.cleaned_data["character_name"]
        try:
            # Filter by category (EveEntity.CATEGORY_CHARACTER constant)
            character = EveEntity.objects.get(name=character_name, category=EveEntity.CATEGORY_CHARACTER)
        except EveEntity.DoesNotExist:
            messages.error(request, f"Character '{character_name}' not found")
            return redirect("aapayout:fleet_detail", pk=fleet.pk)

        # Check if already a participant
        if FleetParticipant.objects.filter(fleet=fleet, character=character).exists():
            messages.warning(request, f"{character.name} is already in this fleet")
            return redirect("aapayout:fleet_detail", pk=fleet.pk)

        # Create participant
        participant = form.save(commit=False)
        participant.fleet = fleet
        participant.character = character
        participant.save()

        # Auto-recalculate payouts if loot exists
        if fleet.loot_pools.exists():
            loot_pool = fleet.loot_pools.first()
            if loot_pool.status in [constants.LOOT_STATUS_APPROVED, constants.LOOT_STATUS_VALUED]:
                # AA Payout
                from aapayout.helpers import create_payouts

                payouts_created = create_payouts(loot_pool)
                logger.info(f"Auto-regenerated {payouts_created} payouts after adding participant")
                if payouts_created > 0:
                    messages.info(request, f"Payouts recalculated: {payouts_created} payouts updated")

        messages.success(request, f"Added {character.name} to the fleet")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    # GET request - redirect to fleet detail (modal is used instead)
    return redirect("aapayout:fleet_detail", pk=fleet.pk)


@login_required
@permission_required("aapayout.basic_access")
def participant_edit(request, pk):
    """Edit a participant"""
    participant = get_object_or_404(FleetParticipant.objects.select_related("fleet", "character"), pk=pk)

    # Check permissions
    if not participant.fleet.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this fleet")
        return redirect("aapayout:fleet_detail", pk=participant.fleet.pk)

    if request.method == "POST":
        form = ParticipantEditForm(request.POST, instance=participant)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated {participant.character.name}")
            return redirect("aapayout:fleet_detail", pk=participant.fleet.pk)
    else:
        form = ParticipantEditForm(instance=participant)

    context = {"form": form, "participant": participant}
    return render(request, "aapayout/participant_edit.html", context)


@login_required
@permission_required("aapayout.basic_access")
@require_POST
def participant_remove(request, pk):
    """Remove a participant from a fleet"""
    participant = get_object_or_404(FleetParticipant.objects.select_related("fleet"), pk=pk)

    # Check permissions
    if not participant.fleet.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this fleet")
        return redirect("aapayout:fleet_detail", pk=participant.fleet.pk)

    fleet_pk = participant.fleet.pk
    character_name = participant.character.name
    participant.delete()

    # Auto-recalculate payouts if loot exists
    fleet = Fleet.objects.get(pk=fleet_pk)  # Re-fetch after delete
    if fleet.loot_pools.exists():
        loot_pool = fleet.loot_pools.first()
        if loot_pool.status in [constants.LOOT_STATUS_APPROVED, constants.LOOT_STATUS_VALUED]:
            # AA Payout
            from aapayout.helpers import create_payouts

            payouts_created = create_payouts(loot_pool)
            logger.info(f"Auto-regenerated {payouts_created} payouts after removing participant")
            if payouts_created > 0:
                messages.info(request, f"Payouts recalculated: {payouts_created} payouts updated")

    messages.success(request, f"Removed {character_name} from the fleet")
    return redirect("aapayout:fleet_detail", pk=fleet_pk)


# ============================================================================
# Loot Management
# ============================================================================


@login_required
@permission_required("aapayout.basic_access")
def loot_create(request, fleet_id):
    """Create a loot pool for a fleet"""
    # AA Payout
    from aapayout import app_settings

    fleet = get_object_or_404(Fleet, pk=fleet_id)

    # Check permissions
    if not fleet.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this fleet")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    # Check if fleet already has a loot pool (only one allowed per fleet)
    if fleet.loot_pools.exists():
        messages.error(request, "This fleet already has a loot pool. Only one loot pool is allowed per fleet.")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    # Warn if Janice API key is not configured
    if not app_settings.AAPAYOUT_JANICE_API_KEY:
        messages.warning(
            request,
            "Janice API key is not configured. Loot valuation will not work. "
            "Please contact your administrator to set AAPAYOUT_JANICE_API_KEY in settings.",
        )

    if request.method == "POST":
        form = LootPoolCreateForm(request.POST)
        if form.is_valid():
            loot_pool = form.save(commit=False)
            loot_pool.fleet = fleet
            loot_pool.status = constants.LOOT_STATUS_DRAFT

            logger.info(f"Creating loot pool '{loot_pool.name}' for fleet {fleet.id}")
            logger.info(f"Raw loot text length: {len(loot_pool.raw_loot_text) if loot_pool.raw_loot_text else 0} chars")

            loot_pool.save()
            logger.info(f"Loot pool {loot_pool.id} saved to database")

            # Run appraisal synchronously
            # The Janice API is fast enough that async processing is not needed,
            # and sync provides immediate feedback to the user
            logger.info(f"Running synchronous appraisal for loot pool {loot_pool.id}")
            result = appraise_loot_pool(loot_pool.id)

            if result.get("success"):
                messages.success(
                    request,
                    f"Loot pool created and valued successfully! "
                    f"{result.get('items_created')} items valued at {result.get('total_value'):,.2f} ISK. "
                    f"{result.get('payouts_created')} payouts created.",
                )
            else:
                messages.error(
                    request, f"Loot pool created but valuation failed: {result.get('error', 'Unknown error')}"
                )
                messages.info(request, "You can retry valuation from the loot pool detail page.")

            return redirect("aapayout:fleet_detail", pk=fleet.pk)
        else:
            logger.warning(f"Loot pool form validation failed for fleet {fleet.id}: {form.errors}")
    else:
        form = LootPoolCreateForm()

    context = {"form": form, "fleet": fleet}
    return render(request, "aapayout/loot_create.html", context)


@login_required
@permission_required("aapayout.basic_access")
def loot_reappraise(request, pk):
    """
    Manually trigger reappraisal of a loot pool

    Useful for debugging or if the initial appraisal failed.
    """
    loot_pool = get_object_or_404(LootPool, pk=pk)
    fleet = loot_pool.fleet

    # Check permissions
    if not fleet.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this fleet")
        return redirect("aapayout:loot_detail", pk=loot_pool.pk)

    # Check if loot pool has raw text
    if not loot_pool.raw_loot_text:
        messages.error(request, "Cannot reappraise: No loot text available")
        return redirect("aapayout:loot_detail", pk=loot_pool.pk)

    logger.info(f"Manual reappraisal requested for loot pool {loot_pool.id} by user {request.user.username}")

    # Clear existing items
    deleted_count = loot_pool.items.count()
    loot_pool.items.all().delete()
    logger.info(f"Cleared {deleted_count} existing items from loot pool {loot_pool.id}")

    # Reset status to draft
    loot_pool.status = constants.LOOT_STATUS_DRAFT
    loot_pool.save()

    # Run appraisal SYNCHRONOUSLY for manual retries
    # This ensures immediate feedback and avoids Celery worker issues
    logger.info(f"Running synchronous reappraisal for loot pool {loot_pool.id}")
    result = appraise_loot_pool(loot_pool.id)

    if result.get("success"):
        messages.success(
            request,
            f"Loot reappraised successfully! {result.get('items_created')} items valued at "
            f"{result.get('total_value'):,.2f} ISK. {result.get('payouts_created')} payouts created.",
        )
    else:
        messages.error(request, f"Reappraisal failed: {result.get('error', 'Unknown error')}")

    return redirect("aapayout:fleet_detail", pk=loot_pool.fleet.pk)


@login_required
@permission_required("aapayout.basic_access")
def loot_detail(request, pk):
    """View loot pool details"""
    loot_pool = get_object_or_404(
        LootPool.objects.select_related("fleet", "fleet__fleet_commander", "approved_by").prefetch_related(
            "items", "payouts"
        ),
        pk=pk,
    )

    # Get loot items
    loot_items = loot_pool.items.all().order_by("-total_value")

    # Get payouts if approved
    payouts = None
    if loot_pool.is_approved():
        payouts = loot_pool.payouts.all().select_related("recipient").order_by("-amount")

    context = {
        "loot_pool": loot_pool,
        "loot_items": loot_items,
        "payouts": payouts,
        "can_approve": loot_pool.can_approve(request.user),
    }

    return render(request, "aapayout/loot_detail.html", context)


@login_required
@permission_required("aapayout.basic_access")
def loot_edit_item(request, pool_id, item_id):
    """Edit a single loot item's price"""
    loot_pool = get_object_or_404(LootPool, pk=pool_id)
    loot_item = get_object_or_404(LootItem, pk=item_id, loot_pool=loot_pool)

    # Check permissions
    if not loot_pool.fleet.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this loot pool")
        return redirect("aapayout:loot_detail", pk=loot_pool.pk)

    if request.method == "POST":
        form = LootItemEditForm(request.POST, instance=loot_item)
        if form.is_valid():
            item = form.save(commit=False)
            item.manual_override = True
            item.price_source = constants.PRICE_SOURCE_MANUAL
            item.save()

            # Recalculate loot pool totals
            loot_pool.calculate_totals()

            messages.success(request, f"Updated price for {loot_item.name}")
            return redirect("aapayout:loot_detail", pk=loot_pool.pk)
    else:
        form = LootItemEditForm(instance=loot_item)

    context = {"form": form, "loot_item": loot_item, "loot_pool": loot_pool}
    return render(request, "aapayout/loot_edit_item.html", context)


@login_required
@permission_required("aapayout.basic_access")
def loot_approve(request, pk):
    """Approve a loot pool and calculate payouts"""
    loot_pool = get_object_or_404(LootPool.objects.select_related("fleet"), pk=pk)

    # Check permissions
    if not loot_pool.can_approve(request.user):
        messages.error(request, "You don't have permission to approve this loot pool")
        return redirect("aapayout:loot_detail", pk=loot_pool.pk)

    # Check if already approved
    if loot_pool.status == constants.LOOT_STATUS_APPROVED:
        messages.warning(request, "This loot pool is already approved")
        return redirect("aapayout:loot_detail", pk=loot_pool.pk)

    # Check if valued
    if loot_pool.status != constants.LOOT_STATUS_VALUED:
        messages.error(request, "Loot pool must be valued before approval")
        return redirect("aapayout:loot_detail", pk=loot_pool.pk)

    if request.method == "POST":
        form = LootPoolApproveForm(loot_pool, request.POST)
        if form.is_valid():
            # Create payouts (corp share is auto-calculated in calculate_payouts)
            payouts_created = create_payouts(loot_pool)

            # Update status
            loot_pool.status = constants.LOOT_STATUS_APPROVED
            loot_pool.approved_by = request.user
            loot_pool.approved_at = timezone.now()
            loot_pool.save()

            messages.success(request, f"Loot pool approved! Created {payouts_created} payouts.")
            return redirect("aapayout:loot_detail", pk=loot_pool.pk)
    else:
        form = LootPoolApproveForm(loot_pool)

    # Calculate payout preview for display
    payout_preview = calculate_payouts(loot_pool)

    # Calculate summary statistics
    total_payouts = sum(p["amount"] for p in payout_preview)
    scout_count = sum(1 for p in payout_preview if p["is_scout"])
    regular_count = len(payout_preview) - scout_count

    context = {
        "form": form,
        "loot_pool": loot_pool,
        "payout_preview": payout_preview,
        "total_payouts": total_payouts,
        "scout_count": scout_count,
        "regular_count": regular_count,
    }
    return render(request, "aapayout/loot_approve.html", context)


@login_required
@permission_required("aapayout.basic_access")
@require_POST
def regenerate_payouts(request, pool_id):
    """Manually regenerate payouts for a loot pool"""
    # AA Payout
    from aapayout.helpers import create_payouts

    loot_pool = get_object_or_404(LootPool, pk=pool_id)

    if not loot_pool.fleet.can_edit(request.user):
        messages.error(request, "Permission denied")
        return redirect("aapayout:fleet_detail", pk=loot_pool.fleet.pk)

    payouts_created = create_payouts(loot_pool)
    messages.success(request, f"Recalculated {payouts_created} payouts")
    logger.info(f"Manual payout recalculation by {request.user.username}: {payouts_created} payouts")

    return redirect("aapayout:fleet_detail", pk=loot_pool.fleet.pk)


# ============================================================================
# Payout Management
# ============================================================================


@login_required
@permission_required("aapayout.basic_access")
def payout_list(request, pool_id):
    """View payouts for a loot pool"""
    # Standard Library
    from decimal import Decimal

    loot_pool = get_object_or_404(LootPool.objects.select_related("fleet"), pk=pool_id)
    payouts = loot_pool.payouts.all().select_related("recipient", "paid_by").order_by("-amount")

    # Calculate statistics
    pending_count = payouts.filter(status=constants.PAYOUT_STATUS_PENDING).count()
    paid_count = payouts.filter(status=constants.PAYOUT_STATUS_PAID).count()
    pending_amount = sum(p.amount for p in payouts.filter(status=constants.PAYOUT_STATUS_PENDING)) or Decimal("0.00")
    paid_amount = sum(p.amount for p in payouts.filter(status=constants.PAYOUT_STATUS_PAID)) or Decimal("0.00")
    total_amount = sum(p.amount for p in payouts) or Decimal("0.00")

    # Check if user can mark payouts as paid
    can_mark_paid = request.user.has_perm("aapayout.approve_payouts") or loot_pool.fleet.fleet_commander == request.user

    context = {
        "loot_pool": loot_pool,
        "payouts": payouts,
        "pending_count": pending_count,
        "paid_count": paid_count,
        "pending_amount": pending_amount,
        "paid_amount": paid_amount,
        "total_amount": total_amount,
        "can_mark_paid": can_mark_paid,
    }
    return render(request, "aapayout/payout_list.html", context)


@login_required
@permission_required("aapayout.basic_access")
def payout_mark_paid(request, pk):
    """Mark a single payout as paid"""
    payout = get_object_or_404(Payout.objects.select_related("loot_pool", "recipient"), pk=pk)

    # Check permissions
    if not payout.can_mark_paid(request.user):
        messages.error(request, "You don't have permission to mark this payout as paid")
        return redirect("aapayout:payout_list", pool_id=payout.loot_pool.pk)

    if request.method == "POST":
        form = PayoutMarkPaidForm(request.POST)
        if form.is_valid():
            payout.mark_paid(request.user, form.cleaned_data.get("transaction_reference", ""))
            payout.payment_method = form.cleaned_data["payment_method"]
            if form.cleaned_data.get("notes"):
                payout.notes = form.cleaned_data["notes"]
            payout.save()

            messages.success(request, f"Marked payout to {payout.recipient.name} as paid")
            return redirect("aapayout:payout_list", pool_id=payout.loot_pool.pk)
    else:
        form = PayoutMarkPaidForm()

    context = {"form": form, "payout": payout}
    return render(request, "aapayout/payout_mark_paid.html", context)


@login_required
@permission_required("aapayout.approve_payouts")
def verify_payments(request, pool_id):
    """
    Verify payments via ESI wallet journal

    Phase 2: Week 7 - Payment Verification

    This view triggers the verification process for all pending payouts
    in a loot pool by checking the FC's wallet journal for matching transfers.
    """
    # AA Payout
    from aapayout.tasks import verify_payments_async

    loot_pool = get_object_or_404(LootPool.objects.select_related("fleet", "fleet__fleet_commander"), pk=pool_id)

    # Check permissions (must be FC or have approve_payouts permission)
    if not (request.user == loot_pool.fleet.fleet_commander or request.user.has_perm("aapayout.approve_payouts")):
        messages.error(request, "You don't have permission to verify payments for this fleet")
        return redirect("aapayout:payout_list", pool_id=pool_id)

    # Check that there are pending payouts
    pending_count = loot_pool.payouts.filter(status=constants.PAYOUT_STATUS_PENDING).count()

    if pending_count == 0:
        messages.info(request, "No pending payouts to verify")
        return redirect("aapayout:payout_list", pool_id=pool_id)

    if request.method == "POST":
        # Check if user has ESI token with wallet journal scope
        # Alliance Auth
        from esi.models import Token

        # Get FC's main character ID
        fc_character = request.user.profile.main_character if hasattr(request.user, "profile") else None
        if not fc_character:
            messages.error(request, "You need to set a main character in your profile to verify payments.")
            return redirect("aapayout:payout_list", pool_id=pool_id)

        # Get token for the specific FC character
        # IMPORTANT: ESI requires the token to match the character ID being queried
        token = (
            Token.objects.filter(
                user=request.user,
                character_id=fc_character.character_id,  # Token must match the FC character
            )
            .require_scopes("esi-wallet.read_character_journal.v1")
            .require_valid()
            .first()
        )

        if not token:
            messages.error(
                request,
                "You need to link your main character's ESI token with wallet journal access. "
                "Please add the 'esi-wallet.read_character_journal.v1' scope for your main character.",
            )
            return redirect("aapayout:payout_list", pool_id=pool_id)

        # Get time window from form (default 24 hours)
        time_window = int(request.POST.get("time_window", 24))

        # Trigger async verification task
        result = verify_payments_async.delay(
            loot_pool_id=pool_id, user_id=request.user.id, time_window_hours=time_window
        )

        messages.success(
            request, f"Payment verification started for {pending_count} pending payouts. " "This may take a moment..."
        )

        # Redirect to results page with task ID
        return redirect("aapayout:verification_results", pool_id=pool_id, task_id=result.id)

    # GET request - show confirmation form
    context = {
        "loot_pool": loot_pool,
        "pending_count": pending_count,
    }

    return render(request, "aapayout/verify_payments.html", context)


@login_required
@permission_required("aapayout.approve_payouts")
def verification_results(request, pool_id, task_id):
    """
    Display verification results

    Phase 2: Week 7 - Payment Verification

    Shows the results of the payment verification task, including
    which payouts were successfully verified and which are still pending.
    """
    # Third Party
    from celery.result import AsyncResult

    loot_pool = get_object_or_404(LootPool.objects.select_related("fleet"), pk=pool_id)

    # Get task result
    task_result = AsyncResult(task_id)

    # Check if task is complete
    if not task_result.ready():
        # Task still running - show loading page
        context = {
            "loot_pool": loot_pool,
            "task_id": task_id,
            "task_status": task_result.state,
            "loading": True,
        }
        return render(request, "aapayout/verification_results.html", context)

    # Task complete - get results
    if task_result.successful():
        result_data = task_result.result

        # Get updated payout counts
        verified_payouts = loot_pool.payouts.filter(status=constants.PAYOUT_STATUS_PAID, verified=True).select_related(
            "recipient"
        )

        pending_payouts = loot_pool.payouts.filter(status=constants.PAYOUT_STATUS_PENDING).select_related("recipient")

        context = {
            "loot_pool": loot_pool,
            "task_id": task_id,
            "task_status": "SUCCESS",
            "loading": False,
            "success": result_data.get("success", False),
            "verified_count": result_data.get("verified_count", 0),
            "pending_count": result_data.get("pending_count", 0),
            "errors": result_data.get("errors", []),
            "verified_payouts": verified_payouts,
            "pending_payouts": pending_payouts,
        }
    else:
        # Task failed
        error_message = str(task_result.result) if task_result.result else "Unknown error"

        context = {
            "loot_pool": loot_pool,
            "task_id": task_id,
            "task_status": "FAILURE",
            "loading": False,
            "success": False,
            "error": error_message,
        }

    return render(request, "aapayout/verification_results.html", context)


@login_required
@permission_required("aapayout.basic_access")
def payout_history(request):
    """
    View payout history with filtering and search

    Phase 2: Week 8 - Payout History View

    Shows payout history with the following features:
    - Filter by fleet, status, date range
    - Search by character or fleet name
    - Pagination (100 per page)
    - Summary statistics

    For regular users: Shows only their own payouts
    For users with view_all_payouts permission: Shows all payouts with full filtering
    """
    # Check if user can view all payouts
    can_view_all = request.user.has_perm("aapayout.view_all_payouts")

    # Base queryset
    if can_view_all:
        # Admin/FC view - all payouts
        payouts = Payout.objects.all()
    else:
        # Regular user - only their own payouts
        main_character = request.user.profile.main_character if hasattr(request.user, "profile") else None

        if not main_character:
            messages.warning(request, "You don't have a main character set")
            return redirect("aapayout:dashboard")

        payouts = Payout.objects.filter(recipient__id=main_character.character_id)

    # Apply filters
    fleet_id = request.GET.get("fleet")
    if fleet_id:
        payouts = payouts.filter(loot_pool__fleet_id=fleet_id)

    status = request.GET.get("status")
    if status:
        payouts = payouts.filter(status=status)

    # Date range filters
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if date_from:
        try:
            # Standard Library
            from datetime import datetime

            # Django
            from django.utils import timezone as tz

            date_from_obj = datetime.strptime(date_from, "%Y-%m-%d")
            # Make timezone aware
            date_from_obj = tz.make_aware(date_from_obj)
            payouts = payouts.filter(created_at__gte=date_from_obj)
        except ValueError:
            messages.warning(request, "Invalid date format for 'from' date")

    if date_to:
        try:
            # Standard Library
            from datetime import datetime, timedelta

            # Django
            from django.utils import timezone as tz

            date_to_obj = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            # Make timezone aware
            date_to_obj = tz.make_aware(date_to_obj)
            payouts = payouts.filter(created_at__lt=date_to_obj)
        except ValueError:
            messages.warning(request, "Invalid date format for 'to' date")

    # Search by character or fleet name
    search = request.GET.get("search")
    if search:
        payouts = payouts.filter(Q(recipient__name__icontains=search) | Q(loot_pool__fleet__name__icontains=search))

    # Optimize query with select_related
    payouts = payouts.select_related(
        "recipient", "loot_pool__fleet", "loot_pool__fleet__fleet_commander", "paid_by"
    ).order_by("-paid_at", "-created_at")

    # Calculate totals before pagination
    totals = payouts.aggregate(
        total_paid=Sum("amount", filter=Q(status=constants.PAYOUT_STATUS_PAID)),
        total_pending=Sum("amount", filter=Q(status=constants.PAYOUT_STATUS_PENDING)),
        count_paid=Count("id", filter=Q(status=constants.PAYOUT_STATUS_PAID)),
        count_pending=Count("id", filter=Q(status=constants.PAYOUT_STATUS_PENDING)),
    )

    # Pagination
    paginator = Paginator(payouts, 100)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Get fleet list for filter dropdown (only if can view all)
    fleet_list = None
    if can_view_all:
        fleet_list = Fleet.objects.filter(
            status__in=[constants.FLEET_STATUS_COMPLETED, constants.FLEET_STATUS_PAID]
        ).order_by("-fleet_time")[
            :50
        ]  # Last 50 fleets

    context = {
        "page_obj": page_obj,
        "total_paid": totals["total_paid"] or 0,
        "total_pending": totals["total_pending"] or 0,
        "count_paid": totals["count_paid"] or 0,
        "count_pending": totals["count_pending"] or 0,
        "fleet_list": fleet_list,
        "status_choices": constants.PAYOUT_STATUS_CHOICES,
        "can_view_all": can_view_all,
        # Preserve filter values in template
        "filter_fleet": fleet_id,
        "filter_status": status,
        "filter_date_from": date_from,
        "filter_date_to": date_to,
        "filter_search": search,
    }

    return render(request, "aapayout/payout_history.html", context)


# ============================================================================
# AJAX / API Views
# ============================================================================


@login_required
@permission_required("aapayout.basic_access")
def character_search(request):
    """AJAX endpoint for character autocomplete"""
    query = request.GET.get("q", "")

    if len(query) < 2:
        return JsonResponse({"results": []})

    # Search for characters
    characters = EveEntity.objects.filter(
        name__icontains=query,
        category=EveEntity.CATEGORY_CHARACTER,  # Characters only
    ).order_by("name")[:20]

    results = [{"character_id": char.id, "character_name": char.name} for char in characters]

    return JsonResponse({"results": results})


@login_required
@permission_required("aapayout.basic_access")
@require_http_methods(["POST"])
def participant_update_status(request, pk):
    """
    AJAX endpoint to update participant scout/exclude status

    Phase 2: Real-time participant controls
    """
    # Standard Library
    import json

    participant = get_object_or_404(FleetParticipant, pk=pk)

    # Check permissions
    if not participant.fleet.can_edit(request.user):
        return JsonResponse({"success": False, "error": "Permission denied"}, status=403)

    try:
        data = json.loads(request.body)

        # Update allowed fields
        if "is_scout" in data:
            participant.is_scout = bool(data["is_scout"])

        if "excluded_from_payout" in data:
            participant.excluded_from_payout = bool(data["excluded_from_payout"])

        participant.save()

        # Auto-recalculate payouts if loot exists
        payouts_recalculated = 0
        if participant.fleet.loot_pools.exists():
            loot_pool = participant.fleet.loot_pools.first()
            if loot_pool.status in [constants.LOOT_STATUS_APPROVED, constants.LOOT_STATUS_VALUED]:
                # AA Payout
                from aapayout.helpers import create_payouts

                payouts_recalculated = create_payouts(loot_pool)
                logger.info(f"Auto-regenerated {payouts_recalculated} payouts after status update for participant {pk}")

        return JsonResponse(
            {
                "success": True,
                "is_scout": participant.is_scout,
                "excluded_from_payout": participant.excluded_from_payout,
                "payouts_recalculated": payouts_recalculated,
            }
        )

    except Exception as e:
        logger.error(f"Failed to update participant {pk}: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=400)


# ==============================================================================
# Phase 2: ESI Fleet Import Views
# ==============================================================================


@login_required
@permission_required("aapayout.manage_own_fleets")
def fleet_import(request, pk):
    """
    Import fleet composition from ESI

    Allows FC to import all fleet members from an active ESI fleet.
    Requires the FC to have an ESI token with esi-fleets.read_fleet.v1 scope.

    Phase 2: Week 3-4 - ESI Fleet Import
    """
    # Alliance Auth
    from esi.models import Token

    # AA Payout
    from aapayout import app_settings
    from aapayout.helpers import get_main_character_for_participant
    from aapayout.models import ESIFleetImport, FleetParticipant
    from aapayout.services.esi_fleet import esi_fleet_service

    fleet = get_object_or_404(Fleet, pk=pk)

    # Check edit permission
    if not fleet.can_edit(request.user):
        messages.error(request, "You do not have permission to edit this fleet.")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    # Check if ESI fleet import is enabled
    if not app_settings.AAPAYOUT_ESI_FLEET_IMPORT_ENABLED:
        messages.error(request, "ESI fleet import is disabled.")
        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    if request.method == "POST":
        # Get FC character ID from session or use main character
        fc_character_id = request.session.get("fc_character_id")
        fc_character_name = request.session.get("fc_character_name", "Unknown")

        if not fc_character_id:
            # Fall back to main character
            fc_character = request.user.profile.main_character if hasattr(request.user, "profile") else None
            if not fc_character:
                messages.error(
                    request, "Please select an FC character from the dropdown in the navigation bar before importing."
                )
                return redirect("aapayout:fleet_detail", pk=fleet.pk)
            fc_character_id = fc_character.character_id
            fc_character_name = fc_character.character_name

        # Get ESI token for the specific FC character with required scope
        # CRITICAL: ESI requires the token to match the character ID being queried
        try:
            token = (
                Token.objects.filter(
                    user=request.user,
                    character_id=fc_character_id,  # Token must match the FC character
                )
                .require_scopes("esi-fleets.read_fleet.v1")
                .require_valid()
                .first()
            )

            if not token:
                messages.error(
                    request,
                    f"No ESI token found for character '{fc_character_name}' (ID: {fc_character_id}). "
                    f"Please add/update your ESI token for this specific character in Alliance Auth. "
                    f"Go to: Services → EVE Online → Add/Update Character → Select '{fc_character_name}' → "
                    f"Authorize with 'esi-fleets.read_fleet.v1' scope.",
                )
                return redirect("aapayout:fleet_detail", pk=fleet.pk)

        except Exception as e:
            logger.error(f"Failed to get ESI token for character {fc_character_id}: {e}")
            messages.error(request, "Failed to get your ESI token. Please try adding your character again.")
            return redirect("aapayout:fleet_detail", pk=fleet.pk)

        logger.info(f"Using ESI token for character {fc_character_id} ({fc_character_name})")

        # Get the fleet ID the FC is currently in
        logger.info(f"Checking if character {fc_character_id} is in a fleet")
        esi_fleet_id, fleet_role, check_error = esi_fleet_service.get_character_fleet_id(fc_character_id, token)

        if check_error or not esi_fleet_id:
            error_msg = check_error or "You are not currently in a fleet in EVE Online."
            messages.error(request, f"{error_msg} Please join a fleet and try again.")
            return redirect("aapayout:fleet_detail", pk=fleet.pk)

        # Validate fleet role - must be fleet commander to import members
        if fleet_role != "fleet_commander":
            messages.error(
                request,
                f"You must be the Fleet Commander (Fleet Boss) to import fleet members. "
                f"Your current role is '{fleet_role}'. "
                f"Please ask the FC to promote you to Fleet Boss or use their character to import.",
            )
            return redirect("aapayout:fleet_detail", pk=fleet.pk)

        logger.info(f"FC is in fleet {esi_fleet_id} with role '{fleet_role}', importing members")

        # Import fleet composition from ESI
        member_data, error = esi_fleet_service.import_fleet_composition(esi_fleet_id, token)

        if error:
            messages.error(request, f"Failed to import fleet: {error}")
            return redirect("aapayout:fleet_detail", pk=fleet.pk)

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
                char_entity = serializable_member.pop("character_entity")
                serializable_member["character_id"] = char_entity.id
                serializable_member["character_name"] = char_entity.name
            serializable_data.append(serializable_member)

        esi_import = ESIFleetImport.objects.create(
            fleet=fleet,
            esi_fleet_id=esi_fleet_id,
            imported_by=request.user,
            characters_found=len(member_data),
            raw_data=serializable_data,  # Store JSON-serializable data for debugging
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
                logger.info(f"Participant {character_entity.name} already in fleet, skipping")
                characters_skipped += 1

                # Still count for unique players
                main_char = get_main_character_for_participant(existing)
                unique_players_set.add(main_char.id)

                continue

            # Create new participant
            participant = FleetParticipant.objects.create(
                fleet=fleet,
                character=character_entity,
                role=constants.ROLE_REGULAR,  # Default role
                joined_at=join_time or timezone.now(),
            )

            # Set main character (for deduplication)
            main_char = get_main_character_for_participant(participant)
            participant.main_character = main_char
            participant.save()

            unique_players_set.add(main_char.id)
            characters_added += 1

            logger.info(f"Added participant {character_entity.name} " f"(main: {main_char.name})")

        # Update ESI import record with results
        esi_import.characters_added = characters_added
        esi_import.characters_skipped = characters_skipped
        esi_import.unique_players = len(unique_players_set)
        esi_import.save()

        # Success message
        messages.success(
            request,
            f"Successfully imported {characters_added} new participants "
            f"({len(unique_players_set)} unique players). "
            f"Skipped {characters_skipped} already in fleet.",
        )

        # Auto-recalculate payouts if loot exists
        if fleet.loot_pools.exists():
            loot_pool = fleet.loot_pools.first()
            if loot_pool.status in [constants.LOOT_STATUS_APPROVED, constants.LOOT_STATUS_VALUED]:
                # AA Payout
                from aapayout.helpers import create_payouts

                payouts_created = create_payouts(loot_pool)
                logger.info(f"Auto-regenerated {payouts_created} payouts after ESI fleet import")
                if payouts_created > 0:
                    messages.info(request, f"Payouts recalculated: {payouts_created} payouts created/updated")

        return redirect("aapayout:fleet_detail", pk=fleet.pk)

    # GET request - redirect to fleet detail (import is now inline via POST button)
    return redirect("aapayout:fleet_detail", pk=fleet.pk)


@login_required
@permission_required("aapayout.basic_access")
def fleet_import_results(request, import_id):
    """
    Display results of ESI fleet import

    Shows detailed breakdown of import results including:
    - Characters found in ESI fleet
    - Characters added to fleet
    - Characters skipped (already in fleet)
    - Unique players after deduplication

    Phase 2: Week 3-4 - ESI Fleet Import
    """
    # AA Payout
    from aapayout.models import ESIFleetImport

    esi_import = get_object_or_404(ESIFleetImport, pk=import_id)
    fleet = esi_import.fleet

    # Check basic permissions
    if not (fleet.can_edit(request.user) or request.user.has_perm("aapayout.view_all_payouts")):
        messages.error(request, "You do not have permission to view this import.")
        return redirect("aapayout:dashboard")

    context = {
        "esi_import": esi_import,
        "fleet": fleet,
    }

    return render(request, "aapayout/fleet_import_results.html", context)


# ==============================================================================
# Phase 2: Express Mode Payment Interface (Week 6)
# ==============================================================================


@login_required
@permission_required("aapayout.approve_payouts")
def express_mode_start(request, pool_id):
    """
    Start Express Mode payment interface

    Express Mode provides a keyboard-driven interface for quickly processing
    payouts. It opens character windows in the EVE client and allows the FC
    to mark payouts as paid with minimal clicks.

    Phase 2: Week 6 - Express Mode
    """
    # Standard Library
    from decimal import Decimal

    # AA Payout
    from aapayout import app_settings
    from aapayout.models import LootPool

    loot_pool = get_object_or_404(LootPool.objects.select_related("fleet"), pk=pool_id)

    # Check permissions
    if not (request.user.has_perm("aapayout.approve_payouts") or loot_pool.fleet.fleet_commander == request.user):
        messages.error(request, "You do not have permission to make payments for this fleet.")
        return redirect("aapayout:payout_list", pool_id=loot_pool.pk)

    # Check if Express Mode is enabled
    if not app_settings.AAPAYOUT_EXPRESS_MODE_ENABLED:
        messages.error(request, "Express Mode is disabled.")
        return redirect("aapayout:payout_list", pool_id=loot_pool.pk)

    # Get pending payouts
    pending_payouts = (
        loot_pool.payouts.filter(status=constants.PAYOUT_STATUS_PENDING).select_related("recipient").order_by("-amount")
    )

    if pending_payouts.count() == 0:
        messages.info(request, "No pending payouts for this loot pool.")
        return redirect("aapayout:payout_list", pool_id=loot_pool.pk)

    # Calculate statistics
    total_pending = pending_payouts.count()
    total_amount = sum(p.amount for p in pending_payouts) or Decimal("0.00")

    # Estimated time (2 seconds per payout with Express Mode)
    estimated_time_seconds = total_pending * 2
    estimated_time_minutes = estimated_time_seconds // 60

    context = {
        "loot_pool": loot_pool,
        "pending_payouts": pending_payouts,
        "total_pending": total_pending,
        "total_amount": total_amount,
        "estimated_time_minutes": estimated_time_minutes,
    }

    return render(request, "aapayout/express_mode.html", context)


@login_required
@permission_required("aapayout.approve_payouts", raise_exception=True)
@require_http_methods(["POST"])
def express_mode_open_window(request, payout_id):
    """
    AJAX endpoint to open character window in EVE client

    Uses ESI UI endpoint to open the character information window for a payout
    recipient in the EVE client.

    Phase 2: Week 6 - Express Mode
    """
    # Alliance Auth
    from esi.models import Token

    # AA Payout
    from aapayout.models import Payout
    from aapayout.services.esi_fleet import esi_ui_service

    payout = get_object_or_404(Payout.objects.select_related("recipient", "loot_pool"), pk=payout_id)

    # Check permissions
    if not payout.can_mark_paid(request.user):
        return JsonResponse({"success": False, "error": "Permission denied"}, status=403)

    try:
        # Get user's ESI token with required scope
        token = (
            Token.objects.filter(
                user=request.user,
            )
            .require_scopes("esi-ui.open_window.v1")
            .require_valid()
            .first()
        )

        if not token:
            return JsonResponse(
                {"success": False, "error": "You need an ESI token with UI window access. Please add your character."},
                status=400,
            )

        # Open character window
        success, error = esi_ui_service.open_character_window(payout.recipient.id, token)

        if not success:
            return JsonResponse({"success": False, "error": f"Failed to open window: {error}"}, status=500)

        return JsonResponse(
            {
                "success": True,
                "character_id": payout.recipient.id,
                "character_name": payout.recipient.name,
            }
        )

    except Exception as e:
        logger.error(f"Failed to open window for payout {payout_id}: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@permission_required("aapayout.approve_payouts", raise_exception=True)
@require_http_methods(["POST"])
def express_mode_mark_paid(request, payout_id):
    """
    AJAX endpoint to mark a payout as paid (Express Mode)

    This is a simplified version of the regular mark_paid endpoint optimized
    for Express Mode's keyboard-driven workflow.

    Phase 2: Week 6 - Express Mode
    """
    # AA Payout
    from aapayout.models import Payout

    payout = get_object_or_404(Payout.objects.select_related("loot_pool"), pk=payout_id)

    # Check permissions
    if not payout.can_mark_paid(request.user):
        return JsonResponse({"success": False, "error": "Permission denied"}, status=403)

    try:
        # Mark as paid
        payout.status = constants.PAYOUT_STATUS_PAID
        payout.paid_by = request.user
        payout.paid_at = timezone.now()
        payout.payment_method = constants.PAYMENT_METHOD_MANUAL  # Express Mode uses manual
        payout.save()

        return JsonResponse(
            {
                "success": True,
                "payout_id": payout.id,
                "amount": float(payout.amount),
            }
        )

    except Exception as e:
        logger.error(f"Failed to mark payout {payout_id} as paid: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
