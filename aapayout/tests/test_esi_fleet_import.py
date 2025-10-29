"""
Tests for ESI Fleet Import

Phase 2: Week 3-4 - ESI Fleet Import
"""

# Standard Library
from unittest.mock import MagicMock, patch

# Django
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

# Alliance Auth (External Libs)
from eveuniverse.models import EveEntity

# AA Payout
from aapayout import constants
from aapayout.models import ESIFleetImport, Fleet, FleetParticipant
from aapayout.services.esi_fleet import esi_fleet_service


class ESIFleetServiceTests(TestCase):
    """Tests for ESI Fleet Service"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data"""
        # Create test entities (no ESI calls needed for simple creates)
        cls.char1 = EveEntity.objects.create(
            id=1001,
            name="Test Character 1",
        )
        cls.char2 = EveEntity.objects.create(
            id=1002,
            name="Test Character 2",
        )
        cls.char3 = EveEntity.objects.create(
            id=1003,
            name="Test Character 3",
        )

    def test_get_or_create_character_entity_existing(self):
        """Test getting an existing character entity"""
        entity = esi_fleet_service.get_or_create_character_entity(self.char1.id)

        self.assertIsNotNone(entity)
        self.assertEqual(entity.id, self.char1.id)
        self.assertEqual(entity.name, "Test Character 1")

    @patch("aapayout.services.esi_fleet.EveEntity.objects.get_or_create_esi")
    def test_get_or_create_character_entity_new(self, mock_get_or_create):
        """Test creating a new character entity from ESI"""
        # Mock ESI response - create a mock object instead of actual EveEntity
        new_char = MagicMock(spec=EveEntity)
        new_char.id = 9999
        new_char.name = "New Character"
        mock_get_or_create.return_value = (new_char, True)

        entity = esi_fleet_service.get_or_create_character_entity(9999)

        self.assertIsNotNone(entity)
        self.assertEqual(entity.id, 9999)
        self.assertEqual(entity.name, "New Character")
        mock_get_or_create.assert_called_once_with(id=9999)

    @patch("aapayout.services.esi_fleet.esi")
    def test_get_fleet_members_success(self, mock_esi):
        """Test successfully getting fleet members from ESI"""
        # Mock ESI response - the ESI call returns an object with a results() method
        expected_data = [
            {
                "character_id": 1001,
                "join_time": "2025-10-28T12:00:00Z",
                "role": "squad_member",
                "ship_type_id": 587,
            },
            {
                "character_id": 1002,
                "join_time": "2025-10-28T12:05:00Z",
                "role": "squad_commander",
                "ship_type_id": 11978,
            },
        ]

        # Create mock ESI result object
        mock_result = MagicMock()
        mock_result.results.return_value = expected_data
        mock_esi.client.Fleets.get_fleets_fleet_id_members.return_value = mock_result

        # Create mock token
        mock_token = MagicMock()
        mock_token.valid_access_token.return_value = "test_token"

        result, error = esi_fleet_service.get_fleet_members(123456, mock_token)

        self.assertIsNone(error)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["character_id"], 1001)
        self.assertEqual(result[1]["character_id"], 1002)

    @patch("aapayout.services.esi_fleet.esi")
    def test_get_fleet_members_error(self, mock_esi):
        """Test error handling when ESI call fails"""
        # Mock ESI error - the ESI call raises an exception
        mock_result = MagicMock()
        mock_result.results.side_effect = Exception("Test error message")
        mock_esi.client.Fleets.get_fleets_fleet_id_members.return_value = mock_result

        mock_token = MagicMock()
        mock_token.valid_access_token.return_value = "test_token"

        result, error = esi_fleet_service.get_fleet_members(123456, mock_token)

        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("ESI API error", error)
        self.assertIn("Test error message", error)

    @patch("aapayout.services.esi_fleet.ESIFleetService.get_fleet_members")
    @patch("aapayout.services.esi_fleet.ESIFleetService.get_or_create_character_entity")
    def test_import_fleet_composition_success(self, mock_get_char, mock_get_members):
        """Test successful fleet composition import"""
        # Mock fleet members from ESI - now returns tuple (data, error)
        mock_get_members.return_value = (
            [
                {
                    "character_id": 1001,
                    "join_time": "2025-10-28T12:00:00Z",
                    "role": "squad_member",
                },
                {
                    "character_id": 1002,
                    "join_time": "2025-10-28T12:05:00Z",
                    "role": "squad_commander",
                },
            ],
            None,  # No error
        )

        # Mock character entity creation
        def get_char_side_effect(char_id):
            if char_id == 1001:
                return self.char1
            elif char_id == 1002:
                return self.char2
            return None

        mock_get_char.side_effect = get_char_side_effect

        # Create mock token
        mock_token = MagicMock()
        mock_token.has_scope.return_value = True
        mock_token.valid_access_token.return_value = "test_token"

        # Import fleet
        members, error = esi_fleet_service.import_fleet_composition(123456, mock_token)

        self.assertIsNone(error)
        self.assertIsNotNone(members)
        self.assertEqual(len(members), 2)
        self.assertEqual(members[0]["character_entity"], self.char1)
        self.assertEqual(members[1]["character_entity"], self.char2)


