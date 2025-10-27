# Phase 1: MVP Implementation Plan

Detailed step-by-step implementation plan for AA-Payout MVP.

**Goal**: Build a functional fleet loot management system with Janice API valuation and manual payout tracking.

---

## Overview

### MVP Features
- ✅ Create and manage fleets
- ✅ Manually add participants
- ✅ Paste loot and auto-value via Janice API
- ✅ Calculate even split + corp share
- ✅ Track payment status
- ✅ View fleet history and payouts

### Not in MVP
- ❌ ESI fleet import
- ❌ Role-based multipliers
- ❌ Automatic payments
- ❌ Advanced reporting
- ❌ Discord notifications

---

## Implementation Steps

### Step 1: Project Setup & Dependencies

#### 1.1 Update Dependencies
**File**: `pyproject.toml`

```python
dependencies = [
    "allianceauth>=4.3.1,<5",
    "django-eveuniverse>=2.0.0",
    "requests>=2.28.0",
]
```

#### 1.2 Create App Settings
**File**: `aapayout/app_settings.py`

Add configuration for:
- Janice API key
- Janice market (jita)
- Janice price type (buy)
- Corp share percentage
- Holding corporation ID
- Minimum payout threshold

#### 1.3 Create Constants File
**File**: `aapayout/constants.py`

Define:
- Fleet status choices
- Loot pool status choices
- Payout status choices
- Payment method choices
- Role choices (scout, regular)

---

### Step 2: Database Models

#### 2.1 General Model (Permissions)
**File**: `aapayout/models.py`

Update with all permissions:
- `basic_access`
- `create_fleet`
- `manage_own_fleets`
- `manage_all_fleets`
- `approve_payouts`
- `view_all_payouts`

#### 2.2 Fleet Model
**File**: `aapayout/models.py`

Fields:
- `name` (CharField, max_length=200)
- `fleet_commander` (FK to User)
- `doctrine` (CharField, optional)
- `location` (CharField)
- `fleet_time` (DateTimeField)
- `status` (CharField with choices: draft, active, completed, paid)
- `notes` (TextField, blank=True)
- `created_at` (DateTimeField, auto_now_add)
- `updated_at` (DateTimeField, auto_now)

Methods:
- `__str__()` - Return fleet name
- `get_absolute_url()` - URL to fleet detail
- `can_edit(user)` - Check if user can edit
- `can_delete(user)` - Check if user can delete
- `get_total_loot_value()` - Sum all loot pools
- `get_participant_count()` - Count participants

#### 2.3 FleetParticipant Model
**File**: `aapayout/models.py`

Fields:
- `fleet` (FK to Fleet, CASCADE)
- `character` (FK to EveCharacter from eveuniverse)
- `role` (CharField with choices: scout, regular)
- `joined_at` (DateTimeField)
- `left_at` (DateTimeField, null=True, blank=True)
- `notes` (TextField, blank=True)
- `created_at` (DateTimeField, auto_now_add)

Meta:
- `unique_together = ['fleet', 'character']`

Methods:
- `__str__()` - Return character name
- `is_active()` - Check if still in fleet

#### 2.4 LootPool Model
**File**: `aapayout/models.py`

Fields:
- `fleet` (FK to Fleet, CASCADE)
- `name` (CharField, default="Fleet Loot")
- `raw_loot_text` (TextField) - Store original paste
- `status` (CharField: draft, valuing, valued, approved, paid)
- `pricing_method` (CharField: janice_buy, janice_sell)
- `total_value` (DecimalField, max_digits=20, decimal_places=2)
- `corp_share_percentage` (DecimalField, max_digits=5, decimal_places=2)
- `corp_share_amount` (DecimalField, max_digits=20, decimal_places=2)
- `participant_share_amount` (DecimalField, max_digits=20, decimal_places=2)
- `janice_appraisal_code` (CharField, max_length=50, blank=True) - For linking to Janice
- `valued_at` (DateTimeField, null=True, blank=True)
- `approved_by` (FK to User, null=True, blank=True)
- `approved_at` (DateTimeField, null=True, blank=True)
- `created_at` (DateTimeField, auto_now_add)
- `updated_at` (DateTimeField, auto_now)

