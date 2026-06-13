"""
utils.py
--------
Pure helper functions for number cleaning and formatting.
No business logic, no external dependencies beyond the standard library.
"""

import re


def clean_number(value):
    """
    Parse a raw financial string (e.g. "$1,234", "(11,043)", "38.5%")
    into a float.  Parentheses denote negative values.
    Returns None if the value cannot be parsed.
    """
    if value is None:
        return None

    value = str(value).strip()

    negative = False
    if "(" in value and ")" in value:
        negative = True

    value = value.replace("$", "")
    value = value.replace(",", "")
    value = value.replace("(", "")
    value = value.replace(")", "")
    value = value.replace("%", "")
    value = value.strip()

    try:
        number = float(value)
        return -number if negative else number
    except ValueError:
        return None


def percentage_change(current, previous):
    """Return the percentage change from *previous* to *current*."""
    return ((current - previous) / previous) * 100


def margin(part, total):
    """Return *part* as a percentage of *total*."""
    return (part / total) * 100


def safe_round(value, decimals=2):
    """Round *value* to *decimals* decimal places."""
    return round(value, decimals)


def format_money(value):
    """Format a numeric value as a USD-millions string, e.g. '$383,285 million'."""
    return f"${value:,.0f} million"


def format_percent(value):
    """Format a numeric value as a percentage string, e.g. '25.31%'."""
    return f"{value:.2f}%"
