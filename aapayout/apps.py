"""App Configuration"""

# Django
from django.apps import AppConfig

# AA Payout
from aapayout import __version__


class AaPayoutConfig(AppConfig):
    """App Config"""

    name = "aapayout"
    label = "aapayout"
    verbose_name = f"AA Payout v{__version__}"
