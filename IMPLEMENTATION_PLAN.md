# AA-Payout: Fleet Loot Valuation and Payout Plugin

## Overview
A plugin that allows fleet commanders to record loot from PvP engagements, automatically value it using market data, and distribute ISK payouts to participating pilots.

---

## Core Features

### 1. Fleet Management
- Create and track fleet operations
- Record participants with join/leave times
- Support different participation types (logi, DPS, scout, etc.)
- Link to EVE ESI for automatic participant verification

### 2. Loot Valuation
- Manual loot entry or paste from game
- Automatic item pricing via EVE market APIs (ESI or third-party like Fuzzwork/Janice)
- Support multiple pricing strategies (Jita buy/sell, regional averages)
- Override prices manually if needed
- Track items that couldn't be valued

### 3. Payout Calculation
- Configurable payout rules (equal split, role-based, time-based)
- Support for different payout percentages (e.g., 80% to pilots, 20% to FC)
- Minimum payout thresholds
- Taxation/SRP integration options

### 4. Payout Distribution
- Manual payout tracking (FC pays via contracts/trades)
- Optional: ESI integration for automatic payment verification
- Payment status tracking (pending, paid, failed)
- Batch payout support

### 5. Reporting & Audit
- Payout history per pilot
- Fleet profitability reports
- Audit trail for all transactions
- Export to CSV/Excel

---

## Database Models

### Core Models

#### Fleet
```python
Fleet
├── id (Primary Key)
├── name (CharField)
├── fleet_commander (FK to User/Character)
├── doctrine (CharField, optional)
├── location (CharField)
├── fleet_time (DateTimeField)
├── status (CharField: planning, active, completed, paid)
├── notes (TextField)
├── created_at/updated_at
```

#### FleetParticipant
```python
FleetParticipant
├── id (Primary Key)
├── fleet (FK to Fleet)
├── character (FK to EVE Character)
├── ship_type (FK to EVE Type, optional)
├── role (CharField: dps, logi, scout, etc.)
├── joined_at (DateTimeField)
├── left_at (DateTimeField, nullable)
├── attendance_weight (DecimalField, default=1.0)
├── notes (TextField)
```

#### LootPool
```python
LootPool
├── id (Primary Key)
├── fleet (FK to Fleet)
├── name (CharField, e.g., "Main Wreck", "Secondary Loot")
├── status (CharField: draft, valued, approved, paid)
├── pricing_method (CharField: jita_buy, jita_sell, etc.)
├── total_raw_value (DecimalField)
├── total_payout_value (DecimalField)
├── payout_percentage (DecimalField, default=100)
├── created_at/updated_at
├── valued_at (DateTimeField, nullable)
├── approved_by (FK to User, nullable)
├── approved_at (DateTimeField, nullable)
```

#### LootItem
```python
LootItem
├── id (Primary Key)
├── loot_pool (FK to LootPool)
├── item_type (FK to EVE Type)
├── quantity (IntegerField)
├── estimated_unit_price (DecimalField)
├── total_value (DecimalField)
├── price_source (CharField)
├── price_fetched_at (DateTimeField)
├── manual_override (BooleanField)
├── notes (TextField)
```

#### Payout
```python
Payout
├── id (Primary Key)
├── loot_pool (FK to LootPool)
├── recipient (FK to Character)
├── amount (DecimalField)
├── share_percentage (DecimalField)
├── status (CharField: pending, processing, paid, failed)
├── payment_method (CharField: manual, contract, direct_trade, esi)
├── transaction_reference (CharField, nullable)
├── paid_by (FK to User, nullable)
├── paid_at (DateTimeField, nullable)
├── notes (TextField)
├── created_at
```

#### PayoutRule
```python
PayoutRule
├── id (Primary Key)
├── name (CharField)
├── description (TextField)
├── is_default (BooleanField)
├── base_share (DecimalField, default=1.0)
├── role_multipliers (JSONField: {role: multiplier})
├── time_based_calculation (BooleanField)
├── minimum_time_minutes (IntegerField)
├── fc_cut_percentage (DecimalField, default=0)
├── logi_bonus_percentage (DecimalField, default=0)
```

---

## Views/URLs Structure

