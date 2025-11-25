"""
Tests for Scout Bonus Calculations

Phase 2: Week 5 - Scout Bonus Calculation
"""

# Standard Library
from decimal import ROUND_DOWN, Decimal
from unittest.mock import patch

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
        # With no scouts, it's a simple even split
        expected_base = Decimal("45000000.00")  # (100M - 10M corp) / 2

        for payout in payouts:
            self.assertEqual(payout["amount"], expected_base)
            self.assertEqual(payout["base_share"], expected_base)
            self.assertEqual(payout["scout_bonus"], Decimal("0.00"))
            self.assertFalse(payout["is_scout"])

        # Verify total doesn't exceed participant pool
        total_distributed = sum(p["amount"] for p in payouts)
        participant_pool = Decimal("90000000.00")  # 100M - 10M corp
        self.assertLessEqual(total_distributed, participant_pool)

    def test_calculate_payouts_all_scouts(self):
        """Test payout calculation with all scouts

        When all participants are scouts, they all get the same share since
        the weighted calculation results in equal shares (no regulars to compare against).
        """
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

        # With all scouts (2 scouts, 0 regular):
        # - Scout weight = 1.1 (10% bonus)
        # - Total shares = 2 * 1.1 = 2.2
        # - Value per share = 90M / 2.2 = 40,909,090.90...
        # - Base share (1.0 share) = 40,909,090.90 (rounded down)
        # - Scout share (1.1 shares) = 45,000,000.00 (rounded down from 45,000,000.00)
        # - Scout bonus = 45M - 40.9M = 4,090,909.10
        participant_pool = Decimal("90000000.00")  # 100M - 10M corp
        total_shares = Decimal("2.2")  # 2 scouts * 1.1 weight
        value_per_share = participant_pool / total_shares
        expected_base = value_per_share.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        scout_weight = Decimal("1.10")
        expected_scout_share = (value_per_share * scout_weight).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_scout_bonus = expected_scout_share - expected_base

        for payout in payouts:
            self.assertEqual(payout["base_share"], expected_base)
            self.assertEqual(payout["scout_bonus"], expected_scout_bonus)
            self.assertEqual(payout["amount"], expected_scout_share)
            self.assertTrue(payout["is_scout"])

        # Verify total doesn't exceed participant pool
        total_distributed = sum(p["amount"] for p in payouts)
        self.assertLessEqual(total_distributed, participant_pool)

    def test_calculate_payouts_mixed_scouts_and_regular(self):
        """Test payout calculation with mix of scouts and regular participants

        This is the key test demonstrating that scout bonuses redistribute
        from a fixed pool rather than adding additional ISK.
        """
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

        # With 2 scouts (1.1 weight each) and 2 regular (1.0 weight each):
        # - Total shares = 2*1.1 + 2*1.0 = 4.2
        # - Participant pool = 90M
        # - Value per share = 90M / 4.2 = 21,428,571.42...
        # - Base share (1.0 share) = 21,428,571.42 (rounded down)
        # - Scout share (1.1 shares) = 23,571,428.57 (rounded down)
        participant_pool = Decimal("90000000.00")
        total_shares = Decimal("4.2")  # 2*1.1 + 2*1.0
        value_per_share = participant_pool / total_shares
        expected_base = value_per_share.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        scout_weight = Decimal("1.10")
        expected_scout_share = (value_per_share * scout_weight).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_scout_bonus = expected_scout_share - expected_base

        scout_count = 0
        regular_count = 0

        for payout in payouts:
            self.assertEqual(payout["base_share"], expected_base)

            if payout["is_scout"]:
                self.assertEqual(payout["scout_bonus"], expected_scout_bonus)
                self.assertEqual(payout["amount"], expected_scout_share)
                scout_count += 1
            else:
                self.assertEqual(payout["scout_bonus"], Decimal("0.00"))
                self.assertEqual(payout["amount"], expected_base)
                regular_count += 1

        self.assertEqual(scout_count, 2)
        self.assertEqual(regular_count, 2)

        # CRITICAL: Verify total doesn't exceed participant pool
        total_distributed = sum(p["amount"] for p in payouts)
        self.assertLessEqual(total_distributed, participant_pool)

    def test_calculate_payouts_single_scout(self):
        """Test payout calculation with single scout participant

        When there's only one participant (a scout), they get the entire participant pool.
        Since there are no regular participants to compare against, the calculation
        is effectively: all pool to single scout.
        """
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

        # With 1 scout (1.1 weight):
        # - Total shares = 1.1
        # - Participant pool = 90M
        # - Value per share = 90M / 1.1 = 81,818,181.81...
        # - Base share = 81,818,181.81 (rounded down)
        # - Scout share (1.1 shares) = 90M (rounded down from full calculation)
        participant_pool = Decimal("90000000.00")
        total_shares = Decimal("1.1")
        value_per_share = participant_pool / total_shares
        expected_base = value_per_share.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        scout_weight = Decimal("1.10")
        expected_scout_share = (value_per_share * scout_weight).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_scout_bonus = expected_scout_share - expected_base

        payout = payouts[0]
        self.assertEqual(payout["base_share"], expected_base)
        self.assertEqual(payout["scout_bonus"], expected_scout_bonus)
        self.assertEqual(payout["amount"], expected_scout_share)
        self.assertTrue(payout["is_scout"])

        # Verify total doesn't exceed participant pool
        self.assertLessEqual(payout["amount"], participant_pool)

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
        """Test that scout bonus percentage is configurable via loot pool"""
        # Create one scout and one regular participant
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char2,
            is_scout=True,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char1,
            is_scout=False,
        )

        # Create loot pool with 20% scout bonus
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            scout_bonus_percentage=Decimal("20.00"),  # 20% instead of default 10%
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),
            valued_at=timezone.now(),
        )

        # Calculate payouts with 20% bonus
        payouts = calculate_payouts(loot_pool)
        self.assertEqual(len(payouts), 2)

        # With 1 scout (1.2 weight) and 1 regular (1.0 weight):
        # - Total shares = 1.2 + 1.0 = 2.2
        # - Participant pool = 90M
        # - Value per share = 90M / 2.2 = 40,909,090.90...
        # - Base share = 40,909,090.90 (rounded down)
        # - Scout share (1.2 shares) = 49,090,909.09 (rounded down)
        participant_pool = Decimal("90000000.00")
        total_shares = Decimal("2.2")  # 1*1.2 + 1*1.0
        value_per_share = participant_pool / total_shares
        expected_base = value_per_share.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        scout_weight = Decimal("1.20")  # 1.0 + 20%
        expected_scout_share = (value_per_share * scout_weight).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_scout_bonus = expected_scout_share - expected_base

        # Find scout payout
        scout_payout = [p for p in payouts if p["is_scout"]][0]
        self.assertEqual(scout_payout["scout_bonus"], expected_scout_bonus)
        self.assertEqual(scout_payout["amount"], expected_scout_share)

        # Verify total doesn't exceed participant pool
        total_distributed = sum(p["amount"] for p in payouts)
        self.assertLessEqual(total_distributed, participant_pool)

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
