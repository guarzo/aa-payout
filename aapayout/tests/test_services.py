"""
Tests for AA-Payout services (Janice API)
"""

# Standard Library
from unittest.mock import Mock, patch

# Django
from django.core.cache import cache
from django.test import TestCase

# AA Payout
from aapayout import app_settings
from aapayout.services.janice import JaniceAPIError, JaniceService


class JaniceServiceTest(TestCase):
    """Test Janice API service"""

    def setUp(self):
        """Clear cache and patch settings before each test"""
        cache.clear()
        # Patch app_settings directly since they're loaded at module import
        self.settings_patcher = patch.multiple(
            app_settings,
            AAPAYOUT_JANICE_API_KEY="test-api-key",
            AAPAYOUT_JANICE_MARKET=2,  # Integer market ID (2=Jita)
            AAPAYOUT_JANICE_PRICE_TYPE="buy",
            AAPAYOUT_JANICE_TIMEOUT=30,
            AAPAYOUT_JANICE_CACHE_HOURS=1,
        )
        self.settings_patcher.start()

    def tearDown(self):
        """Stop patching settings"""
        self.settings_patcher.stop()

    @patch("aapayout.services.janice.requests.post")
    def test_appraise_success(self, mock_post):
        """Test successful appraisal"""
        # Mock response matching actual Janice API format
        # Note: Janice API does NOT return quantity - we parse it from input
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "itemType": {
                    "eid": 46676,
                    "name": "Compressed Arkonor",
                },
                # No "quantity" field - real API doesn't return this
                "immediatePrices": {
                    "buyPrice": 5000.50,
                    "sellPrice": 5500.00,
                },
            },
        ]
        mock_post.return_value = mock_response

        # Test appraisal - quantity 1000 comes from input, not API response
        loot_text = "Compressed Arkonor\t1000"
        result = JaniceService.appraise(loot_text)

        # Check result
        self.assertIn("items", result)
        self.assertIn("metadata", result)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["type_id"], 46676)
        self.assertEqual(result["items"][0]["name"], "Compressed Arkonor")
        self.assertEqual(result["items"][0]["quantity"], 1000)

        # Verify API was called correctly
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args

        self.assertIn("pricer", args[0])
        self.assertEqual(kwargs["headers"]["X-ApiKey"], "test-api-key")
        self.assertEqual(kwargs["params"]["market"], 2)  # Integer market ID
        self.assertEqual(kwargs["data"], loot_text.encode("utf-8"))

    @patch("aapayout.services.janice.requests.post")
    def test_appraise_caching(self, mock_post):
        """Test that results are cached"""
        # Mock response - no quantity field (real API doesn't return it)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "itemType": {"eid": 46676, "name": "Compressed Arkonor"},
                "immediatePrices": {"buyPrice": 5000.50, "sellPrice": 5500.00},
            }
        ]
        mock_post.return_value = mock_response

        loot_text = "Compressed Arkonor\t1000"

        # First call
        result1 = JaniceService.appraise(loot_text)

        # Second call with same text
        result2 = JaniceService.appraise(loot_text)

        # API should only be called once due to caching
        mock_post.assert_called_once()

        # Results should be identical
        self.assertEqual(result1, result2)

    @patch("aapayout.services.janice.requests.post")
    def test_appraise_http_error(self, mock_post):
        """Test handling HTTP errors"""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("Server error")
        mock_post.return_value = mock_response

        loot_text = "Compressed Arkonor\t1000"

        # Should raise JaniceAPIError
        with self.assertRaises(JaniceAPIError):
            JaniceService.appraise(loot_text)

    @patch("aapayout.services.janice.requests.post")
    def test_appraise_timeout(self, mock_post):
        """Test handling timeout"""
        # Third Party
        import requests

        # Mock timeout
        mock_post.side_effect = requests.Timeout("Request timeout")

        loot_text = "Compressed Arkonor\t1000"

        # Should raise JaniceAPIError
        with self.assertRaises(JaniceAPIError):
            JaniceService.appraise(loot_text)

    @patch("aapayout.services.janice.requests.post")
    def test_appraise_invalid_json(self, mock_post):
        """Test handling invalid JSON response"""
        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = mock_response

        loot_text = "Compressed Arkonor\t1000"

        # Should raise JaniceAPIError
        with self.assertRaises(JaniceAPIError):
            JaniceService.appraise(loot_text)

    @patch("aapayout.services.janice.requests.post")
    def test_appraise_multiple_items(self, mock_post):
        """Test appraisal with multiple items"""
        # Mock response - no quantity fields (real API doesn't return them)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "itemType": {"eid": 46676, "name": "Compressed Arkonor"},
                "immediatePrices": {"buyPrice": 5000.50, "sellPrice": 5500.00},
            },
            {
                "itemType": {"eid": 46678, "name": "Compressed Bistot"},
                "immediatePrices": {"buyPrice": 3500.25, "sellPrice": 3800.00},
            },
            {
                "itemType": {"eid": 12005, "name": "Capital Armor Plates"},
                "immediatePrices": {"buyPrice": 125000.00, "sellPrice": 130000.00},
            },
        ]
        mock_post.return_value = mock_response

        loot_text = """Compressed Arkonor\t1000
Compressed Bistot\t500
Capital Armor Plates\t10"""

        result = JaniceService.appraise(loot_text)

        # Check result
        self.assertIn("items", result)
        self.assertEqual(len(result["items"]), 3)

        # Verify items
        items = result["items"]
        self.assertEqual(items[0]["name"], "Compressed Arkonor")
        self.assertEqual(items[1]["name"], "Compressed Bistot")
        self.assertEqual(items[2]["name"], "Capital Armor Plates")

    @patch("aapayout.services.janice.requests.post")
    def test_appraise_empty_response(self, mock_post):
        """Test handling empty appraisal response"""
        # Mock empty response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []  # Empty list
        mock_post.return_value = mock_response

        loot_text = "Invalid Item Name\t1000"
        result = JaniceService.appraise(loot_text)

        # Should return empty items list
        self.assertEqual(len(result["items"]), 0)

    @patch("aapayout.services.janice.requests.post")
    def test_appraise_special_characters(self, mock_post):
        """Test appraisal with special characters in item names"""
        # Mock response - no quantity field (real API doesn't return it)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "itemType": {"eid": 33470, "name": "'Augmented' Ogre"},
                "immediatePrices": {"buyPrice": 50000000.00, "sellPrice": 52000000.00},
            }
        ]
        mock_post.return_value = mock_response

        loot_text = "'Augmented' Ogre\t5"
        result = JaniceService.appraise(loot_text)

        # Check result
        self.assertEqual(result["items"][0]["name"], "'Augmented' Ogre")

    def test_appraise_cache_key_generation(self):
        """Test that different loot text generates different cache keys"""
        with patch("aapayout.services.janice.requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = []
            mock_post.return_value = mock_response

            loot_text1 = "Compressed Arkonor\t1000"
            loot_text2 = "Compressed Bistot\t500"

            # First call
            JaniceService.appraise(loot_text1)

            # Second call with different text
            JaniceService.appraise(loot_text2)

            # API should be called twice (different cache keys)
            self.assertEqual(mock_post.call_count, 2)
