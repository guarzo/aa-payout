# AA Payout - Loot Management System

An Alliance Auth plugin that allows organizers to value loot from PvP engagements and automatically distribute ISK payouts to participating pilots.

![License](https://img.shields.io/badge/license-GPLv3-green)
![Python](https://img.shields.io/badge/python-3.10+-informational)
![Django](https://img.shields.io/badge/django-4.2+-informational)
![Alliance Auth](https://img.shields.io/badge/allianceauth-4.3.1+-blue)

## Features

### Core Features
- **Payout Management**: Create and track payout operations with participant rosters
- **Loot Valuation**: Automatically value loot using Janice API (Jita buy/sell prices)
- **Payout Calculation**: Even split distribution with configurable corporation share
- **Payment Tracking**: Track payment status and maintain audit trails
- **Admin Interface**: Complete Django admin with inline management for all models

### Advanced Features
- **Manual & ESI Import**: Add participants manually or import entire fleet from EVE client via ESI
- **Character Deduplication**: Automatic grouping of alts - one payout per human player
- **Scout Bonus System**: Mark scouts for +10% ISK bonus (configurable percentage)
- **Participant Controls**: Exclude specific participants from payouts
- **Express Mode Payment**: Keyboard-driven payment workflow with ESI window opening (~80% time savings)
- **Payment Verification**: Automatic verification via ESI wallet journal
- **Payout History**: Advanced filtering, search, and pagination for historical payouts

## Requirements

Before installing this plugin, you need:

1. **Alliance Auth 4.3.1+**: This plugin requires Alliance Auth to be installed
2. **Janice API Key** (Required): This plugin uses the Janice API to value loot items
   - Create a free account at [https://janice.e-351.com](https://janice.e-351.com)
   - Generate an API key from your account settings
   - See [Janice API Documentation](https://janice.e-351.com/api/rest/docs/index.html) for more information
3. **ESI Token** (Optional but recommended): For advanced features, organizers need ESI tokens with these scopes:
   - `esi-fleets.read_fleet.v1` - Import fleet composition
   - `esi-ui.open_window.v1` - Express Mode payment interface
   - `esi-wallet.read_character_wallet.v1` - Payment verification

## Installation

### Step 1: Install the Package

Install the package into your Alliance Auth virtual environment:

```bash
pip install aa-payout
```

Or install directly from the repository:

```bash
pip install git+https://github.com/guarzo/aa-payout.git
```

### Step 2: Configure Alliance Auth

Add `aapayout` to your `INSTALLED_APPS` and add the context processor in your Alliance Auth settings file (usually `myauth/settings/local.py`):

```python
INSTALLED_APPS += [
    'aapayout',
]

# Add context processor for organizer character selection
TEMPLATES[0]['OPTIONS']['context_processors'].append(
    'aapayout.context_processors.fc_character'
)
```

### Step 3: Configure Settings

Add your Janice API key to your `local.py` settings file:

```python
# Janice API Configuration (REQUIRED)
AAPAYOUT_JANICE_API_KEY = "your-api-key-here"  # Get this from https://janice.e-351.com
AAPAYOUT_JANICE_MARKET = 2              # Market ID: 2=Jita, 1=Amarr, 3=Dodixie, 4=Rens, 5=Hek
AAPAYOUT_JANICE_PRICE_TYPE = "buy"      # Price type: buy or sell

# Payout Configuration
AAPAYOUT_CORP_SHARE_PERCENTAGE = 10     # Percentage of loot value to corporation
AAPAYOUT_MINIMUM_PAYOUT = 1000000       # Minimum payout amount in ISK (1M ISK)
AAPAYOUT_SCOUT_BONUS_PERCENTAGE = 10    # Scout bonus percentage (default: +10%)

# Optional: Holding Corporation
AAPAYOUT_HOLDING_CORP_ID = 123456       # EVE corporation ID for corp share recipient
```

### Step 4: Run Migrations

Run Django migrations to create the database tables:

```bash
python manage.py migrate
```

### Step 5: Collect Static Files

Collect static files:

```bash
python manage.py collectstatic
```

### Step 6: Restart Services

Restart your Alliance Auth services:

```bash
supervisorctl restart myauth:
```

## Permissions

The following permissions are available:

| Permission | Description |
|------------|-------------|
| `aapayout.basic_access` | Can access the payout system |
| `aapayout.create_fleet` | Can create payouts |
| `aapayout.manage_own_fleets` | Can manage own payouts as organizer |
| `aapayout.manage_all_fleets` | Can manage all payouts |
| `aapayout.approve_payouts` | Can approve payouts |
| `aapayout.view_all_payouts` | Can view all payout history |
| `aapayout.manage_payout_rules` | Can manage payout rules |

## Basic Usage

### Selecting Organizer Character

Before creating payouts or importing from ESI, select which character to use as the organizer:

1. Look for the **organizer character dropdown** in the top navigation bar
2. Click the dropdown (shows "FC: [Character Name]")
3. Select the character you want to use for payout operations
4. The selected character will be used for:
   - ESI fleet detection and import
   - Payment operations
   - Payout organizer assignment

**Note**: The system defaults to your main character. You can change this at any time.

### Creating a Payout

1. Navigate to **Fleet Payouts** in the Alliance Auth sidebar
2. Click **Create Payout**
3. Fill in payout details:
   - Payout name (e.g., "Roaming Fleet - 2025-10-28")
   - Battle report URL (optional, e.g., link to zkillboard or evetools battle report)
   - Notes (optional)
4. Payout time is automatically set to the current time
5. Click **Create**

### Adding Participants

**Option 1: Manual Entry**
1. Open your payout
2. Click **Add Participant**
3. Enter character name
4. Optionally mark as scout or exclude from payout
5. Click **Add**

**Option 2: ESI Fleet Import** (Recommended)
1. Make sure you're in a fleet in EVE Online
2. Select the correct organizer character from the dropdown (top navigation)
3. Open your payout in the system
4. Click **Import from ESI**
5. Click **Import Current Fleet**
6. System will automatically:
   - Detect which fleet you're in
   - Add all fleet members
   - Deduplicate alts (one payout per player)

### Adding Loot

1. Open your payout
2. Click **Add Loot Pool**
3. Give the loot pool a name (e.g., "Main Haul")
4. Paste raw loot text from EVE client:
   - Select items in cargo/contract
   - Copy (Ctrl+C in EVE)
   - Paste into the "Raw Loot Text" field
5. Click **Create**
6. System will automatically value loot via Janice API
7. Corporation share is automatically set to 10% if per-character payout > 200k ISK, otherwise 0%

### Reviewing and Approving Payouts

1. View the loot pool details to see valued items
2. Click **Edit Item** to manually adjust any prices if needed
3. Click **Approve Payouts**
4. Review the payout preview:
   - Base share per participant
   - Scout bonuses (if any scouts marked)
   - Corporation share (auto-calculated: 10% if per-character > 200k ISK, else 0%)
   - Total distribution
5. Click **Approve**

### Processing Payments

**Option 1: Regular Mode**
1. Go to **Payout List** for the loot pool
2. For each payout:
   - Open EVE client
   - Send ISK to recipient character
   - Click **Mark as Paid**
   - Enter transaction reference (optional)
   - Confirm

**Option 2: Express Mode** (Recommended)
1. Go to **Payout List** for the loot pool
2. Click **Express Mode**
3. For each payout:
   - Press `O` to open character window in EVE (via ESI)
   - Transfer ISK manually in EVE client
   - Press `Space` to mark as paid and move to next
4. System tracks progress and estimates time remaining

**Option 3: Payment Verification**
1. Make all payments manually in EVE client
2. Go to **Payout List**
3. Click **Verify Payments**
4. System checks your wallet journal via ESI
5. Automatically marks matching payments as verified

### Viewing Payout History

1. Click **Payout History** in the main menu
2. Use filters to find specific payouts:
   - Filter by payout session
   - Filter by status (pending/paid)
   - Filter by date range
   - Search by character or payout name
3. View summary statistics (total paid, pending, etc.)

## How It Works

### Payout Calculation

1. **Corporation Share**: Automatically set to 10% if per-character payout > 200k ISK, otherwise 0%
2. **Character Deduplication**: Group alts by main character (one payout per human)
3. **Base Share**: Remaining ISK split evenly among unique players
4. **Scout Bonus**: Scouts get +10% additional ISK (not a multiplier)
5. **Rounding**: Individual shares round down to nearest 0.01 ISK
6. **Remainder**: Rounding remainder goes to corporation

**Example** (100M ISK loot, 3 players, 2 scouts):
- Corp share: 10M ISK
- Participant pool: 90M ISK
- Base share: 90M / 3 = 30M ISK
- Scout bonus: 30M * 0.10 = 3M ISK
- Scout A: 30M + 3M = 33M ISK
- Scout B: 30M + 3M = 33M ISK
- Regular: 30M ISK
- Total paid: 96M ISK
- Corp final: 10M + 4M remainder = 14M ISK

## Configuration

Additional configuration options in your `local.py`:

```python
# Advanced Configuration
AAPAYOUT_JANICE_TIMEOUT = 30             # API request timeout in seconds
AAPAYOUT_JANICE_CACHE_HOURS = 1         # Cache appraisals for this many hours
AAPAYOUT_REQUIRE_APPROVAL = True        # Require organizer approval before payouts

# ESI Integration
AAPAYOUT_ESI_FLEET_IMPORT_ENABLED = True  # Enable ESI fleet import
AAPAYOUT_EXPRESS_MODE_ENABLED = True      # Enable Express Mode payment interface

# Payment Verification
AAPAYOUT_VERIFICATION_TIME_WINDOW_HOURS = 24  # Wallet journal search window
AAPAYOUT_AUTO_VERIFY_AFTER_PAYMENT = True     # Auto-verify after Express Mode
```

## Troubleshooting

### Janice API Issues

**Problem**: "Failed to value loot" error
- **Solution**: Check your Janice API key is valid and has not expired
- **Solution**: Verify your Janice account has sufficient API credits
- **Solution**: Check network connectivity to janice.e-351.com

### ESI Import Issues

**Problem**: "You are not currently in a fleet" error
- **Solution**: Make sure you're actually in a fleet in EVE Online
- **Solution**: Verify the correct organizer character is selected in the dropdown (top navigation)
- **Solution**: Ensure you have added an ESI token with `esi-fleets.read_fleet.v1` scope for that character
- **Solution**: Try refreshing your ESI token by re-adding your character

**Problem**: "ESI fleet import failed" error
- **Solution**: Ensure you are the fleet commander or have fleet boss role in EVE Online
- **Solution**: Check your ESI token is valid and not expired
- **Solution**: Verify network connectivity to ESI

### Express Mode Issues

**Problem**: Character window not opening in EVE
- **Solution**: Ensure EVE client is running and logged in
- **Solution**: Verify you have ESI token with `esi-ui.open_window.v1` scope
- **Solution**: Check you are logged into the correct character

### Payment Verification Issues

**Problem**: Payments not being verified
- **Solution**: Ensure you have ESI token with `esi-wallet.read_character_wallet.v1` scope
- **Solution**: Verify you made the payment from the correct character
- **Solution**: Check the payment was made within the time window (default 24 hours)
- **Solution**: Ensure payment amount matches exactly (within 0.01 ISK)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone the repository
git clone https://github.com/guarzo/aa-payout.git
cd aa-payout

# Install in development mode
pip install -e .

# Run tests
python runtests.py

# Run pre-commit checks
pre-commit run --all-files
```

## Support

For bugs, feature requests, or questions, please [open an issue](https://github.com/guarzo/aa-payout/issues) on GitHub.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for [Alliance Auth](https://gitlab.com/allianceauth/allianceauth)
- Loot valuation powered by [Janice API](https://janice.e-351.com)
- Based on the [AA Example Plugin](https://github.com/ppfeufer/aa-example-plugin)
- EVE Online and all associated content is property of CCP Games
