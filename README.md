# AA Payout - Fleet Loot Management System

An Alliance Auth plugin that allows fleet commanders to value loot from PvP engagements and automatically distribute ISK payouts to participating pilots.

![License](https://img.shields.io/badge/license-GPLv3-green)
![Python](https://img.shields.io/badge/python-3.10+-informational)
![Django](https://img.shields.io/badge/django-4.2+-informational)
![Alliance Auth](https://img.shields.io/badge/allianceauth-4.3.1+-blue)

## Features

- **Fleet Management**: Create and track fleet operations with participant rosters
- **Loot Valuation**: Automatically value loot using EVE market data (ESI/Fuzzwork)
- **Flexible Payout Rules**: Configure payout distribution based on roles, time, and custom rules
- **Payment Tracking**: Track payment status and maintain audit trails
- **Comprehensive Reporting**: View payout history, fleet profitability, and export data

## Installation

### Step 1: Install the Package

Install the package into your Alliance Auth virtual environment:

```bash
pip install aa-payout
```

Or install directly from the repository:

```bash
pip install git+https://github.com/yourusername/aa-payout.git
```

### Step 2: Configure Alliance Auth

Add `aapayout` to your `INSTALLED_APPS` in your Alliance Auth settings file (usually `myauth/settings/local.py`):

```python
INSTALLED_APPS += [
    'aapayout',
]
```

### Step 3: Run Migrations

Run Django migrations to create the database tables:

```bash
python manage.py migrate
```

### Step 4: Collect Static Files

Collect static files:

```bash
python manage.py collectstatic
```

### Step 5: Restart Services

Restart your Alliance Auth services:

```bash
supervisorctl restart myauth:
```

## Permissions

The following permissions are available:

| Permission | Description |
|------------|-------------|
| `aapayout.basic_access` | Can access the payout system |
| `aapayout.create_fleet` | Can create fleets |
| `aapayout.manage_own_fleets` | Can manage own fleets as FC |
| `aapayout.manage_all_fleets` | Can manage all fleets |
| `aapayout.approve_payouts` | Can approve payouts |
| `aapayout.view_all_payouts` | Can view all payout history |
| `aapayout.manage_payout_rules` | Can manage payout rules |

## Basic Usage

### Creating a Fleet

1. Navigate to **Fleet Payouts** in the Alliance Auth sidebar
2. Click **Create Fleet**
3. Fill in fleet details (name, doctrine, location, etc.)
4. Add participants manually or import from ESI

### Adding Loot

1. Open your fleet
2. Click **Add Loot Pool**
3. Paste loot from cargo/contract or enter items manually
4. Click **Value Loot** to fetch market prices

### Calculating Payouts

1. Review the valued loot
2. Select a payout rule (equal split, role-based, etc.)
3. Preview the payout distribution
4. Approve and finalize payouts

### Processing Payments

1. View pending payouts
2. Make payments via in-game contracts/trades
3. Mark payments as complete in the system
4. Pilots can view their payment status

## Configuration

You can customize the plugin behavior in your `local.py`:

```python
# Default pricing source (jita_buy, jita_sell, regional)
AAPAYOUT_DEFAULT_PRICING_SOURCE = "jita_sell"

# Minimum payout amount in ISK
AAPAYOUT_MINIMUM_PAYOUT = 1000000  # 1M ISK

# Automatically value loot on submission
AAPAYOUT_AUTO_VALUE_ON_SUBMIT = True

# Require approval before payouts can be processed
AAPAYOUT_REQUIRE_APPROVAL = True

# Discord webhook for notifications (optional)
AAPAYOUT_NOTIFICATION_WEBHOOK = ""

# Market region ID for pricing (10000002 = The Forge/Jita)
AAPAYOUT_MARKET_REGION_ID = 10000002
```

## Development Status

This plugin is currently in active development. See the [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for detailed development roadmap.

Current status: **Phase 1 - Core Framework**

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

For bugs, feature requests, or questions, please [open an issue](https://github.com/yourusername/aa-payout/issues) on GitHub.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for [Alliance Auth](https://gitlab.com/allianceauth/allianceauth)
- Based on the [AA Example Plugin](https://github.com/ppfeufer/aa-example-plugin)
- EVE Online and all associated content is property of CCP Games