Methods:
- `__str__()` - Return pool name + fleet
- `calculate_totals()` - Sum all loot items
- `is_approved()` - Check if approved
- `can_approve(user)` - Check if user can approve

#### 2.5 LootItem Model
**File**: `aapayout/models.py`

Fields:
- `loot_pool` (FK to LootPool, CASCADE)
- `type_id` (IntegerField) - EVE type ID
- `name` (CharField, max_length=200) - Item name
- `quantity` (IntegerField)
- `unit_price` (DecimalField, max_digits=20, decimal_places=2)
- `total_value` (DecimalField, max_digits=20, decimal_places=2)
- `price_source` (CharField: janice, manual)
- `price_fetched_at` (DateTimeField)
- `manual_override` (BooleanField, default=False)
- `notes` (TextField, blank=True)

Meta:
- `ordering = ['-total_value']` - Most valuable first

Methods:
- `__str__()` - Return item name + quantity
- `save()` - Calculate total_value on save

#### 2.6 Payout Model
**File**: `aapayout/models.py`

Fields:
- `loot_pool` (FK to LootPool, CASCADE)
- `recipient` (FK to EveCharacter)
- `amount` (DecimalField, max_digits=20, decimal_places=2)
- `status` (CharField: pending, paid, failed)
- `payment_method` (CharField: manual, contract, direct_trade)
- `transaction_reference` (CharField, max_length=200, blank=True)
- `paid_by` (FK to User, null=True, blank=True)
- `paid_at` (DateTimeField, null=True, blank=True)
- `notes` (TextField, blank=True)
- `created_at` (DateTimeField, auto_now_add)

Meta:
- `ordering = ['-created_at']`

Methods:
- `__str__()` - Return recipient + amount
- `mark_paid(user, reference)` - Mark as paid
- `can_mark_paid(user)` - Check permission

#### 2.7 Model Managers
**File**: `aapayout/managers.py`

Create custom managers:
- `FleetManager` - Filter by FC, status, date range
- `PayoutManager` - Filter by recipient, status, fleet

---

### Step 3: Janice API Integration

#### 3.1 Janice Service
**File**: `aapayout/services/janice.py`

Class: `JaniceService`

Methods:
- `appraise(loot_text: str) -> List[Dict]`
  - Make API request to Janice
  - Parse response
  - Return list of items with pricing
  - Cache results (1 hour)
  - Handle errors gracefully

- `get_appraisal_url(code: str) -> str`
  - Generate link to Janice appraisal

Error handling:
- `JaniceAPIError` - Custom exception
- Log all API calls
- Retry logic for network errors

#### 3.2 Celery Task
**File**: `aapayout/tasks.py`

Tasks:
- `appraise_loot_pool(loot_pool_id)` - Async appraisal
  - Get loot pool
  - Call Janice API
  - Create LootItem records
  - Update loot pool status
  - Calculate totals

---

### Step 4: Helper Functions & Utilities

#### 4.1 Payout Calculator
**File**: `aapayout/helpers.py`

Functions:
- `calculate_payouts(loot_pool) -> List[Dict]`
  - Get total loot value
  - Calculate corp share
  - Calculate participant shares (even split)
  - Round down, remainder to corp
  - Return list of {character, amount}

- `create_payouts(loot_pool) -> None`
  - Delete existing payouts
  - Calculate new payouts
  - Create Payout records

#### 4.2 Character Helpers
**File**: `aapayout/helpers.py`

Functions:
- `search_characters(query: str) -> QuerySet`
  - Search AA characters by name
  - Return QuerySet for autocomplete

- `get_main_character(user) -> EveCharacter`
  - Get user's main character
  - Handle case where no main

---

### Step 5: Forms

#### 5.1 Fleet Forms
**File**: `aapayout/forms.py`

Forms:
- `FleetCreateForm` - Create new fleet
  - Fields: name, doctrine, location, fleet_time, notes
  - Clean methods for validation

- `FleetEditForm` - Edit existing fleet
  - Same fields as create

- `FleetCloseForm` - Close/complete fleet
  - Confirmation only

#### 5.2 Participant Forms
**File**: `aapayout/forms.py`

