"""
Tests for AA-Payout forms
"""

# Standard Library
from decimal import Decimal

# Django
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

# AA Payout
from aapayout import constants
from aapayout.forms import (
    FleetCreateForm,
    FleetEditForm,
    LootItemEditForm,
    LootPoolApproveForm,
    LootPoolCreateForm,
    ParticipantAddForm,
    ParticipantEditForm,
    PayoutMarkPaidForm,
)
from aapayout.models import Fleet, LootPool


class FleetCreateFormTest(TestCase):
    """Test FleetCreateForm"""

    def test_valid_form(self):
        """Test form with valid data"""
        form_data = {
            "name": "Test Fleet",
            "doctrine": "Stealth Bombers",
            "location": "J123456",
            "fleet_time": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "notes": "Test notes",
        }

        form = FleetCreateForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_missing_required_fields(self):
        """Test form with missing required fields"""
        form_data = {
            "doctrine": "Stealth Bombers",
            # Missing name, location, fleet_time
        }

        form = FleetCreateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("location", form.errors)
        self.assertIn("fleet_time", form.errors)

    def test_optional_fields(self):
        """Test form with optional fields empty"""
        form_data = {
            "name": "Test Fleet",
            "location": "J123456",
            "fleet_time": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        }

        form = FleetCreateForm(data=form_data)
        self.assertTrue(form.is_valid())


