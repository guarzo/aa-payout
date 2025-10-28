"""
Tests for Payout History View (Phase 2 Week 8)
"""

# Standard Library
from datetime import timedelta
from decimal import Decimal

# Django
from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

# Alliance Auth (External Libs)
from eveuniverse.models import EveEntity

# AA Payout
from aapayout import constants
from aapayout.models import Fleet, LootPool, Payout


class TestPayoutHistoryView(TestCase):
    """Test Payout History View with filtering and search"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data"""
        # Import Alliance Auth models
        # Alliance Auth
        from allianceauth.authentication.models import CharacterOwnership, UserProfile
        from allianceauth.eveonline.models import EveCharacter

        # Create test users
        cls.user1 = User.objects.create_user(username="user1", password="password")
        cls.user2 = User.objects.create_user(username="user2", password="password")
        cls.admin = User.objects.create_user(username="admin", password="password")

        # Grant admin permissions
        view_all_perm = Permission.objects.get(codename="view_all_payouts")
        cls.admin.user_permissions.add(view_all_perm)
        basic_access = Permission.objects.get(codename="basic_access")
        cls.user1.user_permissions.add(basic_access)
        cls.user2.user_permissions.add(basic_access)
        cls.admin.user_permissions.add(basic_access)

        # Create main characters for users
        cls.char1_eve = EveCharacter.objects.create(
            character_id=11111111,
            character_name="Test Character 1",
            corporation_id=2001,
            corporation_name="Test Corp",
            corporation_ticker="TEST",
        )
        CharacterOwnership.objects.create(
            user=cls.user1,
            character=cls.char1_eve,
            owner_hash="test_hash_user1",
        )
        profile1, _ = UserProfile.objects.get_or_create(user=cls.user1)
        profile1.main_character = cls.char1_eve
        profile1.save()

        cls.char2_eve = EveCharacter.objects.create(
            character_id=22222222,
            character_name="Test Character 2",
            corporation_id=2001,
            corporation_name="Test Corp",
            corporation_ticker="TEST",
        )
        CharacterOwnership.objects.create(
            user=cls.user2,
            character=cls.char2_eve,
            owner_hash="test_hash_user2",
        )
        profile2, _ = UserProfile.objects.get_or_create(user=cls.user2)
        profile2.main_character = cls.char2_eve
        profile2.save()

        # Create main character for admin
        cls.admin_char_eve = EveCharacter.objects.create(
            character_id=33333333,
            character_name="Admin Character",
            corporation_id=2001,
            corporation_name="Test Corp",
            corporation_ticker="TEST",
        )
        CharacterOwnership.objects.create(
            user=cls.admin,
            character=cls.admin_char_eve,
            owner_hash="test_hash_admin",
        )
        profile_admin, _ = UserProfile.objects.get_or_create(user=cls.admin)
        profile_admin.main_character = cls.admin_char_eve
        profile_admin.save()

        # Create EveEntity for payout recipients
        cls.char1, _ = EveEntity.objects.get_or_create(id=11111111, defaults={"name": "Test Character 1"})
        cls.char2, _ = EveEntity.objects.get_or_create(id=22222222, defaults={"name": "Test Character 2"})

        # Create test fleets
        cls.fleet1 = Fleet.objects.create(
            name="Test Fleet Alpha",
            fleet_commander=cls.user1,
            fleet_time=timezone.now() - timedelta(days=5),
            status=constants.FLEET_STATUS_COMPLETED,
        )

        cls.fleet2 = Fleet.objects.create(
            name="Test Fleet Bravo",
            fleet_commander=cls.user2,
            fleet_time=timezone.now() - timedelta(days=2),
            status=constants.FLEET_STATUS_COMPLETED,
        )

        # Create loot pools
        cls.loot_pool1 = LootPool.objects.create(
            fleet=cls.fleet1,
            name="Loot Pool 1",
            status=constants.LOOT_STATUS_APPROVED,
            total_value=Decimal("100000000.00"),
        )

        cls.loot_pool2 = LootPool.objects.create(
            fleet=cls.fleet2,
            name="Loot Pool 2",
            status=constants.LOOT_STATUS_APPROVED,
            total_value=Decimal("200000000.00"),
        )

        # Create payouts for both characters
        cls.payout1_user1 = Payout.objects.create(
            loot_pool=cls.loot_pool1,
            recipient=cls.char1,
            amount=Decimal("45000000.00"),
            status=constants.PAYOUT_STATUS_PAID,
            paid_at=timezone.now() - timedelta(days=4),
            is_scout_payout=True,
            verified=True,
        )

        cls.payout2_user1 = Payout.objects.create(
            loot_pool=cls.loot_pool2,
            recipient=cls.char1,
            amount=Decimal("90000000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
            is_scout_payout=False,
        )

        cls.payout1_user2 = Payout.objects.create(
            loot_pool=cls.loot_pool1,
            recipient=cls.char2,
            amount=Decimal("45000000.00"),
            status=constants.PAYOUT_STATUS_PAID,
            paid_at=timezone.now() - timedelta(days=4),
        )

        cls.payout2_user2 = Payout.objects.create(
            loot_pool=cls.loot_pool2,
            recipient=cls.char2,
            amount=Decimal("90000000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
        )

    def setUp(self):
        """Set up each test"""
        self.client = Client()

    def test_history_view_requires_login(self):
        """Test that history view requires login"""
        response = self.client.get(reverse("aapayout:payout_history"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_history_view_regular_user_only_sees_own_payouts(self):
        """Test that regular users only see their own payouts"""
        self.client.login(username="user1", password="password")
        response = self.client.get(reverse("aapayout:payout_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Character 1")
        self.assertNotContains(response, "Test Character 2")

        # Check context
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertFalse(response.context["can_view_all"])

    def test_history_view_admin_sees_all_payouts(self):
        """Test that admins see all payouts"""
        self.client.login(username="admin", password="password")
        response = self.client.get(reverse("aapayout:payout_history"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_view_all"])

        # Check that all payouts are visible
        payouts = list(response.context["page_obj"])
        self.assertEqual(len(payouts), 4)

    def test_history_view_filter_by_status(self):
        """Test filtering by status"""
        self.client.login(username="admin", password="password")

        # Filter for paid payouts
        response = self.client.get(reverse("aapayout:payout_history"), {"status": constants.PAYOUT_STATUS_PAID})

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context["page_obj"])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.status == constants.PAYOUT_STATUS_PAID for p in payouts))

        # Filter for pending payouts
        response = self.client.get(reverse("aapayout:payout_history"), {"status": constants.PAYOUT_STATUS_PENDING})

        payouts = list(response.context["page_obj"])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.status == constants.PAYOUT_STATUS_PENDING for p in payouts))

    def test_history_view_filter_by_fleet(self):
        """Test filtering by fleet"""
        self.client.login(username="admin", password="password")

        # Filter for fleet1
        response = self.client.get(reverse("aapayout:payout_history"), {"fleet": self.fleet1.pk})

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context["page_obj"])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.loot_pool.fleet == self.fleet1 for p in payouts))

    def test_history_view_search_by_character_name(self):
        """Test searching by character name"""
        self.client.login(username="admin", password="password")

        # Search for character 1
        response = self.client.get(reverse("aapayout:payout_history"), {"search": "Character 1"})

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context["page_obj"])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.recipient == self.char1 for p in payouts))

    def test_history_view_search_by_fleet_name(self):
        """Test searching by fleet name"""
        self.client.login(username="admin", password="password")

        # Search for "Alpha" fleet
        response = self.client.get(reverse("aapayout:payout_history"), {"search": "Alpha"})

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context["page_obj"])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.loot_pool.fleet == self.fleet1 for p in payouts))

    def test_history_view_combined_filters(self):
        """Test combining multiple filters"""
        self.client.login(username="admin", password="password")

        # Filter for paid + fleet1 + character1
        response = self.client.get(
            reverse("aapayout:payout_history"),
            {"status": constants.PAYOUT_STATUS_PAID, "fleet": self.fleet1.pk, "search": "Character 1"},
        )

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context["page_obj"])
        self.assertEqual(len(payouts), 1)
        self.assertEqual(payouts[0], self.payout1_user1)

    def test_history_view_summary_totals(self):
        """Test summary totals calculation"""
        self.client.login(username="admin", password="password")

        response = self.client.get(reverse("aapayout:payout_history"))

        self.assertEqual(response.status_code, 200)

        # Check totals
        self.assertEqual(response.context["count_paid"], 2)
        self.assertEqual(response.context["count_pending"], 2)
        self.assertEqual(response.context["total_paid"], Decimal("90000000.00"))  # 2 paid payouts of 45M each
        self.assertEqual(response.context["total_pending"], Decimal("180000000.00"))  # 2 pending payouts of 90M each

    def test_history_view_pagination(self):
        """Test pagination"""
        # Create many payouts
        for _i in range(120):
            Payout.objects.create(
                loot_pool=self.loot_pool1,
                recipient=self.char1,
                amount=Decimal("1000000.00"),
                status=constants.PAYOUT_STATUS_PAID,
            )

        self.client.login(username="admin", password="password")

        # Get first page
        response = self.client.get(reverse("aapayout:payout_history"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["page_obj"].has_next())
        self.assertEqual(len(response.context["page_obj"]), 100)  # 100 per page

        # Get second page
        response = self.client.get(reverse("aapayout:payout_history"), {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["page_obj"].has_previous() is False)

    def test_history_view_filter_preservation(self):
        """Test that filter values are preserved in context"""
        self.client.login(username="admin", password="password")

        # Apply filters
        response = self.client.get(
            reverse("aapayout:payout_history"),
            {
                "status": constants.PAYOUT_STATUS_PAID,
                "fleet": self.fleet1.pk,
                "search": "test search",
                "date_from": "2025-01-01",
                "date_to": "2025-12-31",
            },
        )

        self.assertEqual(response.status_code, 200)

        # Check that filters are in context
        self.assertEqual(response.context["filter_status"], constants.PAYOUT_STATUS_PAID)
        self.assertEqual(response.context["filter_fleet"], str(self.fleet1.pk))
        self.assertEqual(response.context["filter_search"], "test search")
        self.assertEqual(response.context["filter_date_from"], "2025-01-01")
        self.assertEqual(response.context["filter_date_to"], "2025-12-31")

    def test_history_view_invalid_date_format(self):
        """Test handling of invalid date format"""
        self.client.login(username="admin", password="password")

        # Invalid date format
        response = self.client.get(reverse("aapayout:payout_history"), {"date_from": "invalid-date"})

        self.assertEqual(response.status_code, 200)
        # Should still work, just ignore the invalid date
        messages = list(response.context["messages"])
        self.assertTrue(any("Invalid date format" in str(m) for m in messages))
