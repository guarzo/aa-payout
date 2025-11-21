"""
Janice API Service

Handles interaction with the Janice API for EVE Online item appraisals.
Documentation: https://janice.e-351.com/api/rest/docs/index.html
"""

# Standard Library
import logging
import re
from decimal import Decimal
from typing import Dict

# Third Party
import requests

# Django
from django.core.cache import cache
from django.utils import timezone

# AA Payout
from aapayout import app_settings

logger = logging.getLogger(__name__)

JANICE_API_URL = "https://janice.e-351.com/api/rest/v2"


def normalize_loot_text(loot_text: str) -> str:
    """
    Normalize loot text to ensure proper formatting for Janice API.

    EVE client copy format uses tabs between item name and quantity (e.g., "Orca\t2").
    Users may manually type space-separated input (e.g., "Orca 2").
    This function converts space-separated format to tab-separated.

    Args:
        loot_text: Raw loot text (may be space or tab separated)

    Returns:
        Normalized loot text with tab separators
    """
    lines = []
    for line in loot_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # If line already has a tab, it's already in EVE format - keep as-is
        if "\t" in line:
            lines.append(line)
            continue

        # Try to extract item name and quantity from space-separated format
        # Pattern: "Item Name 123" or "Item Name 1,234" or "Item Name 1.234"
        # The quantity is always at the end and is numeric (possibly with , or . separators)
        match = re.match(r"^(.+?)\s+(\d[\d,\.]*)\s*$", line)
        if match:
            item_name = match.group(1).strip()
            quantity = match.group(2).replace(",", "").replace(".", "")
            lines.append(f"{item_name}\t{quantity}")
            logger.debug(f"[Janice] Normalized '{line}' -> '{item_name}\\t{quantity}'")
        else:
            # No quantity found, assume quantity of 1
            lines.append(f"{line}\t1")
            logger.debug(f"[Janice] No quantity found in '{line}', defaulting to 1")

    return "\n".join(lines)


class JaniceAPIError(Exception):
    """Custom exception for Janice API errors"""

    pass