Forms:
- `ParticipantAddForm` - Add participant
  - Character search/select
  - Role selection
  - Joined time

- `ParticipantEditForm` - Edit participant
  - Role, times, notes

#### 5.3 Loot Forms
**File**: `aapayout/forms.py`

Forms:
- `LootPoolCreateForm` - Create loot pool
  - Name (optional, defaults to "Fleet Loot")
  - Raw loot paste (textarea)
  - Pricing method (janice_buy default)

- `LootItemEditForm` - Edit individual item
  - Unit price override
  - Notes

- `LootPoolApproveForm` - Approve loot pool
  - Corp share percentage
  - Confirmation

#### 5.4 Payout Forms
**File**: `aapayout/forms.py`

Forms:
- `PayoutMarkPaidForm` - Mark payout as paid
  - Payment method
  - Transaction reference
  - Notes

- `BulkPayoutMarkPaidForm` - Mark multiple as paid
  - Select payouts (checkboxes)
  - Payment method
  - Reference

---

### Step 6: Views & URLs

#### 6.1 Dashboard View
**File**: `aapayout/views.py`

View: `dashboard`
- Display user's pending payouts
- Display recent fleets (if FC)
- Display fleet list
- Quick stats (total ISK earned, pending payouts)

URL: `/payout/` → `aapayout:dashboard`

#### 6.2 Fleet Views
**File**: `aapayout/views.py`

Views:
- `fleet_list` - List all fleets (with filters)
- `fleet_create` - Create new fleet
- `fleet_detail` - View fleet details
- `fleet_edit` - Edit fleet
- `fleet_delete` - Delete fleet (with confirmation)
- `fleet_close` - Close/complete fleet

URLs:
- `/payout/fleets/` → `aapayout:fleet_list`
- `/payout/fleets/create/` → `aapayout:fleet_create`
- `/payout/fleets/<id>/` → `aapayout:fleet_detail`
- `/payout/fleets/<id>/edit/` → `aapayout:fleet_edit`
- `/payout/fleets/<id>/delete/` → `aapayout:fleet_delete`
- `/payout/fleets/<id>/close/` → `aapayout:fleet_close`

#### 6.3 Participant Views
**File**: `aapayout/views.py`

Views:
- `participant_add` - Add participant to fleet
- `participant_edit` - Edit participant
- `participant_remove` - Remove participant

URLs:
- `/payout/fleets/<fleet_id>/participants/add/` → `aapayout:participant_add`
- `/payout/participants/<id>/edit/` → `aapayout:participant_edit`
- `/payout/participants/<id>/remove/` → `aapayout:participant_remove`

#### 6.4 Loot Views
**File**: `aapayout/views.py`

Views:
- `loot_create` - Create loot pool (paste loot)
- `loot_detail` - View loot items
- `loot_value` - Trigger Janice appraisal
- `loot_edit_item` - Edit individual item price
- `loot_approve` - Approve loot pool for payout

URLs:
- `/payout/fleets/<fleet_id>/loot/create/` → `aapayout:loot_create`
- `/payout/loot/<id>/` → `aapayout:loot_detail`
- `/payout/loot/<id>/value/` → `aapayout:loot_value`
- `/payout/loot/<id>/items/<item_id>/edit/` → `aapayout:loot_edit_item`
- `/payout/loot/<id>/approve/` → `aapayout:loot_approve`

#### 6.5 Payout Views
**File**: `aapayout/views.py`

Views:
- `payout_list` - View payouts for loot pool
- `payout_mark_paid` - Mark single payout as paid
- `payout_bulk_paid` - Mark multiple as paid
- `payout_history` - View user's payout history

URLs:
- `/payout/loot/<pool_id>/payouts/` → `aapayout:payout_list`
- `/payout/payouts/<id>/mark-paid/` → `aapayout:payout_mark_paid`
- `/payout/loot/<pool_id>/payouts/bulk-paid/` → `aapayout:payout_bulk_paid`
- `/payout/history/` → `aapayout:payout_history`

#### 6.6 AJAX/API Views
**File**: `aapayout/views.py`

Views:
- `character_search` - JSON endpoint for character autocomplete
- `loot_status` - JSON endpoint for checking appraisal status

---

### Step 7: Templates

