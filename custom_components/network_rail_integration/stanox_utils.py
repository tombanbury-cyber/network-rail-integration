"""Utilities for working with STANOX reference data."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

_stanox_data: list[dict[str, str]] | None = None
_stanox_lookup: dict[str, str] | None = None


def load_stanox_data() -> list[dict[str, str]]:
    """Load STANOX reference data from CSV file.

    Returns:
        A list of dictionaries with 'stanox' and 'stanme' keys.
    """
    global _stanox_data, _stanox_lookup
    
    if _stanox_data is not None:
        return _stanox_data
    
    _stanox_data = []
    _stanox_lookup = {}
    
    try:
        csv_path = Path(__file__).parent / "stanox-stanme.csv"
        
        if not csv_path.exists():
            _LOGGER.error("STANOX reference data file not found: %s", csv_path)
            return _stanox_data
        
        if not csv_path.is_file():
            _LOGGER.error("STANOX reference data path is not a file: %s", csv_path)
            return _stanox_data
        
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    stanox = row[0].strip()
                    stanme = row[1].strip()
                    if stanox and stanme:
                        _stanox_data.append({
                            "stanox": stanox,
                            "stanme": stanme,
                        })
                        # Build lookup dictionary for O(1) access
                        _stanox_lookup[stanox] = stanme
        
        _LOGGER.debug("Loaded %d STANOX entries", len(_stanox_data))
    except Exception as exc:
        _LOGGER.error("Failed to load STANOX reference data: %s", exc)
        _stanox_data = []
        _stanox_lookup = {}
    
    return _stanox_data


def get_stanox_options() -> list[dict[str, str]]:
    """Get STANOX options formatted for Home Assistant selector.

    Returns:
        A list of dicts with 'value' (stanox) and 'label' (formatted display string).
    """
    data = load_stanox_data()
    
    options = []
    for entry in data:
        stanox = entry["stanox"]
        stanme = entry["stanme"]
        # Format: "STANME (STANOX)"
        label = f"{stanme} ({stanox})"
        options.append({
            "value": stanox,
            "label": label,
        })
    
    return options


def search_stanox(query: str, limit: int = 100) -> list[dict[str, str]]:
    """Search STANOX data by station name or code.

    Args:
        query: Search query (case-insensitive)
        limit: Maximum number of results to return

    Returns:
        List of matching STANOX entries
    """
    if not query:
        return []
    
    data = load_stanox_data()
    query_lower = query.lower()
    
    results = []
    for entry in data:
        stanox = entry["stanox"]
        stanme = entry["stanme"]
        
        # Match if query is in station name or exact STANOX code
        if query_lower in stanme.lower() or query == stanox:
            results.append(entry)
            
            if len(results) >= limit:
                break
    
    return results


def format_station_name(raw_name: str | None) -> str | None:
    """Format a station name from the STANOX CSV to be more human-readable.
    
    Converts names like "CANTBURYW" to "Canterbury West", "WHITSTBLE" to "Whitstable", etc.
    
    Args:
        raw_name: The raw station name from the CSV (usually uppercase)
        
    Returns:
        Formatted station name, or None if input is None
    """
    if not raw_name:
        return None
    
    # Start with the raw name
    name = raw_name.strip().upper()
    
    # Manual overrides for common abbreviations and special cases
    manual_overrides = {
        "CANTBURYW": "Canterbury West",
        "CANTBURYE": "Canterbury East",
        "WHITSTBLE": "Whitstable",
        "ASHFORDMD": "Ashford Middle",
        "ASHFORDCS": "Ashford CS",
        "ASHFORDCR": "Ashford CR",
        "ASHFORDWY": "Ashford WY",
        "ASHFORDI": "Ashford International",
        "ASHFORDWJ": "Ashford West Junction",
        "ASHFORDEJ": "Ashford East Junction",
    }
    
    # Check manual overrides first
    if name in manual_overrides:
        return manual_overrides[name]
    
    # Dictionary of suffix patterns that clearly indicate a station type/direction
    # Only match these if they are clearly separated or commonly used suffixes
    suffix_patterns = [
        # Multi-character suffixes (more reliable)
        ("JN", " Junction"),
        ("JCT", " Junction"),
        ("STN", " Station"),
        ("RD", " Road"),
        ("ST", " Street"),
        ("SQ", " Square"),
        ("PK", " Park"),
        ("BR", " Bridge"),
        ("GB", " Goods Branch"),
        ("SB", " Signal Box"),
        ("GF", " Ground Frame"),
        ("LP", " Loop"),
        ("SDG", " Siding"),
        ("YD", " Yard"),
        ("HL", " Halt"),
        ("HBF", " Hauptbahnhof"),
    ]
    
    # Check for multi-character suffix patterns
    for suffix, replacement in suffix_patterns:
        if name.endswith(suffix) and len(name) > len(suffix) + 3:
            base = name[:-len(suffix)]
            formatted_base = base.title()
            return formatted_base + replacement
    
    # For single-letter directional suffixes, be more conservative
    # Only apply if the name is long enough and the pattern is clear
    if len(name) > 6:
        if name.endswith("W") and not name[-2].isdigit():
            # Could be West
            base = name[:-1]
            return base.title() + " West"
        elif name.endswith("E") and not name[-2].isdigit():
            # Could be East, but be careful
            base = name[:-1]
            return base.title() + " East"
        elif name.endswith("N") and not name[-2].isdigit():
            base = name[:-1]
            return base.title() + " North"
        elif name.endswith("S") and not name[-2].isdigit():
            base = name[:-1]
            return base.title() + " South"
    
    # If no suffix match, just convert to title case
    return name.title()


def get_station_name(stanox: str | None) -> str | None:
    """Get the station name for a given STANOX code.
    
    Args:
        stanox: The STANOX code to look up
        
    Returns:
        The station name, or None if not found
    """
    if not stanox:
        return None
    
    global _stanox_lookup
    
    # Ensure data is loaded
    if _stanox_lookup is None:
        load_stanox_data()
    
    stanox_str = str(stanox).strip()
    return _stanox_lookup.get(stanox_str) if _stanox_lookup else None


def get_formatted_station_name(stanox: str | None) -> str | None:
    """Get the formatted station name for a given STANOX code.
    
    This returns a human-readable version of the station name (e.g., "Canterbury West"
    instead of "CANTBURYW").
    
    Args:
        stanox: The STANOX code to look up
        
    Returns:
        The formatted station name, or None if not found
    """
    raw_name = get_station_name(stanox)
    return format_station_name(raw_name)
