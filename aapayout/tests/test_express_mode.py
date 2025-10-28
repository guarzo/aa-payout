"""
Tests for Express Mode Payment Interface

Phase 2: Week 6 - Express Mode
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from aapayout import constants
from aapayout.models import Fleet, FleetParticipant, LootPool, Payout
from eveuniverse.models import EveEntity


class ExpressModeViewTests(TestCase):
    """Tests for Express Mode views"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data"""
        # Create user with permissions
        cls.user = User.objects.create_user(
            username="fc_user",
            password="testpass"
        )
        cls.user.user_permissions.add(
            Permission.objects.get(codename="basic_access"),
            Permission.objects.get(codename="approve_payouts"),
        )

        # Create fleet
        cls.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=cls.user,
            location="Jita",
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_ACTIVE,
        )

        # Create characters
        cls.char1 = EveEntity.objects.create(
            id=4001,
            name="Test Pilot 1",
        )
        cls.char2 = EveEntity.objects.create(
            id=4002,
            name="Test Pilot 2",
        )

        # Create participants
        FleetParticipant.objects.create(
            fleet=cls.fleet,
            character=cls.char1,
        )
        FleetParticipant.objects.create(
            fleet=cls.fleet,
            character=cls.char2,
        )

        # Create loot pool
        cls.loot_pool = LootPool.objects.create(
            fleet=cls.fleet,
            name="Test Loot",
            pricing_method=constants.PRICE_SOURCE_JANICE,
            corp_share_percentage=Decimal("10.00"),
            status=constants.LOOT_STATUS_APPROVED,
            total_value=Decimal("100000000.00"),
            valued_at=timezone.now(),
        )

        # Create payouts
        cls.payout1 = Payout.objects.create(
            loot_pool=cls.loot_pool,
            recipient=cls.char1,
            amount=Decimal("45000000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
        )
        cls.payout2 = Payout.objects.create(
            loot_pool=cls.loot_pool,
            recipient=cls.char2,
            amount=Decimal("45000000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
        )

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.client.login(username="fc_user", password="testpass")

    def test_express_mode_start_view(self):
        """Test Express Mode start view loads correctly"""
        url = reverse("aapayout:express_mode_start", kwargs={"pool_id": self.loot_pool.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Express Mode Payment Interface")
        self.assertContains(response, "Test Pilot 1")
        self.assertContains(response, "Test Pilot 2")
        self.assertContains(response, "45,000,000.00 ISK")

    def test_express_mode_requires_permission(self):
        """Test Express Mode requires approve_payouts permission"""
        # Create user without permission
        user = User.objects.create_user(username="noob", password="test")
        user.user_permissions.add(Permission.objects.get(codename="basic_access"))

        client = Client()
        client.login(username="noob", password="test")

        url = reverse("aapayout:express_mode_start", kwargs={"pool_id": self.loot_pool.pk})
        response = client.get(url)

        # Should redirect due to permission denied
        self.assertEqual(response.status_code, 302)

    def test_express_mode_no_pending_payouts(self):
        """Test Express Mode redirects when no pending payouts"""
        # Mark all payouts as paid
        Payout.objects.filter(loot_pool=self.loot_pool).update(
            status=constants.PAYOUT_STATUS_PAID
        )

        url = reverse("aapayout:express_mode_start", kwargs={"pool_id": self.loot_pool.pk})
        response = self.client.get(url)

        # Should redirect to payout list
        self.assertEqual(response.status_code, 302)
        self.assertIn("payouts", response.url)

    @patch("aapayout.views.esi_ui_service.open_character_window")
    @patch("esi.models.Token.objects.filter")
    def test_express_mode_open_window(self, mock_token_filter, mock_open_window):
        """Test Express Mode open character window endpoint"""
        # Mock token
        mock_token = MagicMock()
        mock_token.has_scope.return_value = True
        mock_token.valid_access_token.return_value = "test_token"
        mock_token_filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = mock_token

        # Mock window opening
        mock_open_window.return_value = (True, None)

        url = reverse("aapayout:express_mode_open_window", kwargs={"payout_id": self.payout1.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["character_id"], self.char1.id)
        self.assertEqual(data["character_name"], "Test Pilot 1")

        # Verify window was opened
        mock_open_window.assert_called_once()

    def test_express_mode_mark_paid(self):
        """Test Express Mode mark as paid endpoint"""
        url = reverse("aapayout:express_mode_mark_paid", kwargs={"payout_id": self.payout1.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["payout_id"], self.payout1.pk)

        # Verify payout was marked as paid
        self.payout1.refresh_from_db()
        self.assertEqual(self.payout1.status, constants.PAYOUT_STATUS_PAID)
        self.assertIsNotNone(self.payout1.paid_at)
        self.assertEqual(self.payout1.paid_by, self.user)

    def test_express_mode_mark_paid_requires_permission(self):
        """Test marking paid requires proper permissions"""
        # Create user without permission
        user = User.objects.create_user(username="noob", password="test")
        user.user_permissions.add(Permission.objects.get(codename="basic_access"))

        client = Client()
        client.login(username="noob", password="test")

        url = reverse("aapayout:express_mode_mark_paid", kwargs={"payout_id": self.payout1.pk})
        response = client.post(url)

        # Should return permission denied
        self.assertEqual(response.status_code, 403)
