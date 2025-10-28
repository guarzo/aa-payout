# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AA-Payout is an Alliance Auth plugin for EVE Online that allows fleet commanders to value loot from PvP engagements and distribute ISK payouts to participating pilots.

**Current Status:** Phase 1 (MVP) is **COMPLETE** (2025-10-27). Phase 2 planning is approved and ready for implementation.

## Key Architecture

### Django Plugin Structure
This is an Alliance Auth plugin following the standard AA plugin architecture:
- `aapayout/` - Main plugin package
- `testauth/` - Test Django environment for development
- Alliance Auth integration via `auth_hooks.py` (menu items, URL hooks)
- Plugin registers at URL pattern `/payout/` in Alliance Auth

### Core Workflow (Phase 1 - COMPLETE)
1. FC creates fleet and adds participants manually
2. FC pastes raw loot from EVE client
3. System values loot via **Janice API** (Jita buy prices)
4. System calculates even split among participants + corporation share
5. FC approves payouts
6. FC marks payments as completed

### Core Workflow (Phase 2 - PLANNED)
1. **ESI Fleet Import**: FC imports fleet composition from ESI (auto-adds all participants)
2. **Character Deduplication**: System groups alts by main character (one payout per human)
3. **Scout Marking**: FC marks scouts manually (receives +10% ISK bonus)
4. FC pastes raw loot from EVE client
5. System values loot via Janice API
6. System calculates payouts with scout bonuses and deduplication
7. FC approves payouts
8. **Express Mode Payment**: FC uses optimized payment interface with ESI window opening (~80% time savings)
9. **Payment Verification**: System verifies payments via ESI wallet journal

### Data Models (Phase 1 - COMPLETE)
- **Fleet**: Fleet operations with FC, time, location, status (IMPLEMENTED)
- **FleetParticipant**: Participants with join/leave times (IMPLEMENTED)
- **LootPool**: Container for loot from a fleet with pricing method, corp share (IMPLEMENTED)
- **LootItem**: Individual items with Janice API pricing (IMPLEMENTED)
- **Payout**: Payment records with status tracking, payment method (IMPLEMENTED)

### Data Models (Phase 2 - PLANNED)
- **FleetParticipant additions**: `is_scout`, `excluded_from_payout`, `main_character` fields
- **Payout additions**: `is_scout_payout`, `verified`, `verified_at` fields
- **ESIFleetImport**: Tracks ESI fleet composition imports
- ~~PayoutRule~~: Not needed (Phase 2 uses simple +10% scout bonus, not complex rules)

### External Integrations

