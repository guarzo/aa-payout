# Janice API Integration Guide

This document describes how to integrate with the Janice API for EVE Online item appraisals.

---

## Overview

**Service**: Janice - Your friendly neighborhood space junk worth evaluator
**Website**: https://janice.e-351.com/
**GitHub**: https://github.com/E-351/janice
**Documentation**: https://janice.e-351.com/api/rest/docs/index.html (Swagger UI)

---

## API Details

### Base URL
```
https://janice.e-351.com/api/rest/v2
```

### Authentication
API requests require authentication via custom header:

```http
X-ApiKey: YOUR_API_KEY_HERE
```

**Note**: API keys must be obtained from the developer. Using shared/sample keys may result in account blocking due to traffic monitoring.

### Rate Limits
- Not publicly documented
- Traffic is monitored per API key
- For low-volume usage (< 100 requests/day), shouldn't be an issue

---

## Appraisal Endpoint

### Endpoint
```
POST /pricer?market={market}
```

### Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| market | string | Yes | Market hub to use for pricing | `jita`, `amarr`, `perimeter`, `dodixie`, `hek`, `rens` |

### Request Format

**Content-Type**: `text/plain`

**Body**: Newline-separated list of items. Each line can be:
- Item name only: `Compressed Arkonor`
- Item name with quantity: `Compressed Arkonor 1000`
- Item type ID: `22`

**Example Request Body**:
```
Compressed Arkonor	1000
Compressed Bistot	500
Salvage	250
```

**Example cURL**:
```bash
curl -X POST "https://janice.e-351.com/api/rest/v2/pricer?market=jita" \
  -H "X-ApiKey: YOUR_API_KEY" \
  -H "Content-Type: text/plain" \
  -d "Compressed Arkonor	1000
Compressed Bistot	500
Salvage	250"
```

### Response Format

**Content-Type**: `application/json`

**Structure**: Array of item objects

**Example Response**:
```json
[
  {
    "itemType": {
      "eid": 46689,
      "name": "Compressed Arkonor",
      "volume": 0.15,
      "packagedVolume": 0.15
    },
    "market": {
      "id": 60003760,
      "name": "Jita 4-4"
    },
    "immediatePrices": {
      "buyPrice": 1250.50,
      "sellPrice": 1300.75
    },
    "quantity": 1000
  },
  {
    "itemType": {
      "eid": 46676,
      "name": "Compressed Bistot",
      "volume": 0.15,
      "packagedVolume": 0.15
    },
    "market": {
      "id": 60003760,
      "name": "Jita 4-4"
    },
    "immediatePrices": {
      "buyPrice": 980.25,
      "sellPrice": 1020.80
    },
    "quantity": 500
  }
]
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `itemType.eid` | integer | EVE type ID |
| `itemType.name` | string | Item name |
| `itemType.volume` | float | Volume per unit (m³) |
| `itemType.packagedVolume` | float | Packaged volume per unit (m³) |
| `market.id` | integer | Station/structure ID |
| `market.name` | string | Market location name |
| `immediatePrices.buyPrice` | float | Immediate buy price (ISK per unit) |
| `immediatePrices.sellPrice` | float | Immediate sell price (ISK per unit) |
| `quantity` | integer | Quantity from request (if provided) |

---

## Implementation in Python

### Basic Example

```python
import requests

JANICE_API_KEY = "your_api_key_here"
JANICE_API_URL = "https://janice.e-351.com/api/rest/v2"

def appraise_loot(loot_text: str, market: str = "jita") -> dict:
    """
    Appraise loot using Janice API

    Args:
        loot_text: Newline-separated item list
        market: Market hub (jita, amarr, etc.)

    Returns:
        JSON response from Janice API
    """
    url = f"{JANICE_API_URL}/pricer"
    headers = {
        "X-ApiKey": JANICE_API_KEY,
        "Content-Type": "text/plain"
    }
    params = {"market": market}

    response = requests.post(
        url,
        headers=headers,
        params=params,
        data=loot_text.encode('utf-8')
    )
    response.raise_for_status()

    return response.json()

