"""TOC (Train Operating Company) codes reference data."""

from __future__ import annotations

# Mapping of TOC numeric codes to company names
# Based on Network Rail reference data
TOC_CODES = {
    "20": "TransPennine Express",
    "21": "Greater Anglia",
    "22": "Grand Central",
    "23": "Northern Trains",
    "25": "Great Western Railway",
    "27": "CrossCountry",
    "28": "East Midlands Railway",
    "29": "West Midlands Trains",
    "30": "London Overground",
    "35": "Caledonian Sleeper",
    "55": "Hull Trains",
    "60": "ScotRail",
    "61": "London North Eastern Railway",
    "64": "Merseyrail",
    "65": "Avanti West Coast",
    "71": "Transport for Wales",
    "74": "Chiltern Railways",
    "79": "c2c",
    "80": "Southeastern",
    "84": "South Western Railway",
    "86": "Heathrow Express",
    "88": "Southern/Thameslink/Gatwick Express",
    # Add more as needed - freight operators often use different codes
}

# Direction indicators
DIRECTION_CODES = {
    "U": "UP (towards London)",
    "D": "DOWN (away from London)",
    "": "Not specified",
}

# Line indicators - these vary by location, so we provide generic descriptions
LINE_CODES = {
    "F": "Fast line",
    "S": "Slow line",
    "M": "Main line",
    "R": "Relief line",
    "L": "Local line",
    "": "Not specified",
}


def get_toc_name(toc_id: str | None) -> str:
    """Get the train operating company name from TOC ID.
    
    Args:
        toc_id: The TOC ID code (e.g., "79")
        
    Returns:
        The company name, or "Unknown" if not found
    """
    if not toc_id:
        return "Unknown"
    
    toc_str = str(toc_id).strip()
    return TOC_CODES.get(toc_str, f"Operator {toc_str}")


def get_direction_description(direction_ind: str | None) -> str:
    """Get a human-readable description of the direction indicator.
    
    Args:
        direction_ind: The direction indicator (e.g., "U", "D")
        
    Returns:
        A description of the direction
    """
    if not direction_ind:
        return "Not specified"
    
    dir_str = str(direction_ind).strip().upper()
    return DIRECTION_CODES.get(dir_str, dir_str)


def get_line_description(line_ind: str | None) -> str:
    """Get a human-readable description of the line indicator.
    
    Args:
        line_ind: The line indicator (e.g., "F", "S")
        
    Returns:
        A description of the line
    """
    if not line_ind:
        return "Not specified"
    
    line_str = str(line_ind).strip().upper()
    return LINE_CODES.get(line_str, line_str)