#### 7.1 Base Templates
**Files**: `aapayout/templates/aapayout/`

Templates:
- `base.html` - Base template (already exists, update)
- `_messages.html` - Django messages partial
- `_confirm_modal.html` - Confirmation modal component

#### 7.2 Dashboard Templates
**Files**: `aapayout/templates/aapayout/`

Templates:
- `dashboard.html` - Main dashboard
  - Pending payouts card
  - Recent fleets card
  - Quick actions
  - Stats summary

#### 7.3 Fleet Templates
**Files**: `aapayout/templates/aapayout/fleets/`

Templates:
- `fleet_list.html` - Fleet list with filters
- `fleet_create.html` - Create fleet form
- `fleet_detail.html` - Fleet detail view
  - Fleet info header
  - Participants table
  - Loot pools section
  - Actions buttons
- `fleet_edit.html` - Edit fleet form
- `fleet_delete_confirm.html` - Delete confirmation

#### 7.4 Participant Templates
**Files**: `aapayout/templates/aapayout/participants/`

Templates:
- `_participant_table.html` - Reusable participant table
- `participant_add.html` - Add participant form
- `participant_edit.html` - Edit participant form

#### 7.5 Loot Templates
**Files**: `aapayout/templates/aapayout/loot/`

Templates:
- `loot_create.html` - Loot paste form
- `loot_detail.html` - Loot items table
  - Item list with values
  - Total summary
  - Approve button
- `loot_edit_item.html` - Edit item price
- `loot_approve.html` - Approve loot pool
  - Preview payouts
  - Corp share config

#### 7.6 Payout Templates
**Files**: `aapayout/templates/aapayout/payouts/`

Templates:
- `payout_list.html` - Payout list for loot pool
  - Table with recipient, amount, status
  - Bulk actions
- `payout_mark_paid.html` - Mark paid form
- `payout_history.html` - User payout history

---

### Step 8: Static Files

#### 8.1 CSS
**File**: `aapayout/static/aapayout/css/aapayout.css`

Styles for:
- Fleet cards
- Loot item tables
- Payout status badges
- ISK amount formatting
- Responsive layouts

#### 8.2 JavaScript
**File**: `aapayout/static/aapayout/js/aapayout.js`

Functions for:
- Character autocomplete
- AJAX form submissions
- Dynamic form validation
- ISK number formatting
- Confirmation modals
- Bulk selection checkboxes

---

### Step 9: Admin Interface

#### 9.1 Admin Models
**File**: `aapayout/admin.py`

Register models with custom admin:
- `FleetAdmin` - List, search, filters
- `FleetParticipantAdmin` - Inline on Fleet
- `LootPoolAdmin` - List, search, actions
- `LootItemAdmin` - Inline on LootPool
- `PayoutAdmin` - List, search, filters, actions

Features:
- List display customization
- Search fields
- Date filters
- Custom actions (approve, mark paid)
- Readonly fields where appropriate

---

### Step 10: Testing

#### 10.1 Model Tests
**File**: `aapayout/tests/test_models.py`

Test cases:
- Fleet CRUD operations
- Participant uniqueness
- LootPool calculations
- Payout amount calculations
- Permission checks

#### 10.2 View Tests
**File**: `aapayout/tests/test_views.py`

Test cases:
- Dashboard access
- Fleet create/edit/delete
- Participant management
- Permission enforcement
- URL routing

#### 10.3 Service Tests
**File**: `aapayout/tests/test_services.py`

Test cases:
- Janice API mocking
- Error handling
- Cache behavior
- Payout calculations

#### 10.4 Integration Tests
**File**: `aapayout/tests/test_integration.py`

Test complete workflows:
- Create fleet → Add participants → Add loot → Approve → Payouts
- Mark payouts as paid
- Permission scenarios

---

### Step 11: Documentation

#### 11.1 Update README
**File**: `README.md`

Add:
- Installation instructions with django-eveuniverse
- Configuration examples
- Basic usage walkthrough
- Screenshots (optional)

#### 11.2 User Guide
**File**: `docs/USER_GUIDE.md`

Create guide with:
- How to create a fleet
- How to add participants
- How to paste and value loot
- How to approve payouts
- How to mark payments

