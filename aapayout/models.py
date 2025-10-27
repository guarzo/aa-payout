"""
App Models
Create your models in here
"""

# Django
from django.db import models


class General(models.Model):
    """Meta model for app permissions"""

    class Meta:
        """Meta definitions"""

        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access payout system"),
            ("create_fleet", "Can create fleets"),
            ("manage_own_fleets", "Can manage own fleets as FC"),
            ("manage_all_fleets", "Can manage all fleets"),
            ("approve_payouts", "Can approve payouts"),
            ("view_all_payouts", "Can view all payout history"),
            ("manage_payout_rules", "Can manage payout rules"),
        )
