"""Utility functions for querying SMART berth topology data."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

_LOGGER = logging.getLogger(__name__)


def get_adjacent_berths(
    graph: dict[str, Any], 
    berth_id: str, 
    td_area: str
) -> dict[str, list[dict[str, str]]]:
    """Get berths connected to this berth.
    
    Args:
        graph: SMART graph structure from SmartDataManager
        berth_id: Berth identifier (e.g., "3647")
        td_area: TD area code (e.g., "SK")
        
    Returns:
        Dictionary with "from" and "to" lists of connected berths:
        {
            "from": [{"berth": "3647", "line": "UP", "steptype": "B"}, ...],
            "to": [{"berth": "3649", "line": "DOWN", "steptype": "B"}, ...]
        }
    """
    berth_key = f"{td_area}:{berth_id}"
    connections = graph.get("berth_to_connections", {})
    
    result = connections.get(berth_key, {"from": [], "to": []})
    return {
        "from": result.get("from", []),
        "to": result.get("to", [])
    }


def get_berths_for_stanox(
    graph: dict[str, Any], 
    stanox: str
) -> list[dict[str, str]]:
    """Get all berths associated with a STANOX location.
    
    Args:
        graph: SMART graph structure from SmartDataManager
        stanox: STANOX code (e.g., "32000")
        
    Returns:
        List of dictionaries with berth information:
        [
            {
                "td_area": "SK",
                "from_berth": "M123",
                "to_berth": "M124",
                "stanme": "MANCR PIC",
                "platform": "1",
                "event": "A",
                "steptype": "B"
            },
            ...
        ]
    """
    stanox_to_berths = graph.get("stanox_to_berths", {})
    return stanox_to_berths.get(stanox, [])


def get_station_berths_with_connections(
    graph: dict[str, Any], 
    stanox: str
) -> dict[str, Any]:
    """Get comprehensive station berth data including adjacent stations.
    
    Args:
        graph: SMART graph structure from SmartDataManager
        stanox: STANOX code for the center station
        
    Returns:
        Dictionary with station info and connections:
        {
            "stanox": "32000",
            "stanme": "MANCR PIC",
            "berths": [
                {
                    "berth_id": "M123",
                    "td_area": "SK",
                    "platform": "1",
                    "event": "A"
                },
                ...
            ],
            "up_connections": [
                {
                    "stanox": "32009",
                    "stanme": "ARDWICKJN",
                    "berths": [...]
                },
                ...
            ],
            "down_connections": [
                {
                    "stanox": "32050",
                    "stanme": "ASHBURYS",
                    "berths": [...]
                },
                ...
            ]
        }
    """
    berth_to_connections = graph.get("berth_to_connections", {})
    berth_to_stanox = graph.get("berth_to_stanox", {})
    stanox_to_berths = graph.get("stanox_to_berths", {})
    
    # Get berths for this station
    berth_records = stanox_to_berths.get(stanox, [])
    
    # Extract station name from first berth record
    stanme = ""
    if berth_records:
        stanme = berth_records[0].get("stanme", "")
    
    # Build list of berths for this station
    berths = []
    berth_keys = set()
    
    for record in berth_records:
        td_area = record.get("td_area", "")
        from_berth = record.get("from_berth", "")
        to_berth = record.get("to_berth", "")
        
        # Track unique berths
        if from_berth and td_area:
            berth_key = f"{td_area}:{from_berth}"
            if berth_key not in berth_keys:
                berth_keys.add(berth_key)
                berths.append({
                    "berth_id": from_berth,
                    "td_area": td_area,
                    "platform": record.get("platform", ""),
                    "event": record.get("event", ""),
                })
        
        if to_berth and td_area:
            berth_key = f"{td_area}:{to_berth}"
            if berth_key not in berth_keys:
                berth_keys.add(berth_key)
                berths.append({
                    "berth_id": to_berth,
                    "td_area": td_area,
                    "platform": record.get("platform", ""),
                    "event": record.get("event", ""),
                })
    
    # Find adjacent stations by following berth connections
    adjacent_stanox = set()
    
    for berth_key in berth_keys:
        connections = berth_to_connections.get(berth_key, {})
        
        # Check "from" connections (trains coming from)
        for conn in connections.get("from", []):
            conn_td_area = conn.get("td_area", "")
            conn_berth = conn.get("berth", "")
            if conn_td_area and conn_berth:
                conn_key = f"{conn_td_area}:{conn_berth}"
                conn_stanox = berth_to_stanox.get(conn_key)
                if conn_stanox and conn_stanox != stanox:
                    adjacent_stanox.add(conn_stanox)
        
        # Check "to" connections (trains going to)
        for conn in connections.get("to", []):
            conn_td_area = conn.get("td_area", "")
            conn_berth = conn.get("berth", "")
            if conn_td_area and conn_berth:
                conn_key = f"{conn_td_area}:{conn_berth}"
                conn_stanox = berth_to_stanox.get(conn_key)
                if conn_stanox and conn_stanox != stanox:
                    adjacent_stanox.add(conn_stanox)
    
    # Build connection lists
    # Note: Without direction information in SMART data, we can't definitively
    # determine "up" vs "down". We'll just list all adjacent stations.
    # In a real implementation, this would require additional logic or metadata.
    adjacent_stations = []
    for adj_stanox in adjacent_stanox:
        adj_berth_records = stanox_to_berths.get(adj_stanox, [])
        adj_stanme = adj_berth_records[0].get("stanme", "") if adj_berth_records else ""
        
        adj_berths = []
        adj_berth_keys = set()
        for record in adj_berth_records:
            td_area = record.get("td_area", "")
            from_berth = record.get("from_berth", "")
            to_berth = record.get("to_berth", "")
            
            if from_berth and td_area:
                berth_key = f"{td_area}:{from_berth}"
                if berth_key not in adj_berth_keys:
                    adj_berth_keys.add(berth_key)
                    adj_berths.append({
                        "berth_id": from_berth,
                        "td_area": td_area,
                    })
            
            if to_berth and td_area:
                berth_key = f"{td_area}:{to_berth}"
                if berth_key not in adj_berth_keys:
                    adj_berth_keys.add(berth_key)
                    adj_berths.append({
                        "berth_id": to_berth,
                        "td_area": td_area,
                    })
        
        adjacent_stations.append({
            "stanox": adj_stanox,
            "stanme": adj_stanme,
            "berths": adj_berths,
        })
    
    # Split adjacent stations into up/down based on some heuristic
    # NOTE: This is a known limitation - SMART data does not include explicit
    # direction information, so we cannot definitively determine which stations
    # are "up" (towards London) vs "down" (away from London) in all cases.
    # 
    # Current approach: Split the list evenly. This is a naive heuristic that
    # may not reflect actual railway geography.
    #
    # For a production implementation, this would require:
    # - Additional metadata about station positions/directions
    # - Route analysis to determine typical train flow patterns
    # - Manual configuration or external data source for direction mapping
    #
    # Users should be aware that the "up_connections" and "down_connections" 
    # labels are approximate and may not match official railway terminology.
    #mid = len(adjacent_stations) // 2
    mid = (len(adjacent_stations) + 1) // 2
    
    return {
        "stanox": stanox,
        "stanme": stanme,
        "berths": berths,
        "up_connections": adjacent_stations[:mid],
        "down_connections": adjacent_stations[mid:],
    }


def get_berth_route(
    graph: dict[str, Any], 
    from_stanox: str, 
    to_stanox: str, 
    max_hops: int = 10
) -> list[dict[str, str]]:
    """Find berth sequence between two stations using breadth-first search.
    
    Args:
        graph: SMART graph structure from SmartDataManager
        from_stanox: Starting STANOX code
        to_stanox: Destination STANOX code
        max_hops: Maximum number of berth hops to search (default: 10)
        
    Returns:
        List of berth dictionaries representing the path:
        [
            {"berth_id": "M123", "td_area": "SK", "stanox": "32000"},
            {"berth_id": "M124", "td_area": "SK", "stanox": None},
            {"berth_id": "M125", "td_area": "SK", "stanox": "32009"},
            ...
        ]
        Returns empty list if no path found.
    """
    berth_to_connections = graph.get("berth_to_connections", {})
    berth_to_stanox = graph.get("berth_to_stanox", {})
    stanox_to_berths = graph.get("stanox_to_berths", {})
    
    # Get starting berths for from_stanox
    from_berth_records = stanox_to_berths.get(from_stanox, [])
    if not from_berth_records:
        _LOGGER.warning("No berths found for starting STANOX: %s", from_stanox)
        return []
    
    # Get ending berths for to_stanox
    to_berth_records = stanox_to_berths.get(to_stanox, [])
    if not to_berth_records:
        _LOGGER.warning("No berths found for destination STANOX: %s", to_stanox)
        return []
    
    # Build set of destination berth keys
    dest_berth_keys = set()
    for record in to_berth_records:
        td_area = record.get("td_area", "")
        from_berth = record.get("from_berth", "")
        to_berth = record.get("to_berth", "")
        if from_berth and td_area:
            dest_berth_keys.add(f"{td_area}:{from_berth}")
        if to_berth and td_area:
            dest_berth_keys.add(f"{td_area}:{to_berth}")
    
    # BFS to find shortest path
    queue = deque()
    visited = set()
    
    # Initialize queue with starting berths
    for record in from_berth_records:
        td_area = record.get("td_area", "")
        from_berth = record.get("from_berth", "")
        to_berth = record.get("to_berth", "")
        
        if from_berth and td_area:
            berth_key = f"{td_area}:{from_berth}"
            queue.append((berth_key, [berth_key]))
            visited.add(berth_key)
        
        if to_berth and td_area:
            berth_key = f"{td_area}:{to_berth}"
            if berth_key not in visited:
                queue.append((berth_key, [berth_key]))
                visited.add(berth_key)
    
    # BFS search
    while queue:
        current_key, path = queue.popleft()
        
        # Check if we've reached the destination
        if current_key in dest_berth_keys:
            # Build result with berth info
            result = []
            for berth_key in path:
                parts = berth_key.split(":", 1)
                if len(parts) == 2:
                    td_area, berth_id = parts
                    result.append({
                        "berth_id": berth_id,
                        "td_area": td_area,
                        "stanox": berth_to_stanox.get(berth_key),
                    })
            return result
        
        # Check max hops
        if len(path) >= max_hops:
            continue
        
        # Explore neighbors
        connections = berth_to_connections.get(current_key, {})
        
        # Try "to" connections (forward direction)
        for conn in connections.get("to", []):
            conn_td_area = conn.get("td_area", "")
            conn_berth = conn.get("berth", "")
            if conn_td_area and conn_berth:
                next_key = f"{conn_td_area}:{conn_berth}"
                if next_key not in visited:
                    visited.add(next_key)
                    queue.append((next_key, path + [next_key]))
    
    # No path found
    _LOGGER.debug("No berth route found from %s to %s within %d hops", from_stanox, to_stanox, max_hops)
    return []


def get_platforms_for_area(
    graph: dict[str, Any],
    td_area: str
) -> list[str]:
    """Get list of unique platform IDs for a TD area from SMART data.
    
    Args:
        graph: SMART graph structure from SmartDataManager
        td_area: TD area code (e.g., "SK")
        
    Returns:
        Sorted list of unique platform identifiers found in this area
        (e.g., ["1", "2", "3", "4A", "4B"])
    """
    platforms = set()
    stanox_to_berths = graph.get("stanox_to_berths", {})
    
    # Scan all berth records for this TD area
    for berth_records in stanox_to_berths.values():
        for record in berth_records:
            if record.get("td_area") == td_area:
                platform = record.get("platform", "").strip()
                if platform:
                    platforms.add(platform)
    
    # Sort platforms naturally (1, 2, 3, ..., 10, 11, etc.)
    return sorted(platforms, key=lambda x: (len(x), x))


def get_berth_to_platform_mapping(
    graph: dict[str, Any],
    td_area: str
) -> dict[str, str]:
    """Get mapping of berth IDs to platform IDs for a TD area.
    
    Args:
        graph: SMART graph structure from SmartDataManager
        td_area: TD area code (e.g., "SK")
        
    Returns:
        Dictionary mapping berth_id to platform ID
        (e.g., {"M123": "1", "M124": "2"})
    """
    mapping = {}
    stanox_to_berths = graph.get("stanox_to_berths", {})
    
    # Build mapping from berth records
    for berth_records in stanox_to_berths.values():
        for record in berth_records:
            if record.get("td_area") == td_area:
                platform = record.get("platform", "").strip()
                if platform:
                    from_berth = record.get("from_berth", "").strip()
                    to_berth = record.get("to_berth", "").strip()
                    
                    if from_berth:
                        mapping[from_berth] = platform
                    if to_berth:
                        mapping[to_berth] = platform
    
    return mapping


def get_station_platforms(
    graph: dict[str, Any],
    stanox: str
) -> list[str]:
    """Get list of platforms for a specific station.
    
    Args:
        graph: SMART graph structure from SmartDataManager
        stanox: STANOX code for the station
        
    Returns:
        Sorted list of unique platform identifiers at this station
    """
    platforms = set()
    stanox_to_berths = graph.get("stanox_to_berths", {})
    berth_records = stanox_to_berths.get(stanox, [])
    
    for record in berth_records:
        platform = record.get("platform", "").strip()
        if platform:
            platforms.add(platform)
    
    # Sort platforms naturally
    return sorted(platforms, key=lambda x: (len(x), x))
