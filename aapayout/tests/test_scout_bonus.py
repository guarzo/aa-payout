"""
Tests for Scout Shares Calculations

Phase 2: Week 5 - Scout Shares Calculation (Share-based system)
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


class ScoutSharesCalculationTests(TestCase):
    """Tests for scout shares payout calculations"""

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

        # Create loot pool with scout_shares (doesn't matter when no scouts)
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            scout_shares=Decimal("2.0"),  # 2 shares for scouts (unused here)
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),  # 100M ISK
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Assertions
        self.assertEqual(len(payouts), 2)

        # Each gets base share only (no scout bonus)
        # With no scouts: 2 participants × 1 share = 2 shares total
        # Per-share value: 90M / 2 = 45M
        expected_base = Decimal("45000000.00")

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
        they all have the same number of shares.
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

        # Create loot pool with 2 shares for scouts
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            scout_shares=Decimal("2.0"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),  # 100M ISK
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Assertions
        self.assertEqual(len(payouts), 2)

        # With all scouts (2 scouts × 2 shares each):
        # - Total shares = 2 × 2 = 4
        # - Participant pool = 90M
        # - Per-share value = 90M / 4 = 22.5M
        # - Scout payout = 2 × 22.5M = 45M
        participant_pool = Decimal("90000000.00")  # 100M - 10M corp
        total_shares = Decimal("4.0")  # 2 scouts × 2 shares
        per_share_value = (participant_pool / total_shares).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_scout_payout = (per_share_value * Decimal("2.0")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        for payout in payouts:
            self.assertEqual(payout["base_share"], per_share_value)
            self.assertEqual(payout["amount"], expected_scout_payout)
            self.assertTrue(payout["is_scout"])

        # Verify total doesn't exceed participant pool
        total_distributed = sum(p["amount"] for p in payouts)
        self.assertLessEqual(total_distributed, participant_pool)

    def test_calculate_payouts_mixed_scouts_and_regular(self):
        """Test payout calculation with mix of scouts and regular participants

        This is the key test demonstrating that scout shares give scouts
        more shares from a fixed pool rather than adding additional ISK.
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

        # Create loot pool with 2 shares for scouts
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            scout_shares=Decimal("2.0"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),  # 100M ISK
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Assertions
        self.assertEqual(len(payouts), 4)

        # With 2 scouts (2 shares each) and 2 regular (1 share each):
        # - Total shares = 2×2 + 2×1 = 6
        # - Participant pool = 90M
        # - Per-share value = 90M / 6 = 15M
        # - Scout payout (2 shares) = 30M
        # - Regular payout (1 share) = 15M
        participant_pool = Decimal("90000000.00")
        total_shares = Decimal("6.0")  # 2×2 + 2×1
        per_share_value = (participant_pool / total_shares).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_scout_payout = (per_share_value * Decimal("2.0")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_regular_payout = per_share_value
        expected_scout_bonus = expected_scout_payout - per_share_value

        scout_count = 0
        regular_count = 0

        for payout in payouts:
            self.assertEqual(payout["base_share"], per_share_value)

            if payout["is_scout"]:
                self.assertEqual(payout["scout_bonus"], expected_scout_bonus)
                self.assertEqual(payout["amount"], expected_scout_payout)
                scout_count += 1
            else:
                self.assertEqual(payout["scout_bonus"], Decimal("0.00"))
                self.assertEqual(payout["amount"], expected_regular_payout)
                regular_count += 1

        self.assertEqual(scout_count, 2)
        self.assertEqual(regular_count, 2)

        # CRITICAL: Verify total doesn't exceed participant pool
        total_distributed = sum(p["amount"] for p in payouts)
        self.assertLessEqual(total_distributed, participant_pool)

    def test_calculate_payouts_single_scout(self):
        """Test payout calculation with single scout participant

        When there's only one participant (a scout), they get the entire participant pool.
        """
        # Create one scout
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.char2,
            is_scout=True,
        )

        # Create loot pool with 2 shares for scouts
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            scout_shares=Decimal("2.0"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),  # 100M ISK
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Assertions
        self.assertEqual(len(payouts), 1)

        # With 1 scout (2 shares):
        # - Total shares = 2
        # - Participant pool = 90M
        # - Per-share value = 90M / 2 = 45M
        # - Scout payout = 2 × 45M = 90M
        participant_pool = Decimal("90000000.00")
        total_shares = Decimal("2.0")
        per_share_value = (participant_pool / total_shares).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_scout_payout = (per_share_value * Decimal("2.0")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        payout = payouts[0]
        self.assertEqual(payout["base_share"], per_share_value)
        self.assertEqual(payout["amount"], expected_scout_payout)
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
            scout_shares=Decimal("2.0"),
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
        """Test creating Payout records with scout shares"""
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

        # Create loot pool with 2 shares for scouts
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            scout_shares=Decimal("2.0"),
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

        # With 1 scout (2 shares) and 1 regular (1 share):
        # Total shares = 3, Pool = 90M, Per-share = 30M
        # Scout = 60M, Regular = 30M

        # Check scout payout
        scout_payout = payouts.get(recipient=self.char2)
        self.assertTrue(scout_payout.is_scout_payout)
        self.assertEqual(scout_payout.amount, Decimal("60000000.00"))

        # Check regular payout
        regular_payout = payouts.get(recipient=self.char1)
        self.assertFalse(regular_payout.is_scout_payout)
        self.assertEqual(regular_payout.amount, Decimal("30000000.00"))

    def test_scout_shares_configurable(self):
        """Test that scout shares is configurable via loot pool"""
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

        # Create loot pool with 3 shares for scouts
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            scout_shares=Decimal("3.0"),  # 3 shares instead of default 1.5
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),
            valued_at=timezone.now(),
        )

        # Calculate payouts with 3 shares for scouts
        payouts = calculate_payouts(loot_pool)
        self.assertEqual(len(payouts), 2)

        # With 1 scout (3 shares) and 1 regular (1 share):
        # - Total shares = 3 + 1 = 4
        # - Participant pool = 90M
        # - Per-share value = 90M / 4 = 22.5M
        # - Scout payout (3 shares) = 67.5M
        # - Regular payout (1 share) = 22.5M
        participant_pool = Decimal("90000000.00")
        total_shares = Decimal("4.0")
        per_share_value = (participant_pool / total_shares).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_scout_payout = (per_share_value * Decimal("3.0")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

        # Find scout payout
        scout_payout = next(p for p in payouts if p["is_scout"])
        self.assertEqual(scout_payout["amount"], expected_scout_payout)

        # Verify total doesn't exceed participant pool
        total_distributed = sum(p["amount"] for p in payouts)
        self.assertLessEqual(total_distributed, participant_pool)

    def test_excluded_participants_no_scout_shares(self):
        """Test that excluded participants don't receive scout shares"""
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
            scout_shares=Decimal("2.0"),
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

    def test_fractional_scout_shares(self):
        """Test fractional scout shares (e.g., 1.5 shares)"""
        # Create participants (1 scout, 1 regular)
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

        # Create loot pool with 1.5 shares for scouts
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            scout_shares=Decimal("1.5"),
            status=constants.LOOT_STATUS_VALUED,
            total_value=Decimal("100000000.00"),
            valued_at=timezone.now(),
        )

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)
        self.assertEqual(len(payouts), 2)

        # With 1 scout (1.5 shares) and 1 regular (1 share):
        # - Total shares = 1.5 + 1 = 2.5
        # - Participant pool = 90M
        # - Per-share value = 90M / 2.5 = 36M
        # - Scout payout (1.5 shares) = 54M
        # - Regular payout (1 share) = 36M
        participant_pool = Decimal("90000000.00")
        total_shares = Decimal("2.5")
        per_share_value = (participant_pool / total_shares).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_scout_payout = (per_share_value * Decimal("1.5")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        expected_regular_payout = per_share_value

        scout_payout = next(p for p in payouts if p["is_scout"])
        regular_payout = next(p for p in payouts if not p["is_scout"])

        self.assertEqual(scout_payout["amount"], expected_scout_payout)
        self.assertEqual(regular_payout["amount"], expected_regular_payout)

        # Verify total doesn't exceed participant pool
        total_distributed = sum(p["amount"] for p in payouts)
        self.assertLessEqual(total_distributed, participant_pool)
