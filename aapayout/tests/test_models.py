"""
Tests for AA-Payout models
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
from aapayout import constants
from aapayout.models import Fleet, FleetParticipant, LootItem, LootPool, Payout


class FleetModelTest(TestCase):
    """Test Fleet model"""

    @classmethod
    def setUpTestData(cls):
        # Create test user
        cls.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

    def test_create_fleet(self):
        """Test creating a fleet"""
        fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

        self.assertEqual(fleet.name, "Test Fleet")
        self.assertEqual(fleet.fleet_commander, self.user)
        self.assertEqual(fleet.status, constants.FLEET_STATUS_DRAFT)

    def test_fleet_str_representation(self):
        """Test fleet __str__ method"""
        fleet_time = timezone.now()
        fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=fleet_time,
            status=constants.FLEET_STATUS_DRAFT,
        )

        expected_str = f"Test Fleet - {fleet_time.strftime('%Y-%m-%d')}"
        self.assertEqual(str(fleet), expected_str)

    def test_fleet_can_edit_owner(self):
        """Test that fleet commander can edit their fleet"""
        fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

        self.assertTrue(fleet.can_edit(self.user))

    def test_fleet_can_edit_other_user(self):
        """Test that other users cannot edit fleet without permission"""
        other_user = User.objects.create_user(username="otheruser", email="other@example.com", password="testpass")

        fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

        self.assertFalse(fleet.can_edit(other_user))

    def test_get_participant_count(self):
        """Test getting participant count"""
        fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

        self.assertEqual(fleet.get_participant_count(), 0)

    def test_get_total_loot_value(self):
        """Test getting total loot value"""
        fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

        self.assertEqual(fleet.get_total_loot_value(), Decimal("0.00"))


class FleetParticipantModelTest(TestCase):
    """Test FleetParticipant model"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        cls.character = EveEntity.objects.create(
            id=12345,
            name="Test Character",
            category=EveEntity.CATEGORY_CHARACTER,
        )

        cls.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=cls.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

    def test_create_participant(self):
        """Test creating a participant"""
        participant = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.character,
            role=constants.ROLE_REGULAR,
            joined_at=timezone.now(),
        )

        self.assertEqual(participant.fleet, self.fleet)
        self.assertEqual(participant.character, self.character)
        self.assertEqual(participant.role, constants.ROLE_REGULAR)

    def test_participant_is_active(self):
        """Test participant is_active property"""
        participant = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.character,
            role=constants.ROLE_REGULAR,
            joined_at=timezone.now(),
        )

        self.assertTrue(participant.is_active)

        participant.left_at = timezone.now()
        participant.save()

        self.assertFalse(participant.is_active)

    def test_participant_str_representation(self):
        """Test participant __str__ method"""
        participant = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.character,
            role=constants.ROLE_REGULAR,
            joined_at=timezone.now(),
        )

        self.assertIn("Test Character", str(participant))
        self.assertIn("Test Fleet", str(participant))

    def test_role_scout_syncs_is_scout(self):
        """Test that setting role to 'scout' automatically sets is_scout to True"""
        participant = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.character,
            role=constants.ROLE_SCOUT,
            joined_at=timezone.now(),
        )

        # is_scout should be auto-set to True when role is 'scout'
        self.assertTrue(participant.is_scout)

    def test_is_scout_can_be_set_independently(self):
        """Test that is_scout can be set to True even when role is 'regular'"""
        participant = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.character,
            role=constants.ROLE_REGULAR,
            is_scout=True,
            joined_at=timezone.now(),
        )

        # is_scout should remain True even though role is 'regular'
        self.assertTrue(participant.is_scout)
        self.assertEqual(participant.role, constants.ROLE_REGULAR)

    def test_is_scout_defaults_to_false(self):
        """Test that is_scout defaults to False"""
        participant = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.character,
            role=constants.ROLE_REGULAR,
            joined_at=timezone.now(),
        )

        # is_scout should default to False
        self.assertFalse(participant.is_scout)


