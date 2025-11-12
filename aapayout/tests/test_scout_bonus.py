"""
Tests for Scout Bonus Calculations

Phase 2: Week 5 - Scout Bonus Calculation
"""

# Standard Library
from decimal import Decimal

# Django
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

# Alliance Auth (External Libs)
from eveuniverse.models import EveEntity

# AA Payout
from aapayout import app_settings, constants
from aapayout.helpers import calculate_payouts, create_payouts
from aapayout.models import Fleet, FleetParticipant, LootPool, Payout


class ScoutBonusCalculationTests(TestCase):
    """Tests for scout bonus payout calculations"""

    def setUp(self):
        """Patch settings before each test"""
        # Standard Library
        from unittest.mock import patch

        # Patch app_settings to use low minimum payout for tests
        self.settings_patcher = patch.object(app_settings, "AAPAYOUT_MINIMUM_PAYOUT", 1000)
        self.per_participant_patcher = patch.object(app_settings, "AAPAYOUT_MINIMUM_PER_PARTICIPANT", 1000)
        self.settings_patcher.start()
        self.per_participant_patcher.start()

    def tearDown(self):
        """Stop patching settings"""
        self.settings_patcher.stop()
        self.per_participant_patcher.stop()

    @classmethod
    def setUpTestData(cls):
        """Set up test data"""
        cls.user = User.objects.create_user(username="testuser", password="testpass")

        cls.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=cls.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_ACTIVE,
        )

        # Create test characters
        cls.char1 = EveEntity.objects.create(
            id=3001,
            name="Regular Pilot 1",
        )
        cls.char2 = EveEntity.objects.create(
            id=3002,
            name="Scout Pilot 1",
        )
        cls.char3 = EveEntity.objects.create(
            id=3003,
            name="Regular Pilot 2",
        )
        cls.char4 = EveEntity.objects.create(
            id=3004,
            name="Scout Pilot 2",
        )

    def test_calculate_payouts_no_scouts(self):
        """Test payout calculation with no scouts (all regular participants)"""
        # Create participants (no scouts)
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char1,
            is_scout=False,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char3,
            is_scout=False,
        )

        # Create loot pool
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),  # 100M ISK
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Assertions
        self.assertEqual(len(payouts), 2)

        # Each gets base share only (no scout bonus)
        expected_base = Decimal("45000000.00")  # (100M - 10M corp) / 2

        for payout in payouts:
            self.assertEqual(payout["amount"], expected_base)
            self.assertEqual(payout["base_share"], expected_base)
            self.assertEqual(payout["scout_bonus"], Decimal("0.00"))
            self.assertFalse(payout["is_scout"])

    def test_calculate_payouts_all_scouts(self):
        """Test payout calculation with all scouts"""
        # Create participants (all scouts)
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char2,
            is_scout=True,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char4,
            is_scout=True,
        )

        # Create loot pool
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),  # 100M ISK
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Assertions
        self.assertEqual(len(payouts), 2)

        # Base share and scout bonus
        expected_base = Decimal("45000000.00")  # (100M - 10M corp) / 2
        expected_scout_bonus = Decimal("4500000.00")  # 10% of base
        expected_total = expected_base + expected_scout_bonus

        for payout in payouts:
            self.assertEqual(payout["base_share"], expected_base)
            self.assertEqual(payout["scout_bonus"], expected_scout_bonus)
            self.assertEqual(payout["amount"], expected_total)
            self.assertTrue(payout["is_scout"])

    def test_calculate_payouts_mixed_scouts_and_regular(self):
        """Test payout calculation with mix of scouts and regular participants"""
        # Create participants (2 scouts, 2 regular)
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char1,
            is_scout=False,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char2,
            is_scout=True,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char3,
            is_scout=False,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char4,
            is_scout=True,
        )

        # Create loot pool
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),  # 100M ISK
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Assertions
        self.assertEqual(len(payouts), 4)

        # Base share (same for everyone)
        expected_base = Decimal("22500000.00")  # (100M - 10M corp) / 4
        expected_scout_bonus = Decimal("2250000.00")  # 10% of base

        scout_count = 0
        regular_count = 0

        for payout in payouts:
            self.assertEqual(payout["base_share"], expected_base)

            if payout["is_scout"]:
                self.assertEqual(payout["scout_bonus"], expected_scout_bonus)
                self.assertEqual(payout["amount"], expected_base + expected_scout_bonus)
                scout_count += 1
            else:
                self.assertEqual(payout["scout_bonus"], Decimal("0.00"))
                self.assertEqual(payout["amount"], expected_base)
                regular_count += 1

        self.assertEqual(scout_count, 2)
        self.assertEqual(regular_count, 2)

    def test_calculate_payouts_single_scout(self):
        """Test payout calculation with single scout participant"""
        # Create one scout
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char2,
            is_scout=True,
        )

        # Create loot pool
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),  # 100M ISK
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Assertions
        self.assertEqual(len(payouts), 1)

        # Scout gets base + bonus
        expected_base = Decimal("90000000.00")  # (100M - 10M corp) / 1
        expected_scout_bonus = Decimal("9000000.00")  # 10% of base
        expected_total = expected_base + expected_scout_bonus

        payout = payouts[0]
        self.assertEqual(payout["base_share"], expected_base)
        self.assertEqual(payout["scout_bonus"], expected_scout_bonus)
        self.assertEqual(payout["amount"], expected_total)
        self.assertTrue(payout["is_scout"])

    def test_calculate_payouts_rounding(self):
        """Test payout calculation with rounding edge cases"""
        # Create 3 participants (1 scout, 2 regular)
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char1,
            is_scout=False,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char2,
            is_scout=True,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char3,
            is_scout=False,
        )

        # Create loot pool with value that doesn't divide evenly
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.33"),  # 100M + 33 cents
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Assertions
        self.assertEqual(len(payouts), 3)

        # All amounts should be rounded to 2 decimal places
        for payout in payouts:
            # Check decimal places
            self.assertEqual(payout["amount"].as_tuple().exponent, -2)
            self.assertEqual(payout["base_share"].as_tuple().exponent, -2)
            self.assertEqual(payout["scout_bonus"].as_tuple().exponent, -2)

    def test_create_payouts_with_scouts(self):
        """Test creating Payout records with scout bonus"""
        # Create participants
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char1,
            is_scout=False,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char2,
            is_scout=True,
        )

        # Create loot pool
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),
            valued_at=timezone.now(),
        )

        # Create payouts
        payouts_created = create_payouts(loot_pool)

        # Assertions
        self.assertEqual(payouts_created, 2)

        payouts = Payout.objects.filter(loot_pool=loot_pool)
        self.assertEqual(payouts.count(), 2)

        # Check scout payout
        scout_payout = payouts.get(recipient=self.char2)
        self.assertTrue(scout_payout.is_scout_payout)
        self.assertGreater(scout_payout.amount, Decimal("45000000.00"))

        # Check regular payout
        regular_payout = payouts.get(recipient=self.char1)
        self.assertFalse(regular_payout.is_scout_payout)

    def test_scout_bonus_percentage_configurable(self):
        """Test that scout bonus percentage is configurable"""
        # Create one scout
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char2,
            is_scout=True,
        )

        # Create loot pool
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),
            valued_at=timezone.now(),
        )

        # Calculate payouts with default 10% bonus
        payouts = calculate_payouts(loot_pool)

        # Default 10% scout bonus
        expected_base = Decimal("90000000.00")
        expected_bonus = Decimal("9000000.00")  # 10%

        self.assertEqual(payouts[0]["scout_bonus"], expected_bonus)

        # Verify using configured percentage
        scout_bonus_pct = Decimal(str(app_settings.AAPAYOUT_SCOUT_BONUS_PERCENTAGE))
        calculated_bonus = (expected_base * scout_bonus_pct / Decimal("100")).quantize(Decimal("0.01"))
        self.assertEqual(calculated_bonus, expected_bonus)

    def test_excluded_participants_no_scout_bonus(self):
        """Test that excluded participants don't receive scout bonus"""
        # Create scout participant but exclude them
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char2,
            is_scout=True,
            excluded_from_payout=True,
        )
        # Create regular participant
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char1,
            is_scout=False,
        )

        # Create loot pool
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Only one payout (excluded scout not included)
        self.assertEqual(len(payouts), 1)
        self.assertEqual(payouts[0]["character"], self.char1)
        self.assertFalse(payouts[0]["is_scout"])
