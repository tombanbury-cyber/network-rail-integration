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
