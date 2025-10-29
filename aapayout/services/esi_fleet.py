"""
ESI Fleet Service

Handles ESI fleet composition imports
"""

# Standard Library
import logging
from typing import Dict, List, Optional, Tuple

# Third Party
from bravado.exception import HTTPNotFound

# Alliance Auth
from esi.clients import EsiClientProvider
from esi.models import Token

# Alliance Auth (External Libs)
from eveuniverse.models import EveEntity

logger = logging.getLogger(__name__)

# Initialize ESI client
esi = EsiClientProvider()


class ESIFleetService:
    """Service for interacting with ESI Fleet endpoints"""

    @staticmethod
    def get_character_fleet_id(character_id: int, token: Token) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """
        Get the fleet ID that a character is currently in

        Args:
            character_id: EVE character ID
            token: ESI token with esi-fleets.read_fleet.v1 scope

        Returns:
            Tuple of (fleet_id, role, error_message)
            - fleet_id: Fleet ID if character is in a fleet
            - role: Character's fleet role ('fleet_commander', 'wing_commander', 'squad_commander', 'squad_member')
            - error_message: Error message if failed, None if success

        Example response from ESI:
        {
            'fleet_id': 1234567890,
            'role': 'fleet_commander',
            'squad_id': -1,
            'wing_id': -1
        }
        """
        try:
            logger.info(f"[ESI] Checking if character {character_id} is in a fleet")

            result = esi.client.Fleets.get_characters_character_id_fleet(
                character_id=character_id, token=token.valid_access_token()
            ).results()

            logger.debug(f"[ESI] Fleet check result: {result}")

            fleet_id = result.get("fleet_id")
            role = result.get("role", "squad_member")

            if fleet_id:
                logger.info(f"[ESI] Character {character_id} is in fleet {fleet_id} with role '{role}'")
                return fleet_id, role, None
            else:
                logger.info(f"[ESI] Character {character_id} is not in a fleet")
                return None, None, "Character is not in a fleet"

        except HTTPNotFound:
            # This is expected when character is not in a fleet - not an error
            logger.info(f"[ESI] Character {character_id} is not in a fleet (404 from ESI)")
            return None, None, "Character is not in a fleet"

        except Exception as e:
            # Unexpected error - log at error level
            error_msg = str(e)
            logger.error(f"[ESI] Unexpected error checking fleet status for character {character_id}: {error_msg}")
            logger.exception("[ESI] Full exception details:")
            return None, None, f"Failed to check fleet status: {error_msg}"

    @staticmethod
    def get_fleet_info(fleet_id: int, token: Token) -> Optional[Dict]:
        """
        Get fleet information from ESI

        Args:
            fleet_id: ESI fleet ID
            token: ESI token with esi-fleets.read_fleet.v1 scope

        Returns:
            Dict with fleet information or None if error

        Example response:
        {
            'is_free_move': False,
            'is_registered': False,
            'is_voice_enabled': False,
            'motd': 'Fleet MOTD'
        }
        """
        try:
            result = esi.client.Fleets.get_fleets_fleet_id(
                fleet_id=fleet_id, token=token.valid_access_token()
            ).results()

            logger.info(f"Successfully fetched fleet info for fleet ID {fleet_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to fetch fleet info for fleet ID {fleet_id}: {e}")
            return None

    @staticmethod
    def get_fleet_members(fleet_id: int, token: Token) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Get all fleet members from ESI

        Args:
            fleet_id: ESI fleet ID
            token: ESI token with esi-fleets.read_fleet.v1 scope

        Returns:
            Tuple of (member_list, error_message)
            - member_list: List of fleet member dicts or None if error
            - error_message: String error message if failed, None if success

        Example response:
        (
            [
                {
                    'character_id': 12345678,
                    'join_time': '2025-10-28T12:00:00Z',
                    'role': 'squad_commander',
                    'role_name': 'Squad Commander',
                    'ship_type_id': 587,  # Ship type ID
                    'solar_system_id': 30000142,
                    'squad_id': 1,
                    'station_id': 60003760,
                    'takes_fleet_warp': True,
                    'wing_id': 1
                },
                ...
            ],
            None
        )
        """
        try:
            logger.info(f"[ESI] Fetching fleet members for fleet ID {fleet_id}")
            logger.debug(
                f"[ESI] Token character: {token.character_name if hasattr(token, 'character_name') else 'unknown'}"
            )

            result = esi.client.Fleets.get_fleets_fleet_id_members(
                fleet_id=fleet_id, token=token.valid_access_token()
            ).results()

            logger.info(f"[ESI] Successfully fetched {len(result)} fleet members for fleet ID {fleet_id}")
            return result, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[ESI] Failed to fetch fleet members for fleet ID {fleet_id}: {error_msg}")
            logger.exception("[ESI] Full exception details:")

            # Provide helpful hint for common 404 error (insufficient permissions)
            if "404" in error_msg and ("does not exist" in error_msg or "don't have access" in error_msg):
                return None, (
                    f"ESI API error: {error_msg}\n\n"
                    "This usually means you need to be the Fleet Commander (Fleet Boss) to import fleet members. "
                    "Please verify you have the Fleet Boss role in EVE Online."
                )

            return None, f"ESI API error: {error_msg}"

    @staticmethod
    def get_or_create_character_entity(character_id: int) -> Optional[EveEntity]:
        """
        Get or create EveEntity for a character from ESI

        Args:
            character_id: EVE character ID

        Returns:
            EveEntity instance or None if error
        """
        try:
            # Use eveuniverse's get_or_create_esi method to fetch from ESI if needed
            entity, created = EveEntity.objects.get_or_create_esi(id=character_id)

            if created:
                logger.info(f"Created new EveEntity for character ID {character_id}")
            else:
                logger.debug(f"Found existing EveEntity for character ID {character_id}")

            return entity

        except Exception as e:
            logger.error(f"Failed to get or create entity for character ID {character_id}: {e}")
            return None

    @classmethod
    def import_fleet_composition(cls, fleet_id: int, token: Token) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Import fleet composition from ESI

        This is the main entry point for fleet imports. It fetches the fleet
        members from ESI and returns the data for processing.

        Args:
            fleet_id: ESI fleet ID
            token: ESI token with required scope

        Returns:
            Tuple of (member_data, error_message)
            - member_data: List of member dicts with EveEntity instances
            - error_message: String error message if failed, None if success

        Example success return:
        (
            [
                {
                    'character_id': 12345678,
                    'character_entity': EveEntity instance,
                    'join_time': datetime,
                    'ship_type_id': 587,
                    ...
                },
                ...
            ],
            None
        )

        Example error return:
        (None, "Failed to fetch fleet members from ESI")
        """
        logger.info(f"[ESI] Starting fleet composition import for fleet ID {fleet_id}")

        # Fetch fleet members from ESI
        raw_members, error = cls.get_fleet_members(fleet_id, token)

        if error:
            logger.error(f"[ESI] get_fleet_members failed for fleet ID {fleet_id}: {error}")
            return None, error

        if raw_members is None or len(raw_members) == 0:
            logger.warning(f"[ESI] Fleet {fleet_id} is empty (no members found)")
            return None, "Fleet is empty (no members found)"

        logger.info(f"[ESI] Retrieved {len(raw_members)} raw members from ESI")

        # Process members and create/fetch character entities
        processed_members = []
        logger.info(f"[ESI] Processing {len(raw_members)} fleet members")

        for member in raw_members:
            character_id = member.get("character_id")

            if not character_id:
                logger.warning(f"Skipping member with no character_id: {member}")
                continue

            # Get or create character entity
            character_entity = cls.get_or_create_character_entity(character_id)

            if not character_entity:
                logger.warning(f"Skipping character ID {character_id} - " f"failed to create entity")
                continue

            # Add entity to member data
            member_data = member.copy()
            member_data["character_entity"] = character_entity

            # Convert join_time to datetime if needed
            # Third Party
            from dateutil import parser as date_parser

            if isinstance(member.get("join_time"), str):
                try:
                    member_data["join_time"] = date_parser.parse(member["join_time"])
                except Exception as e:
                    logger.warning(f"Failed to parse join_time for character " f"{character_id}: {e}")

            processed_members.append(member_data)

        logger.info(f"[ESI] Processed {len(processed_members)} out of {len(raw_members)} fleet members")
        logger.info("[ESI] Fleet composition import completed successfully")

        return processed_members, None


