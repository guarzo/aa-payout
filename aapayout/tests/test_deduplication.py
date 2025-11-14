"""
Tests for character deduplication functionality (Phase 2)
"""

# Standard Library
from decimal import Decimal
from unittest.mock import Mock, patch

# Django
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

# Alliance Auth
from allianceauth.eveonline.models import EveCharacter

# Alliance Auth (External Libs)
from eveuniverse.models import EveEntity

# AA Payout
from aapayout import app_settings
from aapayout.helpers import (
    calculate_payouts,
    deduplicate_participants,
    get_main_character_for_participant,
)
from aapayout.models import Fleet, FleetParticipant, LootPool


class GetMainCharacterForParticipantTest(TestCase):
    """Test get_main_character_for_participant function"""

    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(username="testuser", password="password")

        # Create main character
        self.main_char = EveCharacter.objects.create(
            character_id=1001,
            character_name="Main Character",
            corporation_id=2001,
            corporation_name="Test Corp",
        )

        # Create alt character
        self.alt_char = EveCharacter.objects.create(
            character_id=1002,
            character_name="Alt Character",
            corporation_id=2001,
            corporation_name="Test Corp",
        )

        # Create EveEntity for characters
        self.main_entity, _ = EveEntity.objects.get_or_create(
            id=1001,
            defaults={
                "name": "Main Character",
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )
        self.alt_entity, _ = EveEntity.objects.get_or_create(
            id=1002,
            defaults={
                "name": "Alt Character",
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )

        # Create fleet and participant
        self.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
        )

    def test_get_main_character_for_participant_with_cached_main(self):
        """Test getting main character when already set"""
        # Create participant with main_character already set
        participant = FleetParticipant.objects.create(
            fleet=self.fleet, character=self.alt_entity, main_character=self.main_entity
        )

        # Call function
        result = get_main_character_for_participant(participant)

        # Should return the cached main character
        self.assertEqual(result.id, self.main_entity.id)

    @patch("aapayout.helpers.get_main_character")
    @patch("allianceauth.authentication.models.OwnershipRecord.objects.filter")
    @patch("allianceauth.eveonline.models.EveCharacter.objects.filter")
    def test_get_main_character_for_participant_with_ownership(
        self, mock_eve_char_filter, mock_ownership_filter, mock_get_main
    ):
        """Test getting main character when ownership exists"""
        # Create participant with alt character (no main_character set)
        participant = FleetParticipant.objects.create(fleet=self.fleet, character=self.alt_entity)

        # Mock EveCharacter lookup
        mock_eve_char_filter.return_value.first.return_value = self.alt_char

        # Mock OwnershipRecord lookup
        mock_ownership = Mock()
        mock_ownership.user = self.user
        mock_ownership_filter.return_value.first.return_value = mock_ownership

        # Mock get_main_character to return main character
        mock_get_main.return_value = self.main_char

        # Call function
        with patch.object(EveEntity.objects, "get_or_create_esi", return_value=(self.main_entity, False)):
            result = get_main_character_for_participant(participant)

        # Verify result
        self.assertEqual(result.id, self.main_entity.id)

    def test_get_main_character_for_participant_fallback(self):
        """Test fallback to participant's character when no ownership"""
        # Create participant
        participant = FleetParticipant.objects.create(fleet=self.fleet, character=self.alt_entity)

        # Call function (should fallback since no ownership exists)
        result = get_main_character_for_participant(participant)

        # Should return the participant's character itself
        self.assertEqual(result.id, self.alt_entity.id)


class DeduplicateParticipantsTest(TestCase):
    """Test deduplicate_participants function"""

    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(username="testuser", password="password")

        # Create characters
        self.main_entity, _ = EveEntity.objects.get_or_create(
            id=1001, defaults={"name": "Main Character", "category": EveEntity.CATEGORY_CHARACTER}
        )
        self.alt1_entity, _ = EveEntity.objects.get_or_create(
            id=1002, defaults={"name": "Alt 1", "category": EveEntity.CATEGORY_CHARACTER}
        )
        self.alt2_entity, _ = EveEntity.objects.get_or_create(
            id=1003, defaults={"name": "Alt 2", "category": EveEntity.CATEGORY_CHARACTER}
        )
        self.other_entity, _ = EveEntity.objects.get_or_create(
            id=1004, defaults={"name": "Other Player", "category": EveEntity.CATEGORY_CHARACTER}
        )

        # Create fleet
        self.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
        )

    def test_deduplicate_single_character_per_player(self):
        """Test deduplication with one character per player"""
        # Create participants
        p1 = FleetParticipant.objects.create(
            fleet=self.fleet, character=self.main_entity, main_character=self.main_entity
        )
        p2 = FleetParticipant.objects.create(
            fleet=self.fleet, character=self.other_entity, main_character=self.other_entity
        )

        # Deduplicate
        result = deduplicate_participants([p1, p2])

        # Should have 2 unique players
        self.assertEqual(len(result), 2)
        self.assertIn(self.main_entity.id, result)
        self.assertIn(self.other_entity.id, result)

    def test_deduplicate_multiple_alts_same_player(self):
        """Test deduplication with multiple alts from same player"""
        # Create participants (all with same main character)
        p1 = FleetParticipant.objects.create(
            fleet=self.fleet, character=self.main_entity, main_character=self.main_entity
        )
        p2 = FleetParticipant.objects.create(
            fleet=self.fleet, character=self.alt1_entity, main_character=self.main_entity
        )
        p3 = FleetParticipant.objects.create(
            fleet=self.fleet, character=self.alt2_entity, main_character=self.main_entity
        )

        # Deduplicate
        result = deduplicate_participants([p1, p2, p3])

        # Should have 1 unique player with 3 participant records
        self.assertEqual(len(result), 1)
        self.assertIn(self.main_entity.id, result)
        self.assertEqual(len(result[self.main_entity.id]["participants"]), 3)

    def test_scout_status_aggregation(self):
        """Test that scout status is aggregated (any alt = scout)"""
        # Create participants - only one marked as scout
        p1 = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.main_entity,
            main_character=self.main_entity,
            is_scout=False,
        )
        p2 = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.alt1_entity,
            main_character=self.main_entity,
            is_scout=True,  # This alt is scout
        )

        # Deduplicate
        result = deduplicate_participants([p1, p2])

        # Main character should have scout status
        self.assertTrue(result[self.main_entity.id]["is_scout"])

    def test_exclude_status_aggregation(self):
        """Test that exclude status is aggregated (any alt = excluded)"""
        # Create participants - only one excluded
        p1 = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.main_entity,
            main_character=self.main_entity,
            excluded_from_payout=False,
        )
        p2 = FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.alt1_entity,
            main_character=self.main_entity,
            excluded_from_payout=True,  # This alt is excluded
        )

        # Deduplicate
        result = deduplicate_participants([p1, p2])

        # Main character should be excluded
        self.assertTrue(result[self.main_entity.id]["excluded"])


