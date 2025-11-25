"""
ESI Wallet Service

Handles ESI wallet journal integration for payment verification
"""

# Standard Library
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

# Django
from django.utils import timezone

# Alliance Auth
from esi.clients import EsiClientProvider
from esi.models import Token

logger = logging.getLogger(__name__)

# Initialize ESI client
esi = EsiClientProvider()


class ESIWalletService:
    """Service for interacting with ESI Wallet endpoints"""

    @staticmethod
    def get_wallet_journal(character_id: int, token: Token, max_pages: int = 10) -> Optional[List[Dict]]:
        """
        Get wallet journal entries from ESI

        Args:
            character_id: EVE character ID
            token: ESI token with esi-wallet.read_character_wallet.v1 scope
            max_pages: Maximum number of pages to fetch (250 entries per page)

        Returns:
            List of journal entry dicts or None if error

        Example journal entry:
        {
            'id': 12345678901,
            'date': '2025-10-28T12:00:00Z',
            'ref_type': 'player_donation',  # ISK transfer
            'first_party_id': 98765432,     # Sender
            'second_party_id': 12345678,    # Recipient
            'amount': -1000000.00,          # Negative for sender
            'balance': 50000000.00,
            'description': 'Fleet payout',
            'tax': 0.0
        }
        """
        required_scope = "esi-wallet.read_character_wallet.v1"

        # Validate token has required scope
        if not token.has_scope(required_scope):
            error_msg = f"Token does not have required scope: {required_scope}"
            logger.error(error_msg)
            return None

        try:
            all_entries = []
            page = 1

            while page <= max_pages:
                result = esi.client.Wallet.get_characters_character_id_wallet_journal(
                    character_id=character_id, token=token.valid_access_token(), page=page
                ).results()

                if not result or len(result) == 0:
                    # No more pages
                    break

                all_entries.extend(result)
                page += 1

            logger.info(
                f"Fetched {len(all_entries)} wallet journal entries for "
                f"character ID {character_id} ({page - 1} pages)"
            )
            return all_entries

        except Exception as e:
            logger.error(f"Failed to fetch wallet journal for character ID {character_id}: {e}")
            return None

    @staticmethod
    def match_payout_to_journal(
        payout_amount: Decimal, recipient_character_id: int, journal_entries: List[Dict], time_window_hours: int = 24
    ) -> Optional[Dict]:
        """
        Match a payout to a wallet journal entry

        Matching criteria:
        1. ref_type == 'player_donation' (ISK transfer)
        2. second_party_id == recipient character ID
        3. amount matches payout amount (absolute value)
        4. date within time window

        Args:
            payout_amount: Payout amount to match
            recipient_character_id: Recipient character ID
            journal_entries: List of journal entries from ESI
            time_window_hours: Time window in hours to search

        Returns:
            Matched journal entry dict or None if no match
        """
        cutoff_time = timezone.now() - timedelta(hours=time_window_hours)

        for entry in journal_entries:
            # Parse entry date
            # Third Party
            from dateutil import parser as date_parser

            try:
                entry_date = date_parser.parse(entry.get("date", ""))
                # Make timezone aware if needed
                if timezone.is_naive(entry_date):
                    entry_date = timezone.make_aware(entry_date)
            except Exception as e:
                logger.warning(f"Failed to parse entry date: {e}")
                continue

            # Skip old entries
            if entry_date < cutoff_time:
                continue

            # Check if this is an ISK transfer to the right person for the right amount
            ref_type = entry.get("ref_type")
            second_party = entry.get("second_party_id")
            amount = abs(Decimal(str(entry.get("amount", 0))))

            if ref_type == "player_donation" and second_party == recipient_character_id and amount == payout_amount:
                logger.info(
                    f"Matched payout {payout_amount} ISK to {recipient_character_id} "
                    f"with journal entry {entry.get('id')}"
                )
                return entry

        # No match found
        return None

    @classmethod
    def verify_payouts(
        cls, payouts: List, fc_character_id: int, token: Token, time_window_hours: int = 24
    ) -> Tuple[int, int, List[str]]:
        """
        Verify multiple payouts against wallet journal

        Args:
            payouts: List of Payout model instances
            fc_character_id: FC character ID (who sent the payments)
            token: ESI token with wallet journal scope
            time_window_hours: Time window to search

        Returns:
            Tuple of (verified_count, pending_count, errors)
            - verified_count: Number of payouts successfully verified
            - pending_count: Number of payouts still pending
            - errors: List of error messages
        """
        errors = []

        # CRITICAL: Log which character's wallet we're checking (should be FC, NOT payee)
        logger.info(
            f"Starting payment verification - checking FC character ID {fc_character_id}'s wallet journal "
            f"(NOT payee wallets). Token character: {token.character_id}, Token user: {token.user}"
        )

        # Validate that token matches the FC character
        if token.character_id != fc_character_id:
            error_msg = (
                f"Token mismatch! Token is for character {token.character_id} "
                f"but trying to check wallet for character {fc_character_id}. "
                f"ESI requires the token to match the character being queried."
            )
            logger.error(error_msg)
            errors.append(error_msg)
            return 0, len(payouts), errors

        # Fetch wallet journal FROM THE FC'S WALLET
        logger.info(f"Fetching wallet journal from FC character {fc_character_id} (the person who made payments)")
        journal_entries = cls.get_wallet_journal(fc_character_id, token)

        if journal_entries is None:
            error_msg = f"Failed to fetch wallet journal from ESI for FC character {fc_character_id}"
            logger.error(error_msg)
            errors.append(error_msg)
            return 0, len(payouts), errors

        if len(journal_entries) == 0:
            error_msg = f"No wallet journal entries found for FC character {fc_character_id}"
            logger.warning(error_msg)
            errors.append(error_msg)
            return 0, len(payouts), errors

        logger.info(f"Retrieved {len(journal_entries)} journal entries from FC character {fc_character_id}'s wallet")

        verified_count = 0
        pending_count = 0

        # Match each payout
        for payout in payouts:
            logger.info(
                f"Checking payout {payout.id}: {payout.amount} ISK to recipient {payout.recipient.name} "
                f"(recipient ID: {payout.recipient.id}). Looking for payment FROM FC {fc_character_id} "
                f"TO recipient {payout.recipient.id}"
            )

            match = cls.match_payout_to_journal(
                payout_amount=payout.amount,
                recipient_character_id=payout.recipient.id,
                journal_entries=journal_entries,
                time_window_hours=time_window_hours,
            )

            if match:
                # Mark payout as verified
                payout.status = "paid"
                payout.verified = True
                payout.verified_at = timezone.now()
                payout.transaction_reference = str(match.get("id"))
                payout.paid_at = timezone.now()
                payout.save()

                verified_count += 1
                logger.info(
                    f"✓ Verified payout {payout.id}: {payout.amount} ISK to {payout.recipient.name} "
                    f"(matched journal entry {match.get('id')})"
                )
            else:
                pending_count += 1
                logger.warning(
                    f"✗ No match found for payout {payout.id}: {payout.amount} ISK to {payout.recipient.name}. "
                    f"Could not find matching transfer in FC {fc_character_id}'s wallet journal."
                )

        logger.info(
            f"Verification complete for FC {fc_character_id}: "
            f"{verified_count} verified, {pending_count} pending out of {len(payouts)} total payouts"
        )

        return verified_count, pending_count, errors


# Convenience instance
esi_wallet_service = ESIWalletService()
