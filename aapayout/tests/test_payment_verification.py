"""
Tests for Payment Verification (Phase 2 Week 7)
"""

# Standard Library
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Django
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

# Alliance Auth (External Libs)
from eveuniverse.models import EveEntity

# AA Payout
from aapayout import constants
from aapayout.models import Fleet, LootPool, Payout
from aapayout.services.esi_wallet import ESIWalletService


class TestESIWalletService(TestCase):
    """Test ESI Wallet Service"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data"""
        # Create test user
        cls.user = User.objects.create_user(username="testfc", password="password")

        # Create test characters
        cls.fc_character, _ = EveEntity.objects.get_or_create(id=12345678, defaults={"name": "Test FC"})

        cls.recipient1, _ = EveEntity.objects.get_or_create(id=11111111, defaults={"name": "Pilot One"})

        cls.recipient2, _ = EveEntity.objects.get_or_create(id=22222222, defaults={"name": "Pilot Two"})

    def setUp(self):
        """Set up each test"""
        # Create test fleet
        self.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_COMPLETED,
        )

        # Create loot pool
        self.loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            status=constants.LOOT_STATUS_APPROVED,
            total_value=Decimal("100000000.00"),
            corp_share_percentage=Decimal("10.00"),
            corp_share_amount=Decimal("10000000.00"),
            participant_share_amount=Decimal("90000000.00"),
        )

        # Create test payouts
        self.payout1 = Payout.objects.create(
            loot_pool=self.loot_pool,
            recipient=self.recipient1,
            amount=Decimal("45000000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
        )

        self.payout2 = Payout.objects.create(
            loot_pool=self.loot_pool,
            recipient=self.recipient2,
            amount=Decimal("45000000.00"),
            status=constants.PAYOUT_STATUS_PENDING,
        )

    def test_match_payout_to_journal_success(self):
        """Test successful payout matching"""
        # Mock journal entries
        journal_entries = [
            {
                "id": 123456789,
                "date": timezone.now().isoformat(),
                "ref_type": "player_donation",
                "first_party_id": 12345678,
                "second_party_id": 11111111,
                "amount": -45000000.00,
                "balance": 50000000.00,
                "description": "Fleet payout",
            },
            {
                "id": 123456790,
                "date": timezone.now().isoformat(),
                "ref_type": "player_donation",
                "first_party_id": 12345678,
                "second_party_id": 99999999,  # Different recipient
                "amount": -30000000.00,
                "balance": 80000000.00,
            },
        ]

        # Match payout1
        match = ESIWalletService.match_payout_to_journal(
            payout_amount=Decimal("45000000.00"),
            recipient_character_id=11111111,
            journal_entries=journal_entries,
            time_window_hours=24,
        )

        self.assertIsNotNone(match)
        self.assertEqual(match["id"], 123456789)
        self.assertEqual(match["second_party_id"], 11111111)

    def test_match_payout_to_journal_no_match(self):
        """Test no matching journal entry"""
        journal_entries = [
            {
                "id": 123456789,
                "date": timezone.now().isoformat(),
                "ref_type": "player_donation",
                "first_party_id": 12345678,
                "second_party_id": 99999999,  # Wrong recipient
                "amount": -45000000.00,
                "balance": 50000000.00,
            }
        ]

        match = ESIWalletService.match_payout_to_journal(
            payout_amount=Decimal("45000000.00"),
            recipient_character_id=11111111,
            journal_entries=journal_entries,
            time_window_hours=24,
        )

        self.assertIsNone(match)

    def test_match_payout_to_journal_old_entry(self):
        """Test that old journal entries are not matched"""
        # Old entry from 48 hours ago
        old_date = timezone.now() - timedelta(hours=48)

        journal_entries = [
            {
                "id": 123456789,
                "date": old_date.isoformat(),
                "ref_type": "player_donation",
                "first_party_id": 12345678,
                "second_party_id": 11111111,
                "amount": -45000000.00,
                "balance": 50000000.00,
            }
        ]

        match = ESIWalletService.match_payout_to_journal(
            payout_amount=Decimal("45000000.00"),
            recipient_character_id=11111111,
            journal_entries=journal_entries,
            time_window_hours=24,  # 24 hour window
        )

        self.assertIsNone(match)

    def test_match_payout_wrong_amount(self):
        """Test that wrong amounts don't match"""
        journal_entries = [
            {
                "id": 123456789,
                "date": timezone.now().isoformat(),
                "ref_type": "player_donation",
                "first_party_id": 12345678,
                "second_party_id": 11111111,
                "amount": -50000000.00,  # Wrong amount
                "balance": 50000000.00,
            }
        ]

        match = ESIWalletService.match_payout_to_journal(
            payout_amount=Decimal("45000000.00"),
            recipient_character_id=11111111,
            journal_entries=journal_entries,
            time_window_hours=24,
        )

        self.assertIsNone(match)

    def test_match_payout_wrong_ref_type(self):
        """Test that non-donation ref types don't match"""
        journal_entries = [
            {
                "id": 123456789,
                "date": timezone.now().isoformat(),
                "ref_type": "bounty_prizes",  # Wrong type
                "first_party_id": 12345678,
                "second_party_id": 11111111,
                "amount": -45000000.00,
                "balance": 50000000.00,
            }
        ]

        match = ESIWalletService.match_payout_to_journal(
            payout_amount=Decimal("45000000.00"),
            recipient_character_id=11111111,
            journal_entries=journal_entries,
            time_window_hours=24,
        )

        self.assertIsNone(match)

    @patch("aapayout.services.esi_wallet.esi")
    def test_get_wallet_journal_success(self, mock_esi):
        """Test successful wallet journal retrieval"""
        # Mock ESI response
        mock_result = MagicMock()
        mock_result.results.return_value = [
            {"id": 123456789, "date": timezone.now().isoformat(), "ref_type": "player_donation", "amount": -45000000.00}
        ]
        mock_esi.client.Wallet.get_characters_character_id_wallet_journal.return_value = mock_result

        # Mock token
        mock_token = MagicMock()
        mock_token.has_scope.return_value = True
        mock_token.valid_access_token.return_value = "test_token"

        # Get journal
        journal = ESIWalletService.get_wallet_journal(character_id=12345678, token=mock_token, max_pages=1)

        self.assertIsNotNone(journal)
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["id"], 123456789)

    @patch("aapayout.services.esi_wallet.esi")
    def test_get_wallet_journal_pagination(self, mock_esi):
        """Test wallet journal pagination"""
        # Mock ESI response with multiple pages
        mock_result1 = MagicMock()
        mock_result1.results.return_value = [{"id": 1}, {"id": 2}]

        mock_result2 = MagicMock()
        mock_result2.results.return_value = [{"id": 3}, {"id": 4}]

        mock_result3 = MagicMock()
        mock_result3.results.return_value = []  # Empty page ends pagination

        mock_esi.client.Wallet.get_characters_character_id_wallet_journal.side_effect = [
            mock_result1,
            mock_result2,
            mock_result3,
        ]

        # Mock token
        mock_token = MagicMock()
        mock_token.has_scope.return_value = True
        mock_token.valid_access_token.return_value = "test_token"

        # Get journal
        journal = ESIWalletService.get_wallet_journal(character_id=12345678, token=mock_token, max_pages=10)

        self.assertIsNotNone(journal)
        self.assertEqual(len(journal), 4)  # 2 from page 1, 2 from page 2

    def test_get_wallet_journal_no_scope(self):
        """Test wallet journal with missing scope"""
        # Mock token without scope
        mock_token = MagicMock()
        mock_token.has_scope.return_value = False

        # Get journal
        journal = ESIWalletService.get_wallet_journal(character_id=12345678, token=mock_token)

        self.assertIsNone(journal)

    def test_verify_payouts_success(self):
        """Test successful payout verification"""
        # Mock journal with matching entries
        journal_entries = [
            {
                "id": 123456789,
                "date": timezone.now().isoformat(),
                "ref_type": "player_donation",
                "first_party_id": 12345678,
                "second_party_id": 11111111,
                "amount": -45000000.00,
                "balance": 95000000.00,
            },
            {
                "id": 123456790,
                "date": timezone.now().isoformat(),
                "ref_type": "player_donation",
                "first_party_id": 12345678,
                "second_party_id": 22222222,
                "amount": -45000000.00,
                "balance": 50000000.00,
            },
        ]

        # Mock token
        mock_token = MagicMock()
        mock_token.character_id = 12345678  # Must match fc_character_id
        mock_token.has_scope.return_value = True
        mock_token.valid_access_token.return_value = "test_token"

        # Mock ESI call
        with patch.object(ESIWalletService, "get_wallet_journal", return_value=journal_entries):
            # Verify payouts
            verified, pending, errors = ESIWalletService.verify_payouts(
                payouts=[self.payout1, self.payout2], fc_character_id=12345678, token=mock_token
            )

        # Check results
        self.assertEqual(verified, 2)
        self.assertEqual(pending, 0)
        self.assertEqual(len(errors), 0)

        # Reload payouts
        self.payout1.refresh_from_db()
        self.payout2.refresh_from_db()

        # Check status
        self.assertEqual(self.payout1.status, "paid")
        self.assertTrue(self.payout1.verified)
        self.assertIsNotNone(self.payout1.verified_at)

        self.assertEqual(self.payout2.status, "paid")
        self.assertTrue(self.payout2.verified)
        self.assertIsNotNone(self.payout2.verified_at)

    def test_verify_payouts_partial_match(self):
        """Test partial payout verification"""
        # Mock journal with only one matching entry
        journal_entries = [
            {
                "id": 123456789,
                "date": timezone.now().isoformat(),
                "ref_type": "player_donation",
                "first_party_id": 12345678,
                "second_party_id": 11111111,
                "amount": -45000000.00,
                "balance": 50000000.00,
            }
        ]

        # Mock token
        mock_token = MagicMock()
        mock_token.character_id = 12345678  # Must match fc_character_id
        mock_token.has_scope.return_value = True
        mock_token.valid_access_token.return_value = "test_token"

        # Mock ESI call
        with patch.object(ESIWalletService, "get_wallet_journal", return_value=journal_entries):
            # Verify payouts
            verified, pending, errors = ESIWalletService.verify_payouts(
                payouts=[self.payout1, self.payout2], fc_character_id=12345678, token=mock_token
            )

        # Check results
        self.assertEqual(verified, 1)
        self.assertEqual(pending, 1)

        # Reload payouts
        self.payout1.refresh_from_db()
        self.payout2.refresh_from_db()

        # Check status
        self.assertEqual(self.payout1.status, "paid")
        self.assertTrue(self.payout1.verified)

        self.assertEqual(self.payout2.status, "pending")
        self.assertFalse(self.payout2.verified)

    def test_verify_payouts_esi_error(self):
        """Test verification with ESI error"""
        # Mock token
        mock_token = MagicMock()
        mock_token.character_id = 12345678  # Must match fc_character_id

        # Mock ESI call returning None (error)
        with patch.object(ESIWalletService, "get_wallet_journal", return_value=None):
            # Verify payouts
            verified, pending, errors = ESIWalletService.verify_payouts(
                payouts=[self.payout1, self.payout2], fc_character_id=12345678, token=mock_token
            )

        # Check results
        self.assertEqual(verified, 0)
        self.assertEqual(pending, 2)
        self.assertIn("Failed to fetch wallet journal", errors[0])
