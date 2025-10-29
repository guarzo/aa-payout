"""Initialize the app"""

__version__ = "0.2.15"
__title__ = "AA Payout"

# Ensure Celery discovers tasks
default_app_config = "aapayout.apps.AapayoutConfig"
