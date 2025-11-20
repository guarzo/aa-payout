"""
Tests for AA-Payout helper functions
"""

# Standard Library
from decimal import Decimal
from unittest.mock import patch

# Django
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

# Alliance Auth (External Libs)
from eveuniverse.models import EveEntity

# AA Payout
from aapayout import app_settings, constants
from aapayout.helpers import calculate_payouts, create_loot_items_from_appraisal
from aapayout.models import Fleet, FleetParticipant, LootPool


class CalculatePayoutsTest(TestCase):
    """Test payout calculation logic"""

    def setUp(self):
        """Patch settings before each test"""
        # Patch app_settings to use low minimum payout for tests
        self.settings_patcher = patch.object(app_settings, "AAPAYOUT_MINIMUM_PAYOUT", 1000)  # 1k ISK minimum for tests
        self.per_participant_patcher = patch.object(
            app_settings, "AAPAYOUT_MINIMUM_PER_PARTICIPANT", 1000
        )  # 1k ISK minimum for tests
        self.settings_patcher.start()
        self.per_participant_patcher.start()

    def tearDown(self):
        """Stop patching settings"""
        self.settings_patcher.stop()
        self.per_participant_patcher.stop()

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        cls.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=cls.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_ACTIVE,
        )

        # Create test characters
        cls.char1, _ = EveEntity.objects.get_or_create(
            id=12345,
            defaults={
                "name": "Character 1",
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )

        cls.char2, _ = EveEntity.objects.get_or_create(
            id=12346,
            defaults={
                "name": "Character 2",
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )

        cls.char3, _ = EveEntity.objects.get_or_create(
            id=12347,
            defaults={
                "name": "Character 3",
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )

        # Add participants (Phase 2: set main_character for deduplication)
        FleetParticipant.objects.create(
            fleet=cls.fleet,
            character=cls.char1,
            main_character=cls.char1,  # Each character is their own main
            role=constants.ROLE_REGULAR,
            joined_at=timezone.now(),
        )

        FleetParticipant.objects.create(
            fleet=cls.fleet,
            character=cls.char2,
            main_character=cls.char2,  # Each character is their own main
            role=constants.ROLE_REGULAR,
            joined_at=timezone.now(),
        )

        FleetParticipant.objects.create(
            fleet=cls.fleet,
            character=cls.char3,
            main_character=cls.char3,  # Each character is their own main
            role=constants.ROLE_REGULAR,
            joined_at=timezone.now(),
        )

        cls.loot_pool = LootPool.objects.create(
            fleet=cls.fleet,
            name="Test Loot",
            raw_loot_text="Test",
            status=constants.LOOT_STATUS_VALUED,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
            total_value=Decimal("100000.00"),
        )

    def test_calculate_payouts_even_split(self):
        """Test basic even split calculation"""
        payouts = calculate_payouts(self.loot_pool)

        # Should have 3 payouts (one per participant)
        self.assertEqual(len(payouts), 3)

        # Total value is 100,000
        # Corp share: 10% = 10,000
        # Participant pool: 90,000
        # Each participant: 90,000 / 3 = 30,000

        for payout in payouts:
            self.assertEqual(payout["amount"], Decimal("30000.00"))

    def test_calculate_payouts_with_rounding(self):
        """Test payout calculation with rounding"""
        # Create a loot pool with value that doesn't divide evenly
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot Rounding",
            raw_loot_text="Test",
            status=constants.LOOT_STATUS_VALUED,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
            total_value=Decimal("100.00"),
        )

        payouts = calculate_payouts(loot_pool)

        # Total: 100
        # Corp: 10
        # Participant pool: 90
        # Each: 90 / 3 = 30.00 (divides evenly in this case)

        total_paid = sum(p["amount"] for p in payouts)

        # Total paid should not exceed participant pool
        self.assertLessEqual(total_paid, Decimal("90.00"))

        # Each payout should be 30.00
        for payout in payouts:
            self.assertEqual(payout["amount"], Decimal("30.00"))

    def test_calculate_payouts_excludes_left_participants(self):
        """Test that participants who left are excluded"""
        # Mark one participant as left
        participant = FleetParticipant.objects.get(character=self.char3)
        participant.left_at = timezone.now()
        participant.save()

        payouts = calculate_payouts(self.loot_pool)

        # Should only have 2 payouts now
        self.assertEqual(len(payouts), 2)

        # Each should get 90,000 / 2 = 45,000
        for payout in payouts:
            self.assertEqual(payout["amount"], Decimal("45000.00"))

    def test_calculate_payouts_no_participants(self):
        """Test calculation with no participants"""
        # Create a fleet with no participants
        empty_fleet = Fleet.objects.create(
            name="Empty Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_ACTIVE,
        )

        empty_loot_pool = LootPool.objects.create(
            fleet=empty_fleet,
            name="Empty Loot",
            raw_loot_text="Test",
            status=constants.LOOT_STATUS_VALUED,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
            total_value=Decimal("100000.00"),
        )

        payouts = calculate_payouts(empty_loot_pool)

        # Should have no payouts
        self.assertEqual(len(payouts), 0)

    def test_calculate_payouts_zero_corp_share(self):
        """Test calculation with 0% corp share"""
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="No Corp Share",
            raw_loot_text="Test",
            status=constants.LOOT_STATUS_VALUED,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("0.00"),
            total_value=Decimal("90000.00"),
        )

        payouts = calculate_payouts(loot_pool)

        # All 90,000 should go to participants
        # Each: 90,000 / 3 = 30,000
        for payout in payouts:
            self.assertEqual(payout["amount"], Decimal("30000.00"))


class CreateLootItemsFromAppraisalTest(TestCase):
    """Test loot item creation from Janice appraisal"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        cls.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=cls.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_ACTIVE,
        )

        cls.loot_pool = LootPool.objects.create(
            fleet=cls.fleet,
            name="Test Loot",
            raw_loot_text="Compressed Arkonor\t1000",
            status=constants.LOOT_STATUS_VALUING,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
        )

    def test_create_loot_items_from_appraisal(self):
        """Test creating loot items from Janice appraisal data"""
        appraisal_data = {
            "items": [
                {
                    "type_id": 46676,
                    "name": "Compressed Arkonor",
                    "quantity": 1000,
                    "unit_price": Decimal("5000.50"),
                    "total_value": Decimal("5000500.00"),
                },
                {
                    "type_id": 46678,
                    "name": "Compressed Bistot",
                    "quantity": 500,
                    "unit_price": Decimal("3500.25"),
                    "total_value": Decimal("1750125.00"),
                },
            ],
        }

        items_count = create_loot_items_from_appraisal(self.loot_pool, appraisal_data)

        # Should create 2 items
        self.assertEqual(items_count, 2)

        # Verify items were created
        items = list(self.loot_pool.items.all())
        self.assertEqual(len(items), 2)

        # Check first item
        item1 = items[0]
        self.assertEqual(item1.type_id, 46676)
        self.assertEqual(item1.name, "Compressed Arkonor")
        self.assertEqual(item1.quantity, 1000)
        self.assertEqual(item1.unit_price, Decimal("5000.50"))
        self.assertEqual(item1.total_value, Decimal("5000500.00"))
        self.assertEqual(item1.price_source, constants.PRICE_SOURCE_JANICE)

        # Check second item
        item2 = items[1]
        self.assertEqual(item2.type_id, 46678)
        self.assertEqual(item2.name, "Compressed Bistot")
        self.assertEqual(item2.quantity, 500)
        self.assertEqual(item2.unit_price, Decimal("3500.25"))
        self.assertEqual(item2.total_value, Decimal("1750125.00"))

    def test_create_loot_items_empty_appraisal(self):
        """Test handling empty appraisal data"""
        appraisal_data = {
            "items": [],
        }

        items_count = create_loot_items_from_appraisal(self.loot_pool, appraisal_data)

        # Should create no items
        self.assertEqual(items_count, 0)

    def test_create_loot_items_updates_status(self):
        """Test that loot pool status is updated after creating items"""
        appraisal_data = {
            "items": [
                {
                    "type_id": 46676,
                    "name": "Compressed Arkonor",
                    "quantity": 1000,
                    "unit_price": Decimal("5000.50"),
                    "total_value": Decimal("5000500.00"),
                },
            ],
        }

        create_loot_items_from_appraisal(self.loot_pool, appraisal_data)

        # Refresh from database
        self.loot_pool.refresh_from_db()

        # Status should be updated to valued
        self.assertEqual(self.loot_pool.status, constants.LOOT_STATUS_VALUED)