class LootPoolModelTest(TestCase):
    """Test LootPool model"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        cls.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=cls.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

    def test_create_loot_pool(self):
        """Test creating a loot pool"""
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            raw_loot_text="Compressed Arkonor\t1000",
            status=constants.LOOT_STATUS_DRAFT,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
        )

        self.assertEqual(loot_pool.fleet, self.fleet)
        self.assertEqual(loot_pool.name, "Test Loot")
        self.assertEqual(loot_pool.corp_share_percentage, Decimal("10.00"))

    def test_loot_pool_calculate_totals(self):
        """Test loot pool total calculation"""
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            raw_loot_text="Compressed Arkonor\t1000",
            status=constants.LOOT_STATUS_DRAFT,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
        )

        # Create some loot items
        LootItem.objects.create(
            loot_pool=loot_pool,
            type_id=12345,
            name="Item 1",
            quantity=100,
            unit_price=Decimal("1000.00"),
            price_source=constants.PRICE_SOURCE_JANICE,
        )

        LootItem.objects.create(
            loot_pool=loot_pool,
            type_id=12346,
            name="Item 2",
            quantity=50,
            unit_price=Decimal("500.00"),
            price_source=constants.PRICE_SOURCE_JANICE,
        )

        loot_pool.calculate_totals()

        # Total value should be (100 * 1000) + (50 * 500) = 125,000
        self.assertEqual(loot_pool.total_value, Decimal("125000.00"))
        # Corp share should be 10% = 12,500
        self.assertEqual(loot_pool.corp_share_amount, Decimal("12500.00"))
        # Participant share should be 90% = 112,500
        self.assertEqual(loot_pool.participant_share_amount, Decimal("112500.00"))

    def test_loot_pool_str_representation(self):
        """Test loot pool __str__ method"""
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            raw_loot_text="Compressed Arkonor\t1000",
            status=constants.LOOT_STATUS_DRAFT,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
        )

        self.assertEqual(str(loot_pool), "Test Loot - Test Fleet")


class LootItemModelTest(TestCase):
    """Test LootItem model"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        cls.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=cls.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

        cls.loot_pool = LootPool.objects.create(
            fleet=cls.fleet,
            name="Test Loot",
            raw_loot_text="Compressed Arkonor\t1000",
            status=constants.LOOT_STATUS_DRAFT,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
        )

    def test_create_loot_item(self):
        """Test creating a loot item"""
        item = LootItem.objects.create(
            loot_pool=self.loot_pool,
            type_id=12345,
            name="Test Item",
            quantity=100,
            unit_price=Decimal("1000.00"),
            price_source=constants.PRICE_SOURCE_JANICE,
        )

        self.assertEqual(item.name, "Test Item")
        self.assertEqual(item.quantity, 100)
        self.assertEqual(item.unit_price, Decimal("1000.00"))

    def test_loot_item_total_value_calculation(self):
        """Test loot item total value is calculated correctly"""
        item = LootItem.objects.create(
            loot_pool=self.loot_pool,
            type_id=12345,
            name="Test Item",
            quantity=100,
            unit_price=Decimal("1000.00"),
            price_source=constants.PRICE_SOURCE_JANICE,
        )

        # total_value should be automatically calculated
        self.assertEqual(item.total_value, Decimal("100000.00"))

    def test_loot_item_str_representation(self):
        """Test loot item __str__ method"""
        item = LootItem.objects.create(
            loot_pool=self.loot_pool,
            type_id=12345,
            name="Test Item",
            quantity=100,
            unit_price=Decimal("1000.00"),
            price_source=constants.PRICE_SOURCE_JANICE,
        )

        self.assertIn("Test Item", str(item))


class PayoutModelTest(TestCase):
    """Test Payout model"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        cls.character = EveEntity.objects.create(
            id=12345,
            name="Test Character",
            category=EveEntity.CATEGORY_CHARACTER,
        )

        cls.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=cls.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

        cls.loot_pool = LootPool.objects.create(
            fleet=cls.fleet,
            name="Test Loot",
            raw_loot_text="Compressed Arkonor\t1000",
            status=constants.LOOT_STATUS_APPROVED,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
        )

    def test_create_payout(self):
        """Test creating a payout"""
        payout = Payout.objects.create(
            loot_pool=self.loot_pool,
            recipient=self.character,
            amount=Decimal("10000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
        )

        self.assertEqual(payout.loot_pool, self.loot_pool)
        self.assertEqual(payout.recipient, self.character)
        self.assertEqual(payout.amount, Decimal("10000.00"))
        self.assertEqual(payout.status, constants.PAYOUT_STATUS_PENDING)

    def test_payout_mark_paid(self):
        """Test marking a payout as paid"""
        payout = Payout.objects.create(
            loot_pool=self.loot_pool,
            recipient=self.character,
            amount=Decimal("10000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
        )

        payout.mark_paid(user=self.user, reference="TEST-123")

        self.assertEqual(payout.status, constants.PAYOUT_STATUS_PAID)
        self.assertEqual(payout.paid_by, self.user)
        self.assertEqual(payout.transaction_reference, "TEST-123")
        self.assertIsNotNone(payout.paid_at)

    def test_payout_str_representation(self):
        """Test payout __str__ method"""
        payout = Payout.objects.create(
            loot_pool=self.loot_pool,
            recipient=self.character,
            amount=Decimal("10000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
        )

        self.assertIn("Test Character", str(payout))
        self.assertIn("10,000.00", str(payout))  # Formatted with commas