class ESIFleetImportModelTests(TestCase):
    """Tests for ESIFleetImport model"""

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

    def test_create_esi_fleet_import(self):
        """Test creating an ESI fleet import record"""
        esi_import = ESIFleetImport.objects.create(
            fleet=self.fleet,
            esi_fleet_id=123456789,
            imported_by=self.user,
            characters_found=10,
            characters_added=8,
            characters_skipped=2,
            unique_players=7,
        )

        self.assertEqual(esi_import.fleet, self.fleet)
        self.assertEqual(esi_import.esi_fleet_id, 123456789)
        self.assertEqual(esi_import.characters_found, 10)
        self.assertEqual(esi_import.characters_added, 8)
        self.assertEqual(esi_import.unique_players, 7)

    def test_esi_fleet_import_str(self):
        """Test string representation"""
        esi_import = ESIFleetImport.objects.create(
            fleet=self.fleet,
            esi_fleet_id=123456789,
            imported_by=self.user,
        )

        str_repr = str(esi_import)
        self.assertIn("Test Fleet", str_repr)
        self.assertIn(esi_import.imported_at.strftime("%Y-%m-%d"), str_repr)


class ESIFleetImportIntegrationTests(TestCase):
    """Integration tests for ESI fleet import workflow"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data"""
        cls.user = User.objects.create_user(username="fc_user", password="testpass")

        cls.fleet = Fleet.objects.create(
            name="Integration Test Fleet",
            fleet_commander=cls.user,
            fleet_time=timezone.now(),
            status=constants.FLEET_STATUS_ACTIVE,
        )

        # Create test characters (no ESI calls needed for simple creates)
        cls.char1 = EveEntity.objects.create(
            id=2001,
            name="Pilot Alpha",
        )
        cls.char2 = EveEntity.objects.create(
            id=2002,
            name="Pilot Bravo",
        )
        cls.char3 = EveEntity.objects.create(
            id=2003,
            name="Pilot Charlie",
        )

    @patch("aapayout.services.esi_fleet.esi_fleet_service.import_fleet_composition")
    def test_full_import_workflow(self, mock_import):
        """Test complete import workflow from ESI to participants"""
        # Mock ESI import response
        mock_import.return_value = (
            [
                {
                    "character_id": 2001,
                    "character_entity": self.char1,
                    "join_time": timezone.now(),
                },
                {
                    "character_id": 2002,
                    "character_entity": self.char2,
                    "join_time": timezone.now(),
                },
                {
                    "character_id": 2003,
                    "character_entity": self.char3,
                    "join_time": timezone.now(),
                },
            ],
            None,  # No error
        )

        # Simulate import process (from view logic)
        mock_token = MagicMock()
        member_data, error = mock_import(123456, mock_token)

        self.assertIsNone(error)
        self.assertEqual(len(member_data), 3)

        # Create ESI import record
        esi_import = ESIFleetImport.objects.create(
            fleet=self.fleet,
            esi_fleet_id=123456,
            imported_by=self.user,
            characters_found=len(member_data),
        )

        # Add participants
        characters_added = 0
        for member in member_data:
            FleetParticipant.objects.create(
                fleet=self.fleet,
                character=member["character_entity"],
                role=constants.ROLE_REGULAR,
                joined_at=member["join_time"],
            )
            characters_added += 1

        # Update import record
        esi_import.characters_added = characters_added
        esi_import.save()

        # Verify results
        self.assertEqual(esi_import.characters_added, 3)
        self.assertEqual(self.fleet.participants.count(), 3)

        participants = self.fleet.participants.all()
        self.assertEqual(participants[0].character, self.char1)
        self.assertEqual(participants[1].character, self.char2)
        self.assertEqual(participants[2].character, self.char3)
