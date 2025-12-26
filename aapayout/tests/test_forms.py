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
            "battle_report": "https://br.evetools.org/123456",
            "notes": "Test notes",
        }

        form = FleetCreateForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_missing_required_fields(self):
        """Test form with missing required fields"""
        form_data = {
            "battle_report": "https://br.evetools.org/123456",
            # Missing name
        }

        form = FleetCreateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_optional_fields(self):
        """Test form with optional fields empty"""
        form_data = {
            "name": "Test Fleet",
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
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_DRAFT,
        )

    def test_edit_fleet_valid(self):
        """Test editing fleet with valid data"""
        form_data = {
            "name": "Updated Fleet Name",
            "fleet_time": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "battle_report": "https://zkillboard.com/related/123456",
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
        }

        form = ParticipantAddForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_missing_character_name(self):
        """Test form with missing character name"""
        form_data = {}

        form = ParticipantAddForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("character_name", form.errors)

    def test_is_scout_true(self):
        """Test form with is_scout set to True"""
        form_data = {
            "character_name": "Scout Character",
            "is_scout": True,
        }

        form = ParticipantAddForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertTrue(form.cleaned_data["is_scout"])

    def test_is_scout_false(self):
        """Test form with is_scout set to False"""
        form_data = {
            "character_name": "Regular Character",
            "is_scout": False,
        }

        form = ParticipantAddForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertFalse(form.cleaned_data["is_scout"])

    def test_is_scout_not_required(self):
        """Test that is_scout field is optional"""
        form_data = {
            "character_name": "Test Character",
        }

        form = ParticipantAddForm(data=form_data)
        self.assertTrue(form.is_valid())


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

    def test_is_scout_in_edit_form(self):
        """Test that is_scout field can be edited"""
        joined_at = timezone.now()

        form_data = {
            "role": constants.ROLE_REGULAR,
            "is_scout": True,
            "joined_at": joined_at.strftime("%Y-%m-%dT%H:%M"),
            "notes": "Test notes",
        }

        form = ParticipantEditForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertTrue(form.cleaned_data["is_scout"])


class LootPoolCreateFormTest(TestCase):
    """Test LootPoolCreateForm"""

    def test_valid_form(self):
        """Test form with valid data"""
        form_data = {
            "name": "Test Loot Pool",
            "raw_loot_text": "Compressed Arkonor\t1000\nCompressed Bistot\t500",
            "pricing_method": constants.PRICING_JANICE_BUY,
            "scout_shares": "1.5",
        }

        form = LootPoolCreateForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_empty_loot_text(self):
        """Test validation for empty loot text"""
        form_data = {
            "name": "Test Loot Pool",
            "raw_loot_text": "",
            "pricing_method": constants.PRICING_JANICE_BUY,
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
        }

        form = LootPoolCreateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("raw_loot_text", form.errors)


class LootPoolApproveFormTest(TestCase):
    """Test LootPoolApproveForm"""

    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=user,
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
            "confirm": True,
        }

        form = LootPoolApproveForm(self.loot_pool, data=form_data)
        self.assertTrue(form.is_valid())

    def test_missing_confirmation(self):
        """Test that confirmation is required"""
        form_data = {
            "confirm": False,
        }

        form = LootPoolApproveForm(self.loot_pool, data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("confirm", form.errors)


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
