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

    def ready(self):
        """
        Import tasks when the app is ready to ensure Celery discovers them
        """
        # Import tasks to register them with Celery
        # AA Payout
        import aapayout.tasks  # noqa: F401
