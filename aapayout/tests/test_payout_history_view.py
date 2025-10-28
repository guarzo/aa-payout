"""
Tests for Payout History View (Phase 2 Week 8)
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from eveuniverse.models import EveEntity

from aapayout import constants
from aapayout.models import Fleet, LootPool, Payout


class TestPayoutHistoryView(TestCase):
    """Test Payout History View with filtering and search"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data"""
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

        # Create test characters
        cls.char1, _ = EveEntity.objects.get_or_create(
            id=11111111,
            defaults={"name": "Test Character 1", "category_id": 1}
        )

        cls.char2, _ = EveEntity.objects.get_or_create(
            id=22222222,
            defaults={"name": "Test Character 2", "category_id": 1}
        )

        # Mock user profiles with main characters
        cls.user1.profile.main_character = cls.char1
        cls.user1.profile.save()

        cls.user2.profile.main_character = cls.char2
        cls.user2.profile.save()

        # Create test fleets
        cls.fleet1 = Fleet.objects.create(
            name="Test Fleet Alpha",
            fleet_commander=cls.user1,
            location="Jita",
            fleet_time=timezone.now() - timedelta(days=5),
            status=constants.FLEET_STATUS_COMPLETED
        )

        cls.fleet2 = Fleet.objects.create(
            name="Test Fleet Bravo",
            fleet_commander=cls.user2,
            location="Amarr",
            fleet_time=timezone.now() - timedelta(days=2),
            status=constants.FLEET_STATUS_COMPLETED
        )

        # Create loot pools
        cls.loot_pool1 = LootPool.objects.create(
            fleet=cls.fleet1,
            name="Loot Pool 1",
            status=constants.LOOT_STATUS_APPROVED,
            total_value=Decimal("100000000.00")
        )

        cls.loot_pool2 = LootPool.objects.create(
            fleet=cls.fleet2,
            name="Loot Pool 2",
            status=constants.LOOT_STATUS_APPROVED,
            total_value=Decimal("200000000.00")
        )

        # Create payouts for both characters
        cls.payout1_user1 = Payout.objects.create(
            loot_pool=cls.loot_pool1,
            recipient=cls.char1,
            amount=Decimal("45000000.00"),
            status=constants.PAYOUT_STATUS_PAID,
            paid_at=timezone.now() - timedelta(days=4),
            is_scout_payout=True,
            verified=True
        )

        cls.payout2_user1 = Payout.objects.create(
            loot_pool=cls.loot_pool2,
            recipient=cls.char1,
            amount=Decimal("90000000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
            is_scout_payout=False
        )

        cls.payout1_user2 = Payout.objects.create(
            loot_pool=cls.loot_pool1,
            recipient=cls.char2,
            amount=Decimal("45000000.00"),
            status=constants.PAYOUT_STATUS_PAID,
            paid_at=timezone.now() - timedelta(days=4)
        )

        cls.payout2_user2 = Payout.objects.create(
            loot_pool=cls.loot_pool2,
            recipient=cls.char2,
            amount=Decimal("90000000.00"),
            status=constants.PAYOUT_STATUS_PENDING
        )

    def setUp(self):
        """Set up each test"""
        self.client = Client()

    def test_history_view_requires_login(self):
        """Test that history view requires login"""
        response = self.client.get(reverse('aapayout:payout_history'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_history_view_regular_user_only_sees_own_payouts(self):
        """Test that regular users only see their own payouts"""
        self.client.login(username='user1', password='password')
        response = self.client.get(reverse('aapayout:payout_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Character 1")
        self.assertNotContains(response, "Test Character 2")

        # Check context
        self.assertEqual(response.context['page_obj'].paginator.count, 2)
        self.assertFalse(response.context['can_view_all'])

    def test_history_view_admin_sees_all_payouts(self):
        """Test that admins see all payouts"""
        self.client.login(username='admin', password='password')
        response = self.client.get(reverse('aapayout:payout_history'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_view_all'])

        # Check that all payouts are visible
        payouts = list(response.context['page_obj'])
        self.assertEqual(len(payouts), 4)

    def test_history_view_filter_by_status(self):
        """Test filtering by status"""
        self.client.login(username='admin', password='password')

        # Filter for paid payouts
        response = self.client.get(
            reverse('aapayout:payout_history'),
            {'status': constants.PAYOUT_STATUS_PAID}
        )

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context['page_obj'])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.status == constants.PAYOUT_STATUS_PAID for p in payouts))

        # Filter for pending payouts
        response = self.client.get(
            reverse('aapayout:payout_history'),
            {'status': constants.PAYOUT_STATUS_PENDING}
        )

        payouts = list(response.context['page_obj'])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.status == constants.PAYOUT_STATUS_PENDING for p in payouts))

    def test_history_view_filter_by_fleet(self):
        """Test filtering by fleet"""
        self.client.login(username='admin', password='password')

        # Filter for fleet1
        response = self.client.get(
            reverse('aapayout:payout_history'),
            {'fleet': self.fleet1.pk}
        )

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context['page_obj'])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.loot_pool.fleet == self.fleet1 for p in payouts))

    def test_history_view_search_by_character_name(self):
        """Test searching by character name"""
        self.client.login(username='admin', password='password')

        # Search for character 1
        response = self.client.get(
            reverse('aapayout:payout_history'),
            {'search': 'Character 1'}
        )

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context['page_obj'])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.recipient == self.char1 for p in payouts))

    def test_history_view_search_by_fleet_name(self):
        """Test searching by fleet name"""
        self.client.login(username='admin', password='password')

        # Search for "Alpha" fleet
        response = self.client.get(
            reverse('aapayout:payout_history'),
            {'search': 'Alpha'}
        )

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context['page_obj'])
        self.assertEqual(len(payouts), 2)
        self.assertTrue(all(p.loot_pool.fleet == self.fleet1 for p in payouts))

    def test_history_view_filter_by_date_range(self):
        """Test filtering by date range"""
        self.client.login(username='admin', password='password')

        # Filter for last 3 days
        date_from = (timezone.now() - timedelta(days=3)).strftime("%Y-%m-%d")

        response = self.client.get(
            reverse('aapayout:payout_history'),
            {'date_from': date_from}
        )

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context['page_obj'])
        # Only payouts from fleet2 (2 days ago)
        self.assertEqual(len(payouts), 2)

    def test_history_view_combined_filters(self):
        """Test combining multiple filters"""
        self.client.login(username='admin', password='password')

        # Filter for paid + fleet1 + character1
        response = self.client.get(
            reverse('aapayout:payout_history'),
            {
                'status': constants.PAYOUT_STATUS_PAID,
                'fleet': self.fleet1.pk,
                'search': 'Character 1'
            }
        )

        self.assertEqual(response.status_code, 200)
        payouts = list(response.context['page_obj'])
        self.assertEqual(len(payouts), 1)
        self.assertEqual(payouts[0], self.payout1_user1)

    def test_history_view_summary_totals(self):
        """Test summary totals calculation"""
        self.client.login(username='admin', password='password')

        response = self.client.get(reverse('aapayout:payout_history'))

        self.assertEqual(response.status_code, 200)

        # Check totals
        self.assertEqual(response.context['count_paid'], 2)
        self.assertEqual(response.context['count_pending'], 2)
        self.assertEqual(
            response.context['total_paid'],
            Decimal("90000000.00")  # 2 paid payouts of 45M each
        )
        self.assertEqual(
            response.context['total_pending'],
            Decimal("180000000.00")  # 2 pending payouts of 90M each
        )

    def test_history_view_pagination(self):
        """Test pagination"""
        # Create many payouts
        for i in range(120):
            Payout.objects.create(
                loot_pool=self.loot_pool1,
                recipient=self.char1,
                amount=Decimal("1000000.00"),
                status=constants.PAYOUT_STATUS_PAID
            )

        self.client.login(username='admin', password='password')

        # Get first page
        response = self.client.get(reverse('aapayout:payout_history'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['page_obj'].has_next())
        self.assertEqual(len(response.context['page_obj']), 100)  # 100 per page

        # Get second page
        response = self.client.get(
            reverse('aapayout:payout_history'),
            {'page': 2}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['page_obj'].has_previous() is False)

    def test_history_view_shows_scout_badge(self):
        """Test that scout payouts show scout badge"""
        self.client.login(username='user1', password='password')
        response = self.client.get(reverse('aapayout:payout_history'))

        self.assertEqual(response.status_code, 200)
        # Check that scout badge is displayed
        self.assertContains(response, 'badge-scout')
        self.assertContains(response, 'Scout')

    def test_history_view_shows_verified_badge(self):
        """Test that verified payouts show verified badge"""
        self.client.login(username='user1', password='password')
        response = self.client.get(reverse('aapayout:payout_history'))

        self.assertEqual(response.status_code, 200)
        # Check that verified badge is displayed
        self.assertContains(response, 'badge-verified')
        self.assertContains(response, 'Verified')

    def test_history_view_filter_preservation(self):
        """Test that filter values are preserved in context"""
        self.client.login(username='admin', password='password')

        # Apply filters
        response = self.client.get(
            reverse('aapayout:payout_history'),
            {
                'status': constants.PAYOUT_STATUS_PAID,
                'fleet': self.fleet1.pk,
                'search': 'test search',
                'date_from': '2025-01-01',
                'date_to': '2025-12-31'
            }
        )

        self.assertEqual(response.status_code, 200)

        # Check that filters are in context
        self.assertEqual(response.context['filter_status'], constants.PAYOUT_STATUS_PAID)
        self.assertEqual(response.context['filter_fleet'], str(self.fleet1.pk))
        self.assertEqual(response.context['filter_search'], 'test search')
        self.assertEqual(response.context['filter_date_from'], '2025-01-01')
        self.assertEqual(response.context['filter_date_to'], '2025-12-31')

    def test_history_view_invalid_date_format(self):
        """Test handling of invalid date format"""
        self.client.login(username='admin', password='password')

        # Invalid date format
        response = self.client.get(
            reverse('aapayout:payout_history'),
            {'date_from': 'invalid-date'}
        )

        self.assertEqual(response.status_code, 200)
        # Should still work, just ignore the invalid date
        messages = list(response.context['messages'])
        self.assertTrue(any('Invalid date format' in str(m) for m in messages))

    def test_history_view_query_optimization(self):
        """Test that view uses select_related for query optimization"""
        self.client.login(username='admin', password='password')

        with self.assertNumQueries(6):  # Should be a limited number of queries
            response = self.client.get(reverse('aapayout:payout_history'))
            # Accessing related objects shouldn't trigger additional queries
            for payout in response.context['page_obj']:
                _ = payout.recipient.name
                _ = payout.loot_pool.fleet.name
                _ = payout.loot_pool.fleet.fleet_commander.username

    def test_history_view_mobile_responsive(self):
        """Test that template includes responsive design elements"""
        self.client.login(username='admin', password='password')
        response = self.client.get(reverse('aapayout:payout_history'))

        self.assertEqual(response.status_code, 200)
        # Check for responsive table wrapper
        self.assertContains(response, 'table-responsive')
        # Check for responsive grid classes
        self.assertContains(response, 'col-md-')
        self.assertContains(response, 'col-sm-')