# Usage
loot = """Compressed Arkonor\t1000
Compressed Bistot\t500"""

result = appraise_loot(loot)

for item in result:
    name = item['itemType']['name']
    quantity = item.get('quantity', 1)
    buy_price = item['immediatePrices']['buyPrice']
    total = quantity * buy_price
    print(f"{name} x{quantity}: {total:,.2f} ISK")
```

### With Error Handling

```python
import requests
from typing import Optional, List, Dict

class JaniceAPIError(Exception):
    """Custom exception for Janice API errors"""
    pass

def appraise_loot_safe(
    loot_text: str,
    market: str = "jita",
    price_type: str = "buy"
) -> List[Dict]:
    """
    Appraise loot with error handling

    Args:
        loot_text: Newline-separated item list
        market: Market hub (jita, amarr, etc.)
        price_type: 'buy' or 'sell'

    Returns:
        List of item dictionaries with pricing

    Raises:
        JaniceAPIError: If API request fails
    """
    url = f"{JANICE_API_URL}/pricer"
    headers = {
        "X-ApiKey": JANICE_API_KEY,
        "Content-Type": "text/plain"
    }
    params = {"market": market}

    try:
        response = requests.post(
            url,
            headers=headers,
            params=params,
            data=loot_text.encode('utf-8'),
            timeout=30
        )
        response.raise_for_status()

        items = response.json()

        # Process and simplify response
        results = []
        for item in items:
            price_key = f"{price_type}Price"
            results.append({
                'type_id': item['itemType']['eid'],
                'name': item['itemType']['name'],
                'quantity': item.get('quantity', 1),
                'unit_price': item['immediatePrices'][price_key],
                'total_value': item.get('quantity', 1) * item['immediatePrices'][price_key]
            })

        return results

    except requests.exceptions.RequestException as e:
        raise JaniceAPIError(f"Failed to appraise loot: {str(e)}")
    except (KeyError, ValueError) as e:
        raise JaniceAPIError(f"Invalid API response: {str(e)}")
```

---

## Integration Points for AA-Payout

### 1. Settings Configuration

```python
# aapayout/app_settings.py

from django.conf import settings

AAPAYOUT_JANICE_API_KEY = getattr(
    settings,
    "AAPAYOUT_JANICE_API_KEY",
    ""
)

AAPAYOUT_JANICE_MARKET = getattr(
    settings,
    "AAPAYOUT_JANICE_MARKET",
    "jita"
)

AAPAYOUT_JANICE_PRICE_TYPE = getattr(
    settings,
    "AAPAYOUT_JANICE_PRICE_TYPE",
    "buy"  # or "sell"
)

AAPAYOUT_JANICE_TIMEOUT = getattr(
    settings,
    "AAPAYOUT_JANICE_TIMEOUT",
    30  # seconds
)
```

### 2. Service Module

```python
# aapayout/services/janice.py

import requests
import logging
from typing import List, Dict
from django.core.cache import cache

from aapayout import app_settings

logger = logging.getLogger(__name__)

JANICE_API_URL = "https://janice.e-351.com/api/rest/v2"

class JaniceService:
    """Service for interacting with Janice API"""

    @staticmethod
    def appraise(loot_text: str) -> List[Dict]:
        """
        Appraise loot via Janice API

        Args:
            loot_text: Raw loot paste from game

        Returns:
            List of dicts with item data and pricing
        """
        # Check cache first
        cache_key = f"janice_appraisal_{hash(loot_text)}"
        cached = cache.get(cache_key)
        if cached:
            logger.info("Returning cached Janice appraisal")
            return cached

        # Make API request
        url = f"{JANICE_API_URL}/pricer"
        headers = {
            "X-ApiKey": app_settings.AAPAYOUT_JANICE_API_KEY,
            "Content-Type": "text/plain"
        }
        params = {"market": app_settings.AAPAYOUT_JANICE_MARKET}

        try:
            response = requests.post(
                url,
                headers=headers,
                params=params,
                data=loot_text.encode('utf-8'),
                timeout=app_settings.AAPAYOUT_JANICE_TIMEOUT
            )
            response.raise_for_status()

            items = response.json()

            # Process response
            price_key = f"{app_settings.AAPAYOUT_JANICE_PRICE_TYPE}Price"
            results = []

            for item in items:
                results.append({
                    'type_id': item['itemType']['eid'],
                    'name': item['itemType']['name'],
                    'quantity': item.get('quantity', 1),
                    'unit_price': item['immediatePrices'][price_key],
                    'total_value': item.get('quantity', 1) * item['immediatePrices'][price_key]
                })

            # Cache for 1 hour
            cache.set(cache_key, results, 3600)

            logger.info(f"Appraised {len(results)} items via Janice API")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Janice API request failed: {str(e)}")
            raise
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid Janice API response: {str(e)}")
            raise
