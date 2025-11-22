"""App URLs"""

# Django
from django.urls import path

# AA Payout
from aapayout import views

app_name: str = "aapayout"

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),
    # FC Character Selection
    path("set-fc/<int:character_id>/", views.set_fc_character, name="set_fc_character"),
    # ESI OAuth Redirect Views
    path("esi/add-fleet-scope/", views.add_esi_fleet_scope, name="add_esi_fleet_scope"),
    path("esi/add-wallet-scope/", views.add_esi_wallet_scope, name="add_esi_wallet_scope"),
    # Fleet Management
    path("fleets/", views.dashboard, name="fleet_list"),  # Redirect to dashboard
    path("fleets/create/", views.fleet_create, name="fleet_create"),
    path("fleets/<int:pk>/", views.fleet_detail, name="fleet_detail"),
    path("fleets/<int:pk>/edit/", views.fleet_edit, name="fleet_edit"),
    path("fleets/<int:pk>/delete/", views.fleet_delete, name="fleet_delete"),
    path("fleets/<int:pk>/finalize/", views.fleet_finalize, name="fleet_finalize"),
    path("fleets/<int:pk>/verify-payouts/", views.fleet_verify_payouts, name="fleet_verify_payouts"),
    # Participant Management
    path("fleets/<int:fleet_id>/participants/add/", views.participant_add, name="participant_add"),
    path("participants/<int:pk>/edit/", views.participant_edit, name="participant_edit"),
    path("participants/<int:pk>/remove/", views.participant_remove, name="participant_remove"),
    # Loot Management
    path("fleets/<int:fleet_id>/loot/create/", views.loot_create, name="loot_create"),
    path("loot/<int:pk>/", views.loot_detail, name="loot_detail"),
    path("loot/<int:pk>/edit/", views.loot_edit, name="loot_edit"),
    path("loot/<int:pk>/reappraise/", views.loot_reappraise, name="loot_reappraise"),
    path("loot/<int:pk>/approve/", views.loot_approve, name="loot_approve"),
    path("loot/<int:pool_id>/regenerate-payouts/", views.regenerate_payouts, name="regenerate_payouts"),
    # Payout Management
    path("loot/<int:pool_id>/payouts/", views.payout_list, name="payout_list"),
    path("payouts/<int:pk>/mark-paid/", views.payout_mark_paid, name="payout_mark_paid"),
    path("payouts/history/", views.payout_history, name="payout_history"),
    # Phase 2: Payment Verification
    path("loot/<int:pool_id>/verify/", views.verify_payments, name="verify_payments"),
    path("loot/<int:pool_id>/verification/<str:task_id>/", views.verification_results, name="verification_results"),
    # AJAX / API
    path("api/character-search/", views.character_search, name="character_search"),
    path("api/participant/<int:pk>/update/", views.participant_update_status, name="participant_update_status"),
    path("api/loot/<int:pool_id>/update-scout-bonus/", views.update_scout_bonus, name="update_scout_bonus"),
    # Phase 2: ESI Fleet Import
    path("fleets/<int:pk>/import/", views.fleet_import, name="fleet_import"),
    path("imports/<int:import_id>/results/", views.fleet_import_results, name="fleet_import_results"),
    # Phase 2: Express Mode Payment Interface
    path("loot/<int:pool_id>/express-mode/", views.express_mode_start, name="express_mode_start"),
    path("api/payouts/<int:payout_id>/open-window/", views.express_mode_open_window, name="express_mode_open_window"),
    path("api/payouts/<int:payout_id>/mark-paid-express/", views.express_mode_mark_paid, name="express_mode_mark_paid"),
    path("api/payouts/<int:payout_id>/mark-verified/", views.mark_payout_verified, name="mark_payout_verified"),
]