# Convenience instance
esi_fleet_service = ESIFleetService()


# ==============================================================================
# Phase 2 Week 6: Express Mode - ESI UI Window Opening
# ==============================================================================


class ESIUIService:
    """Service for ESI UI interactions (opening windows in EVE client)"""

    @staticmethod
    def open_character_window(character_id: int, token) -> Tuple[bool, Optional[str]]:
        """
        Open a character information window in the EVE client

        This uses the ESI UI endpoint to open a character window. The user must
        have the EVE client running and logged in with the character that owns
        the token.

        Args:
            character_id: EVE character ID to open window for
            token: ESI token with esi-ui.open_window.v1 scope (already validated by view)

        Returns:
            Tuple of (success, error_message)
            - success: True if window opened successfully
            - error_message: String error message if failed, None if success

        Example:
            success, error = ESIUIService.open_character_window(12345678, token)
            if success:
                print("Window opened!")
            else:
                print(f"Failed: {error}")
        """
        try:
            # Token scope is already validated by the view before calling this service
            # Open character window via ESI
            esi.client.User_Interface.post_ui_openwindow_information(
                target_id=character_id, token=token.valid_access_token()
            ).results()

            logger.info(f"Successfully opened character window for ID {character_id}")
            return True, None

        except Exception as e:
            error_msg = f"Failed to open character window for ID {character_id}: {e}"
            logger.error(error_msg)
            return False, str(e)


# Convenience instances
esi_ui_service = ESIUIService()