```

### 3. Celery Task (Async)

```python
# aapayout/tasks.py

from celery import shared_task
from .services.janice import JaniceService
from .models import LootPool, LootItem

@shared_task
def appraise_loot_pool(loot_pool_id: int):
    """
    Asynchronously appraise a loot pool via Janice API

    Args:
        loot_pool_id: ID of LootPool to appraise
    """
    try:
        loot_pool = LootPool.objects.get(id=loot_pool_id)

        # Get raw loot text (stored when user pasted)
        loot_text = loot_pool.raw_loot_text

        # Call Janice API
        items = JaniceService.appraise(loot_text)

        # Create LootItem records
        for item_data in items:
            LootItem.objects.create(
                loot_pool=loot_pool,
                type_id=item_data['type_id'],
                name=item_data['name'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                total_value=item_data['total_value'],
                price_source='janice'
            )

        # Update loot pool status
        loot_pool.status = 'valued'
        loot_pool.save()

    except Exception as e:
        logger.error(f"Failed to appraise loot pool {loot_pool_id}: {str(e)}")
        raise
```

---

## Configuration in local.py

Add to your Alliance Auth `local.py`:

```python
# Janice API Configuration
AAPAYOUT_JANICE_API_KEY = "your_actual_api_key_here"
AAPAYOUT_JANICE_MARKET = "jita"  # jita, amarr, perimeter, dodixie, hek, rens
AAPAYOUT_JANICE_PRICE_TYPE = "buy"  # buy or sell
AAPAYOUT_JANICE_TIMEOUT = 30  # seconds
```

---

## Notes & Considerations

1. **API Key Security**: Store API key in environment variable or secure settings, never commit to git
2. **Caching**: Cache appraisals to reduce API calls (items in same paste will have same prices)
3. **Error Handling**: Gracefully handle API failures (network, rate limits, invalid items)
4. **Fallback**: Consider having manual price override if Janice is unavailable
5. **Market Selection**: Jita is most common, but allow configuration per alliance preference
6. **Price Type**: Use buy prices (what you'd get selling immediately) for conservative estimates
7. **Quantity Parsing**: Janice handles both "Item Name" and "Item Name\tQuantity" formats
8. **Monitoring**: Log API failures and track success rate

---

## Testing

### Manual Test
Visit: https://janice.e-351.com/
Paste items and compare with API results

### Unit Test Example
```python
import pytest
from unittest.mock import patch, Mock
from aapayout.services.janice import JaniceService

@patch('aapayout.services.janice.requests.post')
def test_appraise_success(mock_post):
    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {
            'itemType': {'eid': 22, 'name': 'Arkonor'},
            'immediatePrices': {'buyPrice': 100.0, 'sellPrice': 110.0},
            'quantity': 1000
        }
    ]
    mock_post.return_value = mock_response

    # Test
    result = JaniceService.appraise("Arkonor\t1000")

    assert len(result) == 1
    assert result[0]['name'] == 'Arkonor'
    assert result[0]['total_value'] == 100000.0
```

---

## Resources

- **Janice Website**: https://janice.e-351.com/
- **API Docs**: https://janice.e-351.com/api/rest/docs/index.html
- **GitHub**: https://github.com/E-351/janice
- **Sample Code**: https://github.com/E-351/janice/blob/master/janice-v2.gs