class FleetEditFormTest(TestCase):
    """Test FleetEditForm"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        cls.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=cls.user,
            location="J123456",
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

    def test_edit_fleet_valid(self):
        """Test editing fleet with valid data"""
        form_data = {
            "name": "Updated Fleet Name",
            "doctrine": "Updated Doctrine",
            "location": "J654321",
            "fleet_time": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "notes": "Updated notes",
        }

        form = FleetEditForm(data=form_data, instance=self.fleet)
        self.assertTrue(form.is_valid())


class ParticipantAddFormTest(TestCase):
    """Test ParticipantAddForm"""

    def test_valid_form(self):
        """Test form with valid data"""
        form_data = {
            "character_name": "Test Character",
            "role": constants.ROLE_REGULAR,
            "joined_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "notes": "Test notes",
        }

        form = ParticipantAddForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_missing_character_name(self):
        """Test form with missing character name"""
        form_data = {
            "role": constants.ROLE_REGULAR,
            "joined_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        }

        form = ParticipantAddForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("character_name", form.errors)


class ParticipantEditFormTest(TestCase):
    """Test ParticipantEditForm"""

    def test_valid_form(self):
        """Test form with valid data"""
        joined_at = timezone.now()
        left_at = joined_at + timezone.timedelta(hours=2)

        form_data = {
            "role": constants.ROLE_SCOUT,
            "joined_at": joined_at.strftime("%Y-%m-%dT%H:%M"),
            "left_at": left_at.strftime("%Y-%m-%dT%H:%M"),
            "notes": "Updated notes",
        }

        form = ParticipantEditForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_left_before_joined(self):
        """Test validation that left time must be after joined time"""
        joined_at = timezone.now()
        left_at = joined_at - timezone.timedelta(hours=1)  # Before joined

        form_data = {
            "role": constants.ROLE_REGULAR,
            "joined_at": joined_at.strftime("%Y-%m-%dT%H:%M"),
            "left_at": left_at.strftime("%Y-%m-%dT%H:%M"),
        }

        form = ParticipantEditForm(data=form_data)
        self.assertFalse(form.is_valid())


class LootPoolCreateFormTest(TestCase):
    """Test LootPoolCreateForm"""

    def test_valid_form(self):
        """Test form with valid data"""
        form_data = {
            "name": "Test Loot Pool",
            "raw_loot_text": "Compressed Arkonor\t1000\nCompressed Bistot\t500",
            "pricing_method": constants.PRICING_JANICE_BUY,
            "corp_share_percentage": Decimal("10.00"),
        }

        form = LootPoolCreateForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_empty_loot_text(self):
        """Test validation for empty loot text"""
        form_data = {
            "name": "Test Loot Pool",
            "raw_loot_text": "",
            "pricing_method": constants.PRICING_JANICE_BUY,
            "corp_share_percentage": Decimal("10.00"),
        }

        form = LootPoolCreateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("raw_loot_text", form.errors)

    def test_whitespace_only_loot_text(self):
        """Test validation for whitespace-only loot text"""
        form_data = {
            "name": "Test Loot Pool",
            "raw_loot_text": "   \n\n   ",
            "pricing_method": constants.PRICING_JANICE_BUY,
            "corp_share_percentage": Decimal("10.00"),
        }

        form = LootPoolCreateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("raw_loot_text", form.errors)

    def test_invalid_corp_share_percentage(self):
        """Test validation for invalid corp share percentage"""
        form_data = {
            "name": "Test Loot Pool",
            "raw_loot_text": "Compressed Arkonor\t1000",
            "pricing_method": constants.PRICING_JANICE_BUY,
            "corp_share_percentage": Decimal("150.00"),  # Over 100
        }

        form = LootPoolCreateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("corp_share_percentage", form.errors)

    def test_negative_corp_share_percentage(self):
        """Test validation for negative corp share percentage"""
        form_data = {
            "name": "Test Loot Pool",
            "raw_loot_text": "Compressed Arkonor\t1000",
            "pricing_method": constants.PRICING_JANICE_BUY,
            "corp_share_percentage": Decimal("-5.00"),
        }

        form = LootPoolCreateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("corp_share_percentage", form.errors)


class LootItemEditFormTest(TestCase):
    """Test LootItemEditForm"""

    def test_valid_form(self):
        """Test form with valid data"""
        form_data = {
            "unit_price": Decimal("5000.00"),
            "notes": "Manual override due to market fluctuation",
        }

        form = LootItemEditForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_negative_price(self):
        """Test validation for negative price"""
        form_data = {
            "unit_price": Decimal("-1000.00"),
            "notes": "Test",
        }

        form = LootItemEditForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("unit_price", form.errors)

    def test_zero_price(self):
        """Test that zero price is allowed"""
        form_data = {
            "unit_price": Decimal("0.00"),
            "notes": "Worthless item",
        }

        form = LootItemEditForm(data=form_data)
        self.assertTrue(form.is_valid())


class LootPoolApproveFormTest(TestCase):
    """Test LootPoolApproveForm"""

    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=user,
            location="J123456",
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_ACTIVE,
        )

        cls.loot_pool = LootPool.objects.create(
            fleet=fleet,
            name="Test Loot",
            raw_loot_text="Test",
            status=constants.LOOT_STATUS_VALUED,
            pricing_method=constants.PRICING_JANICE_BUY,
            corp_share_percentage=Decimal("10.00"),
            total_value=Decimal("100000.00"),
        )

    def test_valid_form(self):
        """Test form with valid data"""
        form_data = {
            "corp_share_percentage": Decimal("15.00"),
            "confirm": True,
        }

        form = LootPoolApproveForm(self.loot_pool, data=form_data)
        self.assertTrue(form.is_valid())

    def test_missing_confirmation(self):
        """Test that confirmation is required"""
        form_data = {
            "corp_share_percentage": Decimal("10.00"),
            "confirm": False,
        }

        form = LootPoolApproveForm(self.loot_pool, data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("confirm", form.errors)

    def test_default_corp_share(self):
        """Test that default corp share is set from loot pool"""
        form = LootPoolApproveForm(self.loot_pool)

        # Initial value should be from loot pool
        self.assertEqual(form.initial["corp_share_percentage"], self.loot_pool.corp_share_percentage)


class PayoutMarkPaidFormTest(TestCase):
    """Test PayoutMarkPaidForm"""

    def test_valid_form(self):
        """Test form with valid data"""
        form_data = {
            "payment_method": constants.PAYMENT_METHOD_MANUAL,
            "transaction_reference": "TEST-123",
            "notes": "Payment completed via manual transfer",
        }

        form = PayoutMarkPaidForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_optional_fields(self):
        """Test that transaction reference and notes are optional"""
        form_data = {
            "payment_method": constants.PAYMENT_METHOD_CONTRACT,
        }

        form = PayoutMarkPaidForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_default_payment_method(self):
        """Test that default payment method is set"""
        form = PayoutMarkPaidForm()

        # Initial value should be manual
        self.assertEqual(form.fields["payment_method"].initial, constants.PAYMENT_METHOD_MANUAL)