#### 11.3 Admin Guide
**File**: `docs/ADMIN_GUIDE.md`

Create guide with:
- Initial setup
- Permission configuration
- Corporation configuration
- Janice API key setup
- Troubleshooting

---

## Implementation Order

### Week 1: Foundation
- [ ] Step 1: Project setup & dependencies
- [ ] Step 2: Database models (all)
- [ ] Step 3.1: Janice service (basic)
- [ ] Run migrations, test models in shell

### Week 2: Core Functionality
- [ ] Step 3.2: Celery task for appraisal
- [ ] Step 4: Helper functions
- [ ] Step 5: Forms (fleet & loot)
- [ ] Step 6.1-6.2: Dashboard & fleet views

### Week 3: Loot & Valuation
- [ ] Step 6.4: Loot views
- [ ] Step 7.2-7.3: Dashboard & fleet templates
- [ ] Step 7.5: Loot templates
- [ ] Test loot paste → Janice → display

### Week 4: Payouts & Polish
- [ ] Step 6.5: Payout views
- [ ] Step 6.3: Participant views
- [ ] Step 7.4: Participant templates
- [ ] Step 7.6: Payout templates

### Week 5: Admin & Testing
- [ ] Step 8: Static files (CSS/JS)
- [ ] Step 9: Admin interface
- [ ] Step 10: Testing (basic coverage)

### Week 6: Documentation & Release
- [ ] Step 11: Documentation
- [ ] Manual testing with real data
- [ ] Bug fixes
- [ ] MVP Release

---

## Definition of Done (DoD)

### Per Feature
- [ ] Code written and follows Django/AA conventions
- [ ] Permissions enforced correctly
- [ ] Error handling implemented
- [ ] Basic tests written
- [ ] Works with example data
- [ ] No console errors

### MVP Complete
- [ ] All models created and migrated
- [ ] Can create fleet with participants
- [ ] Can paste loot and get Janice valuation
- [ ] Can approve loot pool
- [ ] Payouts calculated correctly (even split + corp share)
- [ ] Can mark payouts as paid
- [ ] Can view payout history
- [ ] Admin interface functional
- [ ] Basic documentation complete
- [ ] No critical bugs

---

## Success Metrics

### Functionality
- FC can complete full workflow in < 5 minutes
- Loot appraisal completes in < 10 seconds
- Payout calculations are accurate (no rounding errors > 0.01 ISK)
- Supports up to 1T ISK without precision issues

### Usability
- No more than 3 clicks to complete common tasks
- Forms have helpful validation messages
- Status indicators are clear
- ISK amounts are readable (formatted with commas)

### Technical
- Page load times < 2 seconds
- No N+1 query issues
- Proper use of Django ORM
- Clean separation of concerns

---

## Risk Mitigation

### Technical Risks
| Risk | Mitigation |
|------|------------|
| Janice API down | Cache results, allow manual override |
| Decimal precision issues | Use DecimalField, test with large values |
| Character not in AA | Show error, suggest adding to AA |
| Concurrent edits | Use Django ORM transactions |

### User Risks
| Risk | Mitigation |
|------|------------|
| Paste wrong loot | Allow review before approval |
| Miscalculate shares | Show preview before finalizing |
| Forget to mark paid | Highlight pending payouts on dashboard |
| Lose data | No soft deletes needed, admin can recover |

---

## Next Steps After Phase 1

Once MVP is complete and tested:

1. **Gather feedback** from real usage
2. **Fix bugs** and UX issues
3. **Plan Phase 2** (ESI integration)
4. **Optimize** performance if needed
5. **Add requested features** from users

---

## Questions During Implementation

As you implement, these questions may come up:

### Database
- Should we soft-delete fleets or hard-delete?
- Should we track edit history?
- Do we need database indexes beyond PKs/FKs?

### UX
- Should we auto-save drafts?
- Should we show ISK in millions/billions or full amounts?
- Should we email/notify users of new payouts?

### Technical
- Should we use Django Rest Framework for AJAX views?
- Should we add GraphQL support?
- Should we use htmx for dynamic updates?

**Recommendation**: Start simple, add complexity only if needed. Use Django's built-in features first.
