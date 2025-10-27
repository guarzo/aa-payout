# AA-Payout: Requirements & Design Decisions

This document captures the specific requirements and design decisions for the AA-Payout plugin.

---

## Key Requirements

### Fleet Characteristics
- **Fleet size**: Typically 10 or fewer pilots
- **Loot value**: Generally 1B-100B ISK, can reach up to 1T ISK
- **Frequency**: Regular PvP fleet operations

### User Workflow
1. FC creates fleet in system
2. FC pastes raw loot from game into system
3. System automatically values loot via Janice API
4. System calculates even split among participants + corporation share
5. FC reviews and approves payouts
6. Payouts are tracked/executed

---

## Design Decisions

### 1. Item Valuation
**Decision**: Use Janice API for all item pricing

- **Service**: [Janice](https://janice.e-351.com/) - EVE Online appraisal service
- **API**: Accepts raw paste format directly from EVE client
- **Pricing**: Use Jita buy prices
- **Why**:
  - Handles bulk paste format natively
  - Provides accurate market pricing
  - Includes fees and other considerations
  - Well-established in EVE community

**Implementation Notes**:
- Janice API endpoint: `https://janice.e-351.com/api/rest/v2/appraisal`
- Accepts raw item paste in request body
- Returns detailed pricing breakdown
- May require API key (check documentation)

### 2. EVE Data Integration
**Decision**: Use django-eveuniverse for EVE type data

- **Package**: `django-eveuniverse`
- **Purpose**:
  - Item/type database (ships, modules, etc.)
  - Character references
  - Corporation/alliance data
- **Why**: Standard for AA plugins, robust, well-maintained

### 3. Character Management
**Decision**: Main character only, use linked characters

- **Approach**: Use Alliance Auth's character linking system
- **Main character**: Primary character associated with user account
- **Purpose**: Prevent double-counting if user flies multiple alts
- **Display**: Show main character name in payout lists
- **ESI**: Pull from ESI fleet API when available

### 4. Payout Model
**Decision**: Even split + corporation share (MVP)

**MVP (Phase 1)**:
- Equal distribution among all participants
- Corporation receives a configurable percentage (e.g., 10%)
- Example: 10B loot, 10% corp cut = 1B to corp, 9B split among pilots

**Future Enhancements (Phase 2+)**:
- Role-based multipliers (Scout vs Regular)
- Scouts receive higher percentage (configurable)
- Time-based calculations (pro-rated for early leavers)
- FC bonus percentage
- Logi bonus percentage

**Configuration**:
```python
AAPAYOUT_CORP_SHARE_PERCENTAGE = 10  # Percentage to corporation
AAPAYOUT_ROLE_MULTIPLIERS = {
    'scout': 1.5,      # Future feature
    'regular': 1.0,
}
```

### 5. Fleet Participant Management
**Decision**: Manual entry for MVP, ESI import post-MVP

**MVP (Phase 1)**:
- Manual character entry via search/autocomplete
- Add/remove participants manually
- Simple role assignment (Scout/Regular)

**Future (Phase 2)**:
- ESI fleet composition import
- Automatic role detection from fleet position
- Real-time fleet sync
- Join/leave time tracking

**ESI Scopes Required (Future)**:
- `esi-fleets.read_fleet.v1` - Read fleet composition
- `esi-ui.open_window.v1` - Open contract windows (for payments)
- `esi-wallet.read_character_wallet.v1` - Verify payments

### 6. Payment Tracking
**Decision**: Manual tracking for MVP, ESI verification post-MVP

**MVP (Phase 1)**:
- Manual "Mark as Paid" button
- Free-text notes field for transaction reference
- Payment status: Pending, Paid, Failed
- Payment timestamp and user tracking

**Future (Phase 2)**:
- ESI contract verification
- Automatic ISK transfer via ESI
- Transaction ID linking
- Payment reminders/notifications

### 7. Loot Entry
**Decision**: Bulk paste using Janice-compatible format

**Format**: Raw copy from EVE client
```
Compressed Arkonor	1000
Compressed Bistot	500
Salvage	250
```

**Processing**:
1. User pastes raw text from cargo/contract
2. System sends to Janice API for appraisal
3. Janice returns item names, quantities, and values
4. System creates LootItem records
5. User can review and manually override if needed

### 8. Permissions & Access Control
**Decision**: Minimal access control for MVP

**Basic Access** (`aapayout.basic_access`):
- View fleets
- View own payouts
- Create new fleets

**Fleet Management**:
- **Creator**: Full edit/delete rights on their fleets
- **Admin**: Full edit/delete rights on all fleets (via `manage_all_fleets` permission)

**Future Enhancements**:
- Corp/Alliance restrictions
- Director approval workflows
- Payout approval role

---

## MVP Feature Scope

### Phase 1 - MVP (Initial Release)

**Included**:
- ✅ Create fleet with basic info (name, date, location)
- ✅ Manually add participants by character name
- ✅ Bulk paste loot entry
- ✅ Automatic valuation via Janice API (Jita buy prices)
- ✅ Even split calculation with corp share
- ✅ Manual payout tracking (mark as paid)
- ✅ View own payouts
- ✅ Basic fleet history

**Excluded (Future Phases)**:
- ❌ ESI fleet import
- ❌ Role-based payout multipliers
- ❌ Automatic ESI payments
- ❌ Time-based calculations
- ❌ Advanced reporting/analytics
- ❌ Discord notifications
- ❌ CSV export

### Phase 2 - ESI Integration

- ESI fleet composition import
- ESI payment verification
- Real-time fleet updates

### Phase 3 - Advanced Features

- Role-based payout multipliers
- Time-based pro-rating
- Advanced reporting
- Discord webhooks
- Export functionality

---

## Technical Decisions

### Database
- **DecimalField** for ISK amounts (precision for up to 1T ISK)
  - `max_digits=20, decimal_places=2`
- **JSONField** for flexible configurations (payout rules, role multipliers)

### External Dependencies
```python
dependencies = [
    "allianceauth>=4.3.1,<5",
    "django-eveuniverse>=2.0.0",
    "requests>=2.28.0",
]
```

### API Rate Limits
- **Janice API**: Check documentation for rate limits
- **ESI** (Future): Respect ESI rate limits (150 req/s, with error limit)

---

## Open Questions

### Resolved ✅
1. ✅ Item valuation service → Janice API
2. ✅ Payout model → Even split + corp share
3. ✅ Character handling → Main character only
4. ✅ Fleet size → 10 or fewer typically
5. ✅ Value range → 1B-100B (up to 1T)
6. ✅ Permissions → Minimal for MVP
7. ✅ EVE data integration → django-eveuniverse

### All Resolved ✅
8. ✅ Corporation identification → Pre-configured main holding corp in settings
9. ✅ Janice API authentication → Requires API key, low rate limits for our volume
10. ✅ Janice API caching → Save appraisals for future viewing
11. ✅ Character autocomplete → Any character in AA database
12. ✅ Decimal precision → Full ISK amounts, round down on splits, corp keeps remainder
13. ✅ Loot pool naming → Single pool per fleet (auto-named or simple)

---

## Next Steps

1. ✅ Research Janice API documentation → Complete (see JANICE_API.md)
2. Set up django-eveuniverse integration
3. Design database models with proper ISK precision
4. Create loot paste parser (Janice handles this)
5. Implement basic fleet CRUD operations
6. Build payout calculator with corp share logic

## Summary of Final Decisions

### MVP Scope
- **Valuation**: Janice API with Jita buy prices
- **Payout**: Even split among participants + configurable corp share
- **Corp Share**: Pre-configured holding corp in settings, round down remainder goes to corp
- **Participants**: Manual entry from AA character database
- **Fleet Size**: Optimized for 10 or fewer pilots
- **Loot Value**: Support up to 1T ISK with proper decimal precision
- **Payment**: Manual "mark as paid" tracking
- **Permissions**: Creator or admin can edit/delete

### Post-MVP (Phase 2+)
- ESI fleet composition import
- Role-based payout multipliers (Scout vs Regular)
- ESI payment verification/execution
- Advanced reporting and exports