class JaniceService:
    """Service for interacting with Janice API"""

    @staticmethod
    def appraise(loot_text: str) -> Dict:
        """
        Appraise loot via Janice API

        Args:
            loot_text: Raw loot paste from EVE client

        Returns:
            Dict with 'items' list and 'metadata'

        Raises:
            JaniceAPIError: If API request fails
        """
        if not loot_text or not loot_text.strip():
            raise JaniceAPIError("Loot text cannot be empty")

        if not app_settings.AAPAYOUT_JANICE_API_KEY:
            raise JaniceAPIError("Janice API key not configured. " "Please set AAPAYOUT_JANICE_API_KEY in settings.")

        # Normalize loot text to ensure proper tab-separated format
        normalized_text = normalize_loot_text(loot_text)
        logger.debug(f"[Janice] Normalized loot text:\n{normalized_text}")

        # Parse quantities from the normalized input (API doesn't return quantities)
        input_quantities = {}
        for line in normalized_text.strip().splitlines():
            if "\t" in line:
                parts = line.split("\t", 1)
                item_name = parts[0].strip()
                try:
                    quantity = int(parts[1].strip()) if len(parts) > 1 else 1
                except ValueError:
                    quantity = 1
                # Store by lowercase name for case-insensitive matching
                input_quantities[item_name.lower()] = {
                    "original_name": item_name,
                    "quantity": quantity,
                }
        logger.info(f"[Janice] Parsed {len(input_quantities)} items with quantities from input")

        # Check cache first (cache by hash of normalized loot text)
        cache_key = f"janice_appraisal_{hash(normalized_text)}"
        cached = cache.get(cache_key)
        if cached:
            logger.info("Returning cached Janice appraisal")
            return cached

        # Make API request
        url = f"{JANICE_API_URL}/pricer"
        headers = {
            "X-ApiKey": app_settings.AAPAYOUT_JANICE_API_KEY,
            "Content-Type": "text/plain",
        }
        params = {"market": app_settings.AAPAYOUT_JANICE_MARKET}

        try:
            logger.info(
                f"[Janice] Calling Janice API for {len(normalized_text.splitlines())} lines "
                f"(market: {app_settings.AAPAYOUT_JANICE_MARKET}, "
                f"price_type: {app_settings.AAPAYOUT_JANICE_PRICE_TYPE})"
            )
            logger.info(f"[Janice] API URL: {url}")
            logger.info(f"[Janice] Sending loot text: {repr(normalized_text[:500])}")

            response = requests.post(
                url,
                headers=headers,
                params=params,
                data=normalized_text.encode("utf-8"),
                timeout=app_settings.AAPAYOUT_JANICE_TIMEOUT,
            )

            logger.info(f"[Janice] API response status: {response.status_code}")

            # Check for errors
            if response.status_code == 401:
                logger.error("[Janice] Invalid API key (401 Unauthorized)")
                raise JaniceAPIError("Invalid Janice API key")
            elif response.status_code == 429:
                logger.error("[Janice] Rate limit exceeded (429)")
                raise JaniceAPIError("Janice API rate limit exceeded")
            elif response.status_code == 400:
                # Bad request - log response body for debugging
                try:
                    error_body = response.text
                    logger.error(f"[Janice] Bad Request (400): {error_body}")
                    raise JaniceAPIError(f"Invalid loot format or API request. Janice returned: {error_body}")
                except Exception:
                    logger.error("[Janice] Bad Request (400) with no response body")
                    raise JaniceAPIError("Invalid loot format or API request")
            elif response.status_code >= 500:
                logger.error(f"[Janice] Server error: {response.status_code}")
                raise JaniceAPIError(f"Janice API server error: {response.status_code}")

            response.raise_for_status()

            # Parse response
            items_data = response.json()
            logger.info(
                f"[Janice] Received response with {len(items_data) if isinstance(items_data, list) else 0} items"
            )

            # Log first few items for debugging (helps identify quantity issues)
            if isinstance(items_data, list) and len(items_data) > 0:
                logger.info(f"[Janice] Raw API response (first 3 items): {items_data[:3]}")

            if not isinstance(items_data, list):
                logger.error(f"[Janice] Unexpected response format: {type(items_data)}")
                raise JaniceAPIError("Unexpected API response format")

            # Process response
            price_key = f"{app_settings.AAPAYOUT_JANICE_PRICE_TYPE}Price"
            processed_items = []
            total_value = Decimal("0.00")

            logger.info(f"[Janice] Processing {len(items_data)} items using price key: {price_key}")

            for item in items_data:
                try:
                    type_id = item["itemType"]["eid"]
                    name = item["itemType"]["name"]

                    # Look up quantity from our parsed input (API doesn't return quantities)
                    # Match by lowercase name for case-insensitive matching
                    input_data = input_quantities.get(name.lower())
                    if input_data:
                        quantity = input_data["quantity"]
                    else:
                        # Item wasn't in our input - this shouldn't happen normally
                        logger.warning(f"[Janice] Item '{name}' from API response not found in input, defaulting to 1")
                        quantity = 1

                    unit_price = Decimal(str(item["immediatePrices"][price_key]))
                    item_total_value = quantity * unit_price

                    logger.debug(f"[Janice] Item '{name}': qty={quantity}, unit={unit_price}, total={item_total_value}")

                    processed_items.append(
                        {
                            "type_id": type_id,
                            "name": name,
                            "quantity": quantity,
                            "unit_price": unit_price,
                            "total_value": item_total_value,
                        }
                    )

                    total_value += item_total_value

                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(f"[Janice] Failed to process item in response: {e}, item data: {item}")
                    continue

            # Build result with metadata
            result = {
                "items": processed_items,
                "metadata": {
                    "market": app_settings.AAPAYOUT_JANICE_MARKET,
                    "price_type": app_settings.AAPAYOUT_JANICE_PRICE_TYPE,
                    "total_value": total_value,
                    "item_count": len(processed_items),
                    "appraised_at": timezone.now().isoformat(),
                },
            }

            # Cache for configured hours
            cache_seconds = app_settings.AAPAYOUT_JANICE_CACHE_HOURS * 3600
            cache.set(cache_key, result, cache_seconds)
            logger.debug(f"[Janice] Cached result for {cache_seconds} seconds")

            logger.info(
                f"[Janice] Successfully appraised {len(processed_items)} items "
                f"(total value: {total_value:,.2f} ISK)"
            )

            return result

        except requests.exceptions.Timeout:
            logger.error(f"[Janice] API request timed out after {app_settings.AAPAYOUT_JANICE_TIMEOUT} seconds")
            raise JaniceAPIError(
                f"Janice API request timed out after " f"{app_settings.AAPAYOUT_JANICE_TIMEOUT} seconds"
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[Janice] Failed to connect to Janice API: {e}")
            raise JaniceAPIError("Failed to connect to Janice API. Please try again later.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Janice API request failed: {str(e)}")
            raise JaniceAPIError(f"Janice API request failed: {str(e)}")
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Invalid Janice API response format: {str(e)}")
            raise JaniceAPIError(f"Invalid Janice API response: {str(e)}")

    @staticmethod
    def get_appraisal_url(code: str) -> str:
        """
        Generate link to Janice appraisal page

        Args:
            code: Janice appraisal code

        Returns:
            URL to appraisal on Janice website
        """
        return f"https://janice.e-351.com/a/{code}"

    @staticmethod
    def validate_api_key() -> bool:
        """
        Validate that the configured Janice API key works

        Returns:
            True if API key is valid, False otherwise
        """
        if not app_settings.AAPAYOUT_JANICE_API_KEY:
            return False

        try:
            # Test with a simple item
            result = JaniceService.appraise("Tritanium\t1")
            return len(result.get("items", [])) > 0
        except JaniceAPIError:
            return False
