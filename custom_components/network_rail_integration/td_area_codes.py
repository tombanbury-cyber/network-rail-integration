"""TD (Train Describer) area codes reference data."""

from __future__ import annotations

# Mapping of TD area codes to geographical area names
# Based on Network Rail signalling area designations
TD_AREA_CODES = {
    # London and South East
    "AW": "Ashford West",
    "EK": "East Kent",
    "G1": "Clapham Junction",
    "G3": "Battersea",
    "SE": "South Eastern",
    "TH": "Thameslink",
    "VN": "Victoria",
    "WD": "Wimbledon",
    "WK": "Waterloo",
    
    # South
    "BH": "Brighton",
    "EH": "Eastleigh",
    "SN": "Southampton",
    
    # South West
    "EX": "Exeter",
    "NW": "Newton Abbot",
    "PZ": "Penzance",
    "RW": "Reading West",
    
    # Midlands
    "BM": "Birmingham",
    "CF": "Cardiff",
    "NR": "Nuneaton",
    "WV": "Wolverhampton",
    
    # North West
    "CH": "Chester",
    "CR": "Crewe",
    "LV": "Liverpool",
    "MC": "Manchester Central",
    "PG": "Preston",
    "WN": "Wigan",
    
    # North East
    "DN": "Doncaster",
    "HF": "Halifax",
    "HU": "Hull",
    "LD": "Leeds",
    "SK": "Sheffield",
    "YK": "York",
    
    # Scotland
    "ED": "Edinburgh",
    "GL": "Glasgow",
    "AB": "Aberdeen",
    "DU": "Dundee",
    
    # Wales
    "SW": "Swansea",
    "CY": "Cardiff Valleys",
    
    # East
    "CB": "Cambridge",
    "IP": "Ipswich",
    "NC": "Norwich",
    "PE": "Peterborough",
    
    # Add more as needed
}


def get_td_area_name(area_id: str | None) -> str | None:
    """Get the geographical area name for a TD area code.
    
    Args:
        area_id: The TD area code (e.g., "AW", "EK", "SK")
        
    Returns:
        The area name, or None if not found
    """
    if not area_id:
        return None
    
    area_id_upper = str(area_id).strip().upper()
    return TD_AREA_CODES.get(area_id_upper)


def format_td_area_title(area_id: str) -> str:
    """Format a TD area code into a human-readable title.
    
    Args:
        area_id: The TD area code (e.g., "AW", "EK")
        
    Returns:
        Formatted title like "TD Area Ashford West (AW)" or "TD Area AW" if name not found
    
    Examples:
        >>> format_td_area_title("AW")
        "TD Area Ashford West (AW)"
        >>> format_td_area_title("XX")
        "TD Area XX"
    """
    area_name = get_td_area_name(area_id)
    if area_name:
        return f"TD Area {area_name} ({area_id})"
    return f"TD Area {area_id}"