```
/payout/
├── dashboard/                    # Main dashboard
├── fleets/
│   ├── create/                  # Create new fleet
│   ├── <fleet_id>/              # Fleet detail
│   ├── <fleet_id>/edit/         # Edit fleet
│   ├── <fleet_id>/participants/ # Manage participants
│   └── <fleet_id>/close/        # Mark fleet as complete
├── loot/
│   ├── <fleet_id>/create/       # Create loot pool
│   ├── <pool_id>/               # Loot pool detail
│   ├── <pool_id>/edit/          # Edit loot items
│   ├── <pool_id>/value/         # Trigger valuation
│   ├── <pool_id>/approve/       # Approve for payout
│   └── <pool_id>/calculate/     # Calculate payouts
├── payouts/
│   ├── <pool_id>/               # View payouts for pool
│   ├── <payout_id>/mark-paid/   # Mark individual payout as paid
│   ├── <pool_id>/bulk-paid/     # Mark multiple payouts as paid
│   └── history/                 # Payout history
├── reports/
│   ├── pilot/<char_id>/         # Pilot payout history
│   ├── fc/<char_id>/            # FC fleet history
│   └── export/                  # Export data
└── settings/                     # Configure payout rules
```

---

## Key Workflows

### Workflow 1: Create Fleet and Record Loot
1. FC creates fleet in system
2. FC adds participants (manual or ESI import from fleet history)
3. FC creates loot pool for the fleet
4. FC enters loot items (manual entry or paste from cargo scan)
5. System fetches market prices automatically
6. FC reviews and approves valuations
7. System calculates payouts based on selected rule
8. FC reviews and processes payouts
9. FC marks payouts as paid as they complete transactions

### Workflow 2: Pilot Views Payout
1. Pilot logs into Alliance Auth
2. Navigates to Payout plugin
3. Views pending and historical payouts
4. Sees fleet details, participation time, and amount owed
5. Can track payment status

---

## Technical Components

### Celery Tasks
```python
@shared_task
def fetch_item_prices(loot_pool_id):
    """Fetch prices from ESI or Fuzzwork"""

@shared_task
def calculate_payouts(loot_pool_id, payout_rule_id):
    """Calculate all payouts based on rule"""

@shared_task
def fetch_fleet_participants_from_esi(fleet_id):
    """Pull participants from ESI if FC has token"""

@shared_task
def send_payout_notifications(payout_ids):
    """Send Discord/in-game notifications"""
```

### External API Integrations
1. **EVE ESI**
   - Character verification
   - Item type information
   - Market prices (regional)
   - Optional: Fleet composition data
   - Optional: Contract/transaction verification

2. **Third-party Pricing** (fallback/alternative)
   - Fuzzwork Market Data
   - EVE Marketer
   - Janice (for complex valuations)

### Admin Interface
```python
# admin.py
- FleetAdmin (view all fleets, override statuses)
- LootPoolAdmin (audit valuations)
- PayoutAdmin (view/audit all payouts)
- PayoutRuleAdmin (manage global payout rules)
```

---

## Permissions Structure

```python
# models.py - General permissions
permissions = (
    ("basic_access", "Can access payout system"),
    ("create_fleet", "Can create fleets"),
    ("manage_own_fleets", "Can manage own fleets as FC"),
    ("manage_all_fleets", "Can manage all fleets"),
    ("approve_payouts", "Can approve payouts"),
    ("view_all_payouts", "Can view all payout history"),
    ("manage_payout_rules", "Can manage payout rules"),
)
```

---

## UI/UX Components

### Dashboard View
- Quick stats (pending payouts, recent fleets, total ISK distributed)
- Recent fleets table
- Pending actions for FCs

### Fleet Detail View
- Fleet info header
- Participants table (with edit capabilities for FC)
- Loot pools section
- Payout status

### Loot Entry Interface
- Bulk paste area (parse from cargo/contract)
- Individual item entry form
- Live preview of parsed items
- Automatic type-ahead for item names

### Payout Calculator View
- Select payout rule
- Preview payout distribution
- Adjust individual shares if needed
- Approve and finalize

---

## Configuration Settings