class CalculatePayoutsWithDeduplicationTest(TestCase):
    """Test calculate_payouts with deduplication"""

    def setUp(self):
        """Set up test data"""
        # Patch minimum payout settings for tests
        self.settings_patcher = patch.object(app_settings, "AAPAYOUT_MINIMUM_PAYOUT", 1000)
        self.per_participant_patcher = patch.object(app_settings, "AAPAYOUT_MINIMUM_PER_PARTICIPANT", 1000)
        self.settings_patcher.start()
        self.per_participant_patcher.start()

        # Create test user
        self.user = User.objects.create_user(username="testuser", password="password")

        # Create characters
        self.player1_main, _ = EveEntity.objects.get_or_create(
            id=1001, defaults={"name": "Player 1 Main", "category": EveEntity.CATEGORY_CHARACTER}
        )
        self.player1_alt, _ = EveEntity.objects.get_or_create(
            id=1002, defaults={"name": "Player 1 Alt", "category": EveEntity.CATEGORY_CHARACTER}
        )
        self.player2_main, _ = EveEntity.objects.get_or_create(
            id=1003, defaults={"name": "Player 2 Main", "category": EveEntity.CATEGORY_CHARACTER}
        )

        # Create fleet
        self.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
        )

        # Create loot pool
        self.loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            total_value=Decimal("100000000.00"),  # 100M ISK
            corp_share_percentage=Decimal("10.00"),
        )

    def tearDown(self):
        """Stop patching settings"""
        self.settings_patcher.stop()
        self.per_participant_patcher.stop()

    def test_payout_calculation_with_deduplication(self):
        """Test that payouts use deduplication (one per player)"""
        # Create participants - Player 1 has 2 characters, Player 2 has 1
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.player1_main,
            main_character=self.player1_main,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.player1_alt,
            main_character=self.player1_main,  # Same main as above
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.player2_main,
            main_character=self.player2_main,
        )

        # Calculate payouts
        payouts = calculate_payouts(self.loot_pool)

        # Should have 2 payouts (one per unique player), not 3
        self.assertEqual(len(payouts), 2)

        # Corp share: 10M, Participant pool: 90M, Split by 2: 45M each
        expected_amount = Decimal("45000000.00")
        self.assertEqual(payouts[0]["amount"], expected_amount)
        self.assertEqual(payouts[1]["amount"], expected_amount)

    def test_excluded_participants_not_paid(self):
        """Test that excluded participants receive no payout"""
        # Create participants
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.player1_main,
            main_character=self.player1_main,
            excluded_from_payout=False,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.player2_main,
            main_character=self.player2_main,
            excluded_from_payout=True,  # This player is excluded
        )

        # Calculate payouts
        payouts = calculate_payouts(self.loot_pool)

        # Should have 1 payout (excluded player gets nothing)
        self.assertEqual(len(payouts), 1)

        # Only player gets all participant share
        # Corp: 10M, Participant: 90M, all to player 1
        expected_amount = Decimal("90000000.00")
        self.assertEqual(payouts[0]["amount"], expected_amount)
        self.assertEqual(payouts[0]["character"].id, self.player1_main.id)

    def test_payout_includes_alt_character_list(self):
        """Test that payout data includes list of alt characters"""
        # Create participants - Player 1 has main + 2 alts
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.player1_main,
            main_character=self.player1_main,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.player1_alt,
            main_character=self.player1_main,
        )

        # Calculate payouts
        payouts = calculate_payouts(self.loot_pool)

        # Should have alt_characters field
        self.assertIn("alt_characters", payouts[0])
        self.assertEqual(len(payouts[0]["alt_characters"]), 2)

    def test_payout_with_no_eligible_participants(self):
        """Test payout calculation when all participants excluded"""
        # Create participants - all excluded
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.player1_main,
            main_character=self.player1_main,
            excluded_from_payout=True,
        )

        # Calculate payouts
        payouts = calculate_payouts(self.loot_pool)

        # Should have no payouts
        self.assertEqual(len(payouts), 0)