#### Janice API (Phase 1 - IMPLEMENTED)
- Primary loot valuation service (https://janice.e-351.com/api/rest/v2)
- Endpoint: `POST /pricer?market=jita`
- Requires API key in `X-ApiKey` header
- See JANICE_API.md for complete integration details

#### django-eveuniverse (Phase 1 - IMPLEMENTED)
- EVE type data (items, characters) via EveEntity model
- Character lookups and references

#### ESI Integration (Phase 2 - PLANNED)
**Required Scopes:**
```python
'esi-ui.open_window.v1'                   # Open character windows (Express Mode)
'esi-fleets.read_fleet.v1'                # Import fleet composition
'esi-wallet.read_character_wallet.v1'     # Check FC wallet balance (optional)
'esi-wallet.read_character_journal.v1'    # Verify payments post-transfer
'esi-mail.send_mail.v1'                   # Send payout notifications (optional)
```

**ESI Capabilities:**
- ✅ Fleet import: `GET /v1/fleets/{fleet_id}/members/`
- ✅ Open character windows: `POST /v1/ui/openwindow/information/`
- ✅ Wallet journal verification: `GET /v1/characters/{character_id}/wallet/journal/`

**ESI Limitations (Research Confirmed):**
- ❌ No direct ISK transfer endpoint exists
- ❌ Contracts are read-only (cannot create via ESI)
- ❌ Pre-fill ISK transfer window requested since 2016 (Issue #190), never implemented

**Express Mode Approach:**
Instead of full payment automation (not possible), we use ESI to open character windows in EVE client, reducing manual payment time from ~40min to ~7-8min for 20 payouts (~80% time savings).

### Payout Calculation

#### Phase 1 (IMPLEMENTED)
- **Even split** + configurable corporation share percentage
- Corporation receives percentage first (e.g., 10%)
- Remaining ISK split evenly among participants
- Round down on individual shares, remainder goes to corp
- Uses DecimalField (max_digits=20, decimal_places=2) for ISK amounts to handle up to 1T ISK

#### Phase 2 (PLANNED)
- **Character deduplication**: One payout per human player (main character)
  - Uses Alliance Auth character ownership to identify alts
  - If any alt participates, main character receives the payout
- **Scout bonus**: +10% additional ISK (not a multiplier)
  - If any alt is marked scout, main character gets scout bonus
  - Example: Base share 30M ISK → Scout gets 33M ISK (30M + 3M bonus)
- **Exclude from payout**: FC can exclude participants
- **Calculation example:**
  ```
  Total: 100M ISK
  Corp Share (10%): 10M ISK
  Participant Pool: 90M ISK
  Players (3): 2 scouts, 1 regular

  Base Share: 90M / 3 = 30M ISK
  Scout Bonus: 30M * 0.10 = 3M ISK

  Payouts:
  - Scout A: 30M + 3M = 33M ISK
  - Scout B: 30M + 3M = 33M ISK
  - Regular: 30M ISK
  Total Paid: 96M ISK
  Remainder to Corp: 4M ISK
  ```

## Development Commands

### Testing
```bash
# Run tests with tox (creates isolated test environment)
make tox_tests

# Run tests with coverage report
make coverage

# Run tests directly (requires Alliance Auth environment)
python runtests.py aapayout

# Run tests for specific module
coverage run runtests.py aapayout.tests.test_models -v 2
```

### Development
```bash
# Run pre-commit checks (linting, formatting)
make pre-commit-checks

# Build the package for testing
make build_test

# Create model graph visualization
make graph_models
```

### Migrations
```bash
# Create migrations (when models change)
python manage.py makemigrations aapayout

# Apply migrations
python manage.py migrate

# Show migration status
python manage.py showmigrations aapayout
```

### Django Shell
```bash
# Open Django shell for testing models/queries
python manage.py shell

# Quick test in shell:
from django.contrib.auth.models import User
from aapayout.models import General
# Test permissions, models, etc.
```

## Configuration

### Alliance Auth Settings (local.py)
Key settings to add when implementing features:
```python
# Janice API Configuration (Phase 1)
AAPAYOUT_JANICE_API_KEY = "your_api_key_here"
AAPAYOUT_JANICE_MARKET = "jita"  # jita, amarr, perimeter, etc.
AAPAYOUT_JANICE_PRICE_TYPE = "buy"  # buy or sell
AAPAYOUT_JANICE_TIMEOUT = 30

# Payout Configuration (Phase 1)
AAPAYOUT_CORP_SHARE_PERCENTAGE = 10  # Percentage to holding corp
AAPAYOUT_MINIMUM_PAYOUT = 1000000  # 1M ISK minimum
AAPAYOUT_REQUIRE_APPROVAL = True

# Holding Corporation (Phase 1)
AAPAYOUT_HOLDING_CORP_ID = 123456  # EVE corp ID
```

### Permissions
Available permissions (defined in models.py General class):
- `basic_access` - View fleets and own payouts
- `create_fleet` - Create new fleets
- `manage_own_fleets` - Manage own fleets as FC
- `manage_all_fleets` - Admin: manage all fleets
- `approve_payouts` - Approve payout distributions
- `view_all_payouts` - View all payout history
- `manage_payout_rules` - Manage payout calculation rules

## File Structure

### Application Code (Phase 1 - COMPLETE)
- `aapayout/models.py` - Complete database models (Fleet, FleetParticipant, LootPool, LootItem, Payout)
- `aapayout/constants.py` - Constants for statuses, roles, pricing methods
- `aapayout/views.py` - 18 views covering full CRUD operations
- `aapayout/urls.py` - Complete URL routing with RESTful patterns
- `aapayout/forms.py` - 9 Django forms for all operations
- `aapayout/helpers.py` - Payout calculation logic and loot item creation
- `aapayout/tasks.py` - Celery task for async Janice appraisal
- `aapayout/app_settings.py` - Complete plugin settings (Janice API, corp share, etc.)
- `aapayout/admin.py` - Complete Django admin with custom displays and inlines
- `aapayout/services/janice.py` - Complete Janice API integration with caching
- `aapayout/auth_hooks.py` - Alliance Auth integration (menu, URLs)
- `aapayout/apps.py` - App configuration

### Templates (Phase 1 - COMPLETE)
- `aapayout/templates/aapayout/base.html` - Base template with navigation
- `aapayout/templates/aapayout/dashboard.html` - Main dashboard
- Fleet templates: `fleet_list.html`, `fleet_create.html`, `fleet_detail.html`, `fleet_edit.html`
- Participant templates: `participant_add.html`, `participant_edit.html`
- Loot templates: `loot_create.html`, `loot_detail.html`, `loot_edit_item.html`, `loot_approve.html`
- Payout templates: `payout_list.html`, `payout_mark_paid.html`, `payout_history.html`

### Static Files (Phase 1 - COMPLETE)
- `aapayout/static/aapayout/css/aapayout.css` - Complete styling (400+ lines)
- `aapayout/static/aapayout/js/aapayout.js` - Complete JS functionality (350+ lines)

### Testing (Phase 1 - COMPLETE)
- `aapayout/tests/test_models.py` - 18 model tests
- `aapayout/tests/test_helpers.py` - 10 helper function tests
- `aapayout/tests/test_services.py` - 13 Janice API tests (mocked)
- `aapayout/tests/test_forms.py` - 17 form validation tests
- `testauth/` - Test Django project environment
- `runtests.py` - Test runner script
- `tox.ini` - Tox test configuration

### Documentation
- `IMPLEMENTATION_PLAN.md` - Full architecture and phased implementation plan (updated)
- `PHASE1_PLAN.md` - Detailed Phase 1 implementation (COMPLETE)
- `PHASE2_PLAN.md` - Detailed Phase 2 plan (Express Mode + ESI)
- `REQUIREMENTS.md` - Requirements and design decisions
- `JANICE_API.md` - Complete Janice API integration guide
- `README.md` - User-facing documentation
- `CLAUDE.md` - This file (updated)

## Development Status

**Current Phase**: Phase 1 COMPLETE ✅ | Phase 2 Planning APPROVED

### Phase 1 - COMPLETE (2025-10-27)
- ✅ Complete plugin structure
- ✅ All database models implemented (Fleet, FleetParticipant, LootPool, LootItem, Payout)
- ✅ Janice API integration with caching
- ✅ Complete admin interface
- ✅ Full CRUD views (18 views)
- ✅ Complete UI templates (13 templates)
- ✅ Forms for all operations (9 forms)
- ✅ Payout calculation logic (even split + corp share)
- ✅ Celery task for async appraisal
- ✅ Comprehensive test suite (58 tests)
- ✅ Complete styling and JavaScript

**Phase 1 Status:** Fully functional MVP. System can create fleets, add participants, value loot via Janice API, calculate even split payouts with corp share, and track payment status.

### Phase 2 - Ready for Implementation (6-7 weeks)

See PHASE2_PLAN.md for complete details.

**Focus:** Minimize FC labor through ESI automation and Express Mode payment interface

**Week 1-2: Character Deduplication & FC Controls**
- Add FleetParticipant fields: `is_scout`, `excluded_from_payout`, `main_character`
- Implement character ownership lookup via Alliance Auth
- Add UI for scout marking and participant exclusion
- Update payout calculation for deduplication

**Week 3-4: ESI Fleet Import**
- ESI fleet composition import (`GET /fleets/{fleet_id}/members/`)
- Character relationship detection
- Import results display
- Celery task for large fleets

**Week 5: Scout Bonus & Controls UI**
- Scout bonus calculation (+10% ISK)
- FC controls UI polish
- Real-time payout preview updates

**Week 6: Express Mode Payment Interface**
- ESI window opening (`POST /ui/openwindow/information/`)
- Keyboard-driven payment workflow
- Progress tracking
- ~80% time savings vs manual (40min → 7-8min for 20 payouts)

**Week 7: Payment Verification**
- ESI wallet journal integration
- Payment matching algorithm
- Automatic verification
- Manual override capability

**Week 8: Payout History View**
- Search and filter interface
- Date range filtering
- Pagination
- Query optimization

**Why No Full Payment Automation:**
ESI research confirmed no ISK transfer or contract creation endpoints exist. Express Mode optimizes the manual process using available ESI capabilities.

## Important Design Decisions

### Decimal Precision for ISK
- Always use `DecimalField(max_digits=20, decimal_places=2)` for ISK amounts
- Never use FloatField to avoid precision issues
- Loot values can reach 1 trillion ISK

### Janice API Integration
- Janice handles raw paste format directly from EVE client
- Cache appraisal results (1 hour) to reduce API calls
- Store `raw_loot_text` in LootPool model for re-appraisal
- Handle API failures gracefully with manual override option

### Character References & Deduplication (Phase 2)
- **Phase 1:** Participants added individually (can accidentally add same player's alts)
- **Phase 2:** Character deduplication using Alliance Auth character ownership
  - One payout per human player, sent to main character
  - System automatically groups alts using `CharacterOwnership` model
  - If any alt is marked scout, main character gets scout bonus
  - If any alt is excluded, entire player is excluded
  - Fallback: If no main character found, use character itself
- Reference characters via django-eveuniverse EveEntity model
- Link to Alliance Auth user accounts

### Payout Rounding
- Individual shares round down to nearest 0.01 ISK
- Remainder from rounding goes to corporation
- Prevents total payout from exceeding loot value

### Express Mode Design (Phase 2)
- **Goal:** Reduce payment time from ~40min to ~7-8min for 20 payouts (~80% savings)
- **Approach:** Optimize manual process using available ESI capabilities
- **Key Features:**
  - ESI opens character window in EVE client (`POST /ui/openwindow/information/`)
  - One-click amount copying to clipboard
  - Keyboard shortcuts (Space to advance, O to open, C to copy)
  - Progress tracking with time estimates
  - FC does ISK transfer in EVE client (cannot be automated via ESI)
- **Why Not Full Automation:** ESI has no ISK transfer or contract creation endpoints
- **UI Design:** Single-page workflow with minimal context switching

## Testing Guidelines

### When Writing Tests
- Mock Janice API responses (don't call real API in tests)
- Test ISK calculations with large values (up to 1T)
- Test decimal precision and rounding edge cases
- Test permission enforcement on all views
- Use `@patch('aapayout.services.janice.requests.post')` for API mocks

### Test Database
- Tests use separate test database
- `--keepdb` flag reuses test database for faster runs
- `--failfast` stops on first failure

## Alliance Auth Integration

### Menu Item
- Menu entry: "Fleet Payouts" with coins icon
- Only visible to users with `aapayout.basic_access` permission
- Defined in `auth_hooks.py` via MenuItemHook

### URL Registration
- Plugin URLs registered under `/payout/` prefix
- Uses UrlHook in `auth_hooks.py`
- All URLs defined in `aapayout/urls.py` with app_name="aapayout"

## Common Patterns

### View Permissions
```python
@login_required
@permission_required("aapayout.specific_permission")
def view_name(request):
    # View logic
```

### Model Permissions Check
```python
# Check if user can edit fleet
if fleet.fleet_commander == request.user or request.user.has_perm("aapayout.manage_all_fleets"):
    # Allow edit
```

### ISK Formatting in Templates
```python
# In views, pass formatted ISK
context["total_isk"] = f"{amount:,.2f}"

# Or use template filter (to be created)
{{ amount|isk_format }}
```

### Celery Task Pattern
```python
@shared_task
def task_name(model_id):
    try:
        obj = Model.objects.get(id=model_id)
        # Task logic
        obj.status = 'completed'
        obj.save()
    except Exception as e:
        logger.error(f"Task failed: {str(e)}")
        raise
```

## Resources

- Alliance Auth Docs: https://gitlab.com/allianceauth/allianceauth
- Alliance Auth Plugin Template: https://github.com/ppfeufer/aa-example-plugin
- Janice API: https://janice.e-351.com/api/rest/docs/index.html
- Django 4.2 Docs: https://docs.djangoproject.com/en/4.2/
