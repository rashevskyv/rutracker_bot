"""
Size formatting utilities for torrent sizes.
"""
import re


def format_size(raw_size: str) -> str:
    """
    Normalize a torrent size string for display.

    Rules:
    - If >= 1 GB → show as X.XX ГБ (2 decimal places)
    - If < 1 GB → show as X МБ (no decimals)
    - If already in MB → keep as-is but clean up

    Args:
        raw_size: Raw size string like "12.03 ГБ", "0.52 ГБ", "534 MB"

    Returns:
        Formatted size string like "12.03 ГБ", "532 МБ"
    """
    if not raw_size or raw_size == "N/A":
        return raw_size

    # Try to extract number and unit
    match = re.match(r'([\d.,]+)\s*(ГБ|GB|МБ|MB|ТБ|TB|КБ|KB)', raw_size.strip(), re.IGNORECASE)
    if not match:
        return raw_size  # Can't parse, return as-is

    number_str = match.group(1).replace(',', '.')
    unit = match.group(2).upper()

    try:
        value = float(number_str)
    except ValueError:
        return raw_size

    # Normalize to GB
    if unit in ('MB', 'МБ'):
        value_gb = value / 1024
    elif unit in ('TB', 'ТБ'):
        value_gb = value * 1024
    elif unit in ('KB', 'КБ'):
        value_gb = value / (1024 * 1024)
    else:  # GB, ГБ
        value_gb = value

    # Format based on size
    if value_gb >= 1.0:
        return f"{value_gb:.2f} ГБ"
    else:
        value_mb = value_gb * 1024
        return f"{int(round(value_mb))} МБ"