class DeduplicationIntegrationTest(TestCase):
    """Integration tests for deduplication workflow"""

    def setUp(self):
        """Set up test data"""
        # Patch minimum payout settings for tests
        self.settings_patcher = patch.object(app_settings, "AAPAYOUT_MINIMUM_PAYOUT", 1000)
        self.per_participant_patcher = patch.object(app_settings, "AAPAYOUT_MINIMUM_PER_PARTICIPANT", 1000)
        self.settings_patcher.start()
        self.per_participant_patcher.start()

        # Create test user
        self.user = User.objects.create_user(username="testuser", password="password")

        # Create characters for Player 1 (2 chars)
        self.p1_main, _ = EveEntity.objects.get_or_create(
            id=1001, defaults={"name": "P1 Main", "category": EveEntity.CATEGORY_CHARACTER}
        )
        self.p1_alt, _ = EveEntity.objects.get_or_create(
            id=1002, defaults={"name": "P1 Alt", "category": EveEntity.CATEGORY_CHARACTER}
        )

        # Create characters for Player 2 (3 chars)
        self.p2_main, _ = EveEntity.objects.get_or_create(
            id=2001, defaults={"name": "P2 Main", "category": EveEntity.CATEGORY_CHARACTER}
        )
        self.p2_alt1, _ = EveEntity.objects.get_or_create(
            id=2002, defaults={"name": "P2 Alt1", "category": EveEntity.CATEGORY_CHARACTER}
        )
        self.p2_alt2, _ = EveEntity.objects.get_or_create(
            id=2003, defaults={"name": "P2 Alt2", "category": EveEntity.CATEGORY_CHARACTER}
        )

        # Create fleet
        self.fleet = Fleet.objects.create(
            name="Test Fleet",
            fleet_commander=self.user,
            fleet_time=timezone.now(),
        )

    def tearDown(self):
        """Stop patching settings"""
        self.settings_patcher.stop()
        self.per_participant_patcher.stop()

    def test_multi_boxing_scenario(self):
        """
        Test realistic scenario:
        - Player 1 brings 2 characters
        - Player 2 brings 3 characters
        - Total: 5 characters, but only 2 payouts
        """
        # Create loot pool
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            total_value=Decimal("200000000.00"),  # 200M ISK
            corp_share_percentage=Decimal("10.00"),
        )

        # Player 1 participants
        FleetParticipant.objects.create(fleet=self.fleet, character=self.p1_main, main_character=self.p1_main)
        FleetParticipant.objects.create(fleet=self.fleet, character=self.p1_alt, main_character=self.p1_main)

        # Player 2 participants
        FleetParticipant.objects.create(fleet=self.fleet, character=self.p2_main, main_character=self.p2_main)
        FleetParticipant.objects.create(fleet=self.fleet, character=self.p2_alt1, main_character=self.p2_main)
        FleetParticipant.objects.create(fleet=self.fleet, character=self.p2_alt2, main_character=self.p2_main)

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Verify counts
        self.assertEqual(len(payouts), 2, "Should have 2 payouts (one per player)")
        self.assertEqual(self.fleet.participants.count(), 5, "Should have 5 participant records")

        # Verify amounts
        # Corp: 20M, Participant pool: 180M, Split by 2: 90M each
        for payout in payouts:
            self.assertEqual(payout["amount"], Decimal("90000000.00"))

    def test_scout_and_exclude_combination(self):
        """
        Test scenario with scout and exclude:
        - Player 1: 2 chars, one is scout
        - Player 2: 1 char, excluded
        - Player 3: 1 char, regular
        """
        # Create Player 3
        p3_main, _ = EveEntity.objects.get_or_create(
            id=3001, defaults={"name": "P3 Main", "category": EveEntity.CATEGORY_CHARACTER}
        )

        # Create loot pool
        loot_pool = LootPool.objects.create(
            fleet=self.fleet,
            name="Test Loot",
            total_value=Decimal("100000000.00"),  # 100M ISK
            corp_share_percentage=Decimal("10.00"),
        )

        # Player 1 - has scout alt
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.p1_main,
            main_character=self.p1_main,
            is_scout=False,
        )
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.p1_alt,
            main_character=self.p1_main,
            is_scout=True,  # Scout!
        )

        # Player 2 - excluded
        FleetParticipant.objects.create(
            fleet=self.fleet,
            character=self.p2_main,
            main_character=self.p2_main,
            excluded_from_payout=True,
        )

        # Player 3 - regular
        FleetParticipant.objects.create(fleet=self.fleet, character=p3_main, main_character=p3_main)

        # Calculate payouts
        payouts = calculate_payouts(loot_pool)

        # Should have 2 payouts (Player 2 excluded)
        self.assertEqual(len(payouts), 2)

        # Find Player 1's payout
        p1_payout = next(p for p in payouts if p["character"].id == self.p1_main.id)

        # Verify Player 1 has scout status (from alt)
        self.assertTrue(p1_payout["is_scout"])

        # Verify Player 2 not in payouts
        p2_payout = [p for p in payouts if p["character"].id == self.p2_main.id]
        self.assertEqual(len(p2_payout), 0)
