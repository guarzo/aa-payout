"""
Janice API Service

Handles interaction with the Janice API for EVE Online item appraisals.
Documentation: https://janice.e-351.com/api/rest/docs/index.html
"""

# Standard Library
import logging
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

        # Check cache first (cache by hash of loot text)
        cache_key = f"janice_appraisal_{hash(loot_text.strip())}"
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
                f"[Janice] Calling Janice API for {len(loot_text.splitlines())} lines "
                f"(market: {app_settings.AAPAYOUT_JANICE_MARKET}, "
                f"price_type: {app_settings.AAPAYOUT_JANICE_PRICE_TYPE})"
            )
            logger.debug(f"[Janice] API URL: {url}")
            logger.debug(f"[Janice] Loot text preview: {loot_text[:200]}")

            response = requests.post(
                url,
                headers=headers,
                params=params,
                data=loot_text.encode("utf-8"),
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
            elif response.status_code >= 500:
                logger.error(f"[Janice] Server error: {response.status_code}")
                raise JaniceAPIError(f"Janice API server error: {response.status_code}")

            response.raise_for_status()

            # Parse response
            items_data = response.json()
            logger.info(f"[Janice] Received response with {len(items_data) if isinstance(items_data, list) else 0} items")

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
                    quantity = item.get("quantity", 1)
                    unit_price = Decimal(str(item["immediatePrices"][price_key]))
                    item_total_value = quantity * unit_price

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
                f"[Janice] Successfully appraised {len(processed_items)} items " f"(total value: {total_value:,.2f} ISK)"
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
