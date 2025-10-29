"""Custom template filters for AA-Payout"""

# Standard Library
from decimal import Decimal

# Django
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def isk_format(value):
    """
    Format ISK values in a human-readable format.

    Examples:
        500 -> "500"
        1,500 -> "1.5K"
        1,500,000 -> "1.5M"
        1,500,000,000 -> "1.5B"
        1,500,000,000,000 -> "1.5T"

    Args:
        value: Numeric value (int, float, or Decimal)

    Returns:
        Formatted string with K/M/B/T suffix
    """
    if value is None:
        return "0"

    # Convert to Decimal for consistent handling
    try:
        if isinstance(value, (int, float)):
            amount = Decimal(str(value))
        elif isinstance(value, Decimal):
            amount = value
        else:
            return str(value)
    except (ValueError, TypeError):
        return str(value)

    # Handle negative values
    is_negative = amount < 0
    amount = abs(amount)

    # Determine the appropriate suffix and divisor
    if amount >= Decimal("1000000000000"):  # 1 trillion+
        divisor = Decimal("1000000000000")
        suffix = "T"
    elif amount >= Decimal("1000000000"):  # 1 billion+
        divisor = Decimal("1000000000")
        suffix = "B"
    elif amount >= Decimal("1000000"):  # 1 million+
        divisor = Decimal("1000000")
        suffix = "M"
    elif amount >= Decimal("1000"):  # 1 thousand+
        divisor = Decimal("1000")
        suffix = "K"
    else:
        # Less than 1,000 - show as integer
        result = str(int(amount))
        if is_negative:
            result = f"-{result}"
        return result

    # Calculate the formatted value
    formatted_amount = amount / divisor

    # Format with 1 decimal place, but drop .0 if it's a round number
    if formatted_amount == int(formatted_amount):
        result = f"{int(formatted_amount)}{suffix}"
    else:
        result = f"{formatted_amount:.1f}{suffix}"

    if is_negative:
        result = f"-{result}"

    return result


@register.filter
def isk_format_full(value):
    """
    Format ISK values with the 'ISK' suffix.

    Examples:
        1,500,000 -> "1.5M ISK"

    Args:
        value: Numeric value

    Returns:
        Formatted string with K/M/B/T suffix and "ISK"
    """
    formatted = isk_format(value)
    return f"{formatted} ISK"


@register.filter
def isk_detailed(value):
    """
    Format ISK values with both abbreviated and full value on hover.

    Creates a tooltip showing the full value when hovering over the abbreviated value.

    Args:
        value: Numeric value

    Returns:
        HTML string with tooltip
    """
    if value is None:
        return mark_safe('<span title="0 ISK">0 ISK</span>')

    try:
        # Format the value
        formatted = isk_format(value)

        # Get full value with commas
        if isinstance(value, (int, float)):
            amount = Decimal(str(value))
        elif isinstance(value, Decimal):
            amount = value
        else:
            return str(value)

        # Format full value with commas
        full_value = f"{amount:,.2f}"

        # Create tooltip HTML
        html = (
            f'<span title="{full_value} ISK" '
            f'style="cursor: help; border-bottom: 1px dotted currentColor;">'
            f"{formatted} ISK</span>"
        )

        return mark_safe(html)

    except (ValueError, TypeError):
        return str(value)


@register.filter
def get_item(dictionary, key):
    """
    Get item from dictionary by key.

    Usage in template:
        {{ my_dict|get_item:key_variable }}

    Args:
        dictionary: Dictionary to access
        key: Key to look up

    Returns:
        Value from dictionary or None if not found
    """
    if dictionary is None:
        return None
    return dictionary.get(key)