```python
# app_settings.py
AAPAYOUT_DEFAULT_PRICING_SOURCE = "jita_sell"  # jita_buy, jita_sell, regional
AAPAYOUT_MINIMUM_PAYOUT = 1000000  # 1M ISK minimum
AAPAYOUT_AUTO_VALUE_ON_SUBMIT = True
AAPAYOUT_REQUIRE_APPROVAL = True
AAPAYOUT_NOTIFICATION_WEBHOOK = ""  # Discord webhook
AAPAYOUT_ESI_SCOPES = []  # Required ESI scopes
AAPAYOUT_MARKET_REGION_ID = 10000002  # The Forge (Jita)
```

---

## Implementation Phases

### Phase 1: Core Framework (Week 1-2)
- [ ] Set up plugin structure from example
- [ ] Create database models
- [ ] Basic admin interface
- [ ] Simple fleet creation view

### Phase 2: Loot Management (Week 3-4)
- [ ] Loot pool creation
- [ ] Manual item entry
- [ ] Paste parser for bulk import
- [ ] ESI integration for item types

### Phase 3: Valuation (Week 5-6)
- [ ] ESI market data integration
- [ ] Celery task for price fetching
- [ ] Fallback pricing sources
- [ ] Manual price override interface

### Phase 4: Payout Calculation (Week 7-8)
- [ ] Payout rule engine
- [ ] Calculator view
- [ ] Payout preview interface
- [ ] Payout approval workflow

### Phase 5: Tracking & Distribution (Week 9-10)
- [ ] Payout status tracking
- [ ] Payment marking interface
- [ ] Notification system
- [ ] Pilot payout history view

### Phase 6: Reporting & Polish (Week 11-12)
- [ ] Reports and exports
- [ ] Dashboard refinement
- [ ] Documentation
- [ ] Testing and bug fixes

---

## Technology Stack

- **Backend**: Django 4.2+ (Alliance Auth requirement)
- **Frontend**: Bootstrap 5, jQuery/vanilla JS
- **Database**: PostgreSQL (via Alliance Auth)
- **Task Queue**: Celery (via Alliance Auth)
- **APIs**: EVE ESI, Fuzzwork Market API
- **Dependencies**:
  - `allianceauth>=4.3.1`
  - `django-eveuniverse` (for EVE type data)
  - `requests` (for API calls)
  - Optional: `python-esi` for ESI integration

---

## File Structure

```
aa-payout/
├── aapayout/                      # Main plugin package
│   ├── __init__.py
│   ├── apps.py
│   ├── auth_hooks.py
│   ├── urls.py
│   ├── models.py                  # Database models
│   ├── views.py                   # View functions
│   ├── admin.py                   # Django admin config
│   ├── forms.py                   # Django forms
│   ├── tasks.py                   # Celery tasks
│   ├── app_settings.py            # Plugin settings
│   ├── managers.py                # Custom model managers
│   ├── helpers.py                 # Helper functions
│   ├── constants.py               # Constants and choices
│   ├── static/aapayout/
│   │   ├── css/
│   │   ├── js/
│   │   └── images/
│   ├── templates/aapayout/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── fleets/
│   │   ├── loot/
│   │   ├── payouts/
│   │   └── reports/
│   ├── migrations/
│   │   └── __init__.py
│   └── tests/
│       ├── __init__.py
│       └── test_*.py
├── testauth/                      # Test environment
│   ├── __init__.py
│   ├── settings/
│   ├── urls.py
│   ├── wsgi.py
│   └── celery.py
├── .github/
│   └── workflows/
├── .gitignore
├── .editorconfig
├── .flake8
├── .isort.cfg
├── .pre-commit-config.yaml
├── pyproject.toml
├── setup.py (if needed)
├── MANIFEST.in
├── README.md
├── CHANGELOG.md
├── LICENSE
├── Makefile
├── tox.ini
├── runtests.py
└── IMPLEMENTATION_PLAN.md         # This file
```

---

## Next Steps

1. **Finalize requirements** - Review and adjust scope based on your needs
2. **Set up repository** - Fork example plugin and rename
3. **Define payout rules** - Determine how your alliance wants to split loot
4. **Start with Phase 1** - Build core models and basic views
5. **Iterate** - Build feature by feature, testing with real data
