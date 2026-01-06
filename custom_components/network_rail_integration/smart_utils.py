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


def find_adjacent_stations_multihop(
    graph: dict[str, Any],
    center_berth_keys: set[str],
    center_stanox: str,
    max_hops: int = 3
) -> dict[str, int]:
    """Find stations within max_hops berth steps from center station.  
    
    Returns:  
        Dictionary mapping stanox -> hop_distance
    """
    from collections import deque
    
    berth_to_connections = graph. get("berth_to_connections", {})
    berth_to_stanox = graph.get("berth_to_stanox", {})
    
    adjacent_stations = {}  # stanox -> distance
    visited_berths = set()
    queue = deque()
    
    # Initialize with center berths at distance 0
    for berth_key in center_berth_keys:
        queue.append((berth_key, 0))
        visited_berths.add(berth_key)
    
    _LOGGER.debug("Multi-hop:  Starting from %d center berths", len(center_berth_keys))
    
    hop_counts = {0: len(center_berth_keys)}
    
    while queue: 
        current_berth, distance = queue.popleft()
        
        # Stop if we've gone too far
        if distance >= max_hops:
            continue
        
        connections = berth_to_connections. get(current_berth, {})
        
        # Check both "from" and "to" connections
        for direction in ["from", "to"]:  
            for conn in connections. get(direction, []):
                conn_td_area = conn.get("td_area", "")
                conn_berth = conn.get("berth", "")
                
                if not conn_td_area or not conn_berth:
                    continue
                
                conn_key = f"{conn_td_area}:{conn_berth}"
                conn_stanox = berth_to_stanox.get(conn_key)
                
                # Found a station (not the center)
                if conn_stanox and conn_stanox != center_stanox:
                    # Record this station if not seen or closer
                    if conn_stanox not in adjacent_stations or distance + 1 < adjacent_stations[conn_stanox]: 
                        adjacent_stations[conn_stanox] = distance + 1
                
                # Continue exploring from this berth
                if conn_key not in visited_berths:
                    visited_berths.add(conn_key)
                    queue.append((conn_key, distance + 1))
                    hop_counts[distance + 1] = hop_counts.get(distance + 1, 0) + 1
    
    _LOGGER. debug("Multi-hop:  Visited %d berths across hops:  %s", len(visited_berths), hop_counts)
    
    return adjacent_stations


# hello

def get_station_berths_with_connections(
    graph: dict[str, Any], 
    stanox:  str,
    max_hops: int = 3
) -> dict[str, Any]:
    """Get comprehensive station berth data including adjacent stations."""
    berth_to_connections = graph.get("berth_to_connections", {})
    berth_to_stanox = graph.get("berth_to_stanox", {})
    stanox_to_berths = graph.get("stanox_to_berths", {})
    
    _LOGGER.info("=" * 80)
    _LOGGER.info("Getting station berths with connections for STANOX: %s", stanox)
    
    # Get berths for this station
    berth_records = stanox_to_berths.get(stanox, [])
    
    # Extract station name from first berth record
    stanme = ""
    if berth_records:
        stanme = berth_records[0].get("stanme", "")
    
    _LOGGER.info("Center station: %s (%s), %d berth records", stanme, stanox, len(berth_records))
    
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
                berths. append({
                    "berth_id": from_berth,
                    "td_area":  td_area,
                    "platform": record.get("platform", ""),
                    "event":  record.get("event", ""),
                })
        
        if to_berth and td_area:
            berth_key = f"{td_area}:{to_berth}"
            if berth_key not in berth_keys:
                berth_keys.add(berth_key)
                berths.append({
                    "berth_id":  to_berth,
                    "td_area": td_area,
                    "platform": record.get("platform", ""),
                    "event": record.get("event", ""),
                })
    
    _LOGGER.info("Center station berths: %s", sorted([b["berth_id"] for b in berths]))
    
    # Calculate average berth number for center station (for direction heuristic)
    center_berth_nums = []
    for rec in berth_records: 
        for berth_field in ["from_berth", "to_berth"]:
            berth = rec.get(berth_field, "")
            if berth and berth.isdigit():
                center_berth_nums. append(int(berth))
    avg_center = sum(center_berth_nums) / len(center_berth_nums) if center_berth_nums else 0
    _LOGGER.info("Center station average berth number: %.1f", avg_center)
    
    # Use multi-hop discovery to find adjacent stations (within max_hops berth hops)
    _LOGGER.info("Starting multi-hop discovery (max %d hops)...", max_hops)
    adjacent_stations = find_adjacent_stations_multihop(graph, berth_keys, stanox, max_hops=max_hops)
    
    
    # Use multi-hop discovery to find adjacent stations
    _LOGGER.info("Starting multi-hop discovery (max %d hops)...", max_hops)
    adjacent_stations = find_adjacent_stations_multihop(graph, berth_keys, stanox, max_hops=max_hops)
    
    _LOGGER.info("Found %d adjacent stations via connections", len(adjacent_stations))
    
    # FALLBACK: If we found fewer than expected stations, try berth proximity search
    if len(adjacent_stations) < 5:  # Arbitrary threshold
        _LOGGER.info("Using berth proximity fallback to find additional stations...")
        
        # Determine primary TD area from berth records
        td_areas = set(rec.get("td_area") for rec in berth_records)
        primary_td_area = td_areas.pop() if td_areas else None
        
        if primary_td_area and center_berth_nums:
            nearby_by_proximity = find_nearby_stations_by_berth_proximity(
                graph, stanox, center_berth_nums, primary_td_area, max_distance=50
            )
            
            _LOGGER.info("Found %d stations by berth proximity", len(nearby_by_proximity))
            
            # Add nearby stations that weren't found by multi-hop
            for nearby_stanox, distance in nearby_by_proximity:
                if nearby_stanox not in adjacent_stations:
                    # Estimate hop distance based on berth distance
                    estimated_hops = max(1, int(distance / 10))
                    adjacent_stations[nearby_stanox] = estimated_hops
                    _LOGGER.info("  Added %s via proximity (distance:  %.1f berths)", 
                                nearby_stanox, distance)
    
    
    _LOGGER.info("Found %d adjacent stations:", len(adjacent_stations))
    for adj_stanox, hop_distance in adjacent_stations.items():
        adj_records = stanox_to_berths.get(adj_stanox, [])
        adj_name = adj_records[0].get("stanme", "") if adj_records else "Unknown"
        _LOGGER. info("  - %s (%s) at %d hops", adj_name, adj_stanox, hop_distance)
    
    # Classify stations as UP or DOWN based on berth numbers and line evidence
    up_adjacent_stanox = set()
    down_adjacent_stanox = set()
    
    for adj_stanox, hop_distance in adjacent_stations.items():
        adj_berth_records = stanox_to_berths.get(adj_stanox, [])
        if not adj_berth_records: 
            continue
        
        adj_name = adj_berth_records[0].get("stanme", "")
        
        _LOGGER.info("-" * 60)
        _LOGGER.info("Classifying station:  %s (%s)", adj_name, adj_stanox)
        
        # Try to determine direction from line names in connections
        up_evidence = 0
        down_evidence = 0
        line_details = []
        
        # Check all berths of adjacent station for line indicators
        for adj_rec in adj_berth_records: 
            adj_td_area = adj_rec.get("td_area", "")
            for berth_field in ["from_berth", "to_berth"]: 
                adj_berth = adj_rec. get(berth_field, "")
                if not adj_berth or not adj_td_area:
                    continue
                
                adj_berth_key = f"{adj_td_area}:{adj_berth}"
                connections = berth_to_connections.get(adj_berth_key, {})
                
                # Check connections for line indicators
                for direction in ["from", "to"]: 
                    for conn in connections.get(direction, []):
                        conn_line = conn.get("line", "").upper()
                        conn_berth = conn.get("berth", "")
                        conn_td_area = conn.get("td_area", "")
                        
                        if conn_line: 
                            line_details.append(f"{direction}:{adj_berth}->{conn_berth} [{conn_line}]")
                            
                        if "UP" in conn_line: 
                            up_evidence += 1
                        elif "DOWN" in conn_line:
                            down_evidence += 1
        
        _LOGGER.info("  Line evidence - UP: %d, DOWN: %d", up_evidence, down_evidence)
        if line_details:
            _LOGGER.info("  Line details: %s", ", ".join(line_details[: 5]))  # Show first 5
        
        # Get berth numbers for comparison
        adj_berth_nums = []
        for rec in adj_berth_records:
            for berth_field in ["from_berth", "to_berth"]:
                berth = rec.get(berth_field, "")
                if berth and berth.isdigit():
                    adj_berth_nums.append(int(berth))
        
        avg_adj = sum(adj_berth_nums) / len(adj_berth_nums) if adj_berth_nums else 0
        _LOGGER.info("  Adjacent station average berth:  %.1f", avg_adj)
        
        # Decide direction based on evidence or berth numbers
        if up_evidence > down_evidence: 
            _LOGGER.info("  -> Classified as UP (line evidence)")
            up_adjacent_stanox.add(adj_stanox)
        elif down_evidence > up_evidence:  
            _LOGGER.info("  -> Classified as DOWN (line evidence)")
            down_adjacent_stanox.add(adj_stanox)
        else:
            # Use berth number heuristic
            if avg_adj > 0 and avg_center > 0:
                if avg_adj < avg_center:  
                    _LOGGER. info("  -> Classified as UP (berth %.1f < center %.1f)", avg_adj, avg_center)
                    up_adjacent_stanox.add(adj_stanox)
                else:
                    _LOGGER.info("  -> Classified as DOWN (berth %.1f > center %.1f)", avg_adj, avg_center)
                    down_adjacent_stanox.add(adj_stanox)
            else:
                _LOGGER. info("  -> Classified as DOWN (default)")
                down_adjacent_stanox.add(adj_stanox)
    
    _LOGGER.info("=" * 80)
    _LOGGER.info("Final classification:")
    _LOGGER.info("  UP stations: %d", len(up_adjacent_stanox))
    _LOGGER.info("  DOWN stations: %d", len(down_adjacent_stanox))
    
    # Build station lists
    def build_station_list(stanox_set):
        stations = []
        for adj_stanox in stanox_set:  
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
                            "berth_id":  to_berth,
                            "td_area": td_area,
                        })
            
            stations.append({
                "stanox": adj_stanox,
                "stanme": adj_stanme,
                "berths": adj_berths,
            })
        return stations
    
    up_connections = build_station_list(up_adjacent_stanox)
    down_connections = build_station_list(down_adjacent_stanox)
    
    # TEMPORARY: Check if Birchington exists
    if stanox == "89483":  # Herne Bay
        birchington_info = search_station_in_smart(graph, "89479")
        _LOGGER.info("=" * 80)
        _LOGGER.info("DIAGNOSTIC: Searching for Birchington (89479)")
        _LOGGER.info("Found: %s", birchington_info["found"])
        if birchington_info["found"]:
            _LOGGER.info("Station name: %s", birchington_info. get("station_name"))
            _LOGGER.info("Berths:  %s", birchington_info["berths"])
        else:
            _LOGGER. info("Birchington (89479) NOT FOUND in SMART data!")
        _LOGGER.info("=" * 80)
    
    
    
    # TEMPORARY: Check for berths between Herne Bay and Birchington
    if stanox == "89483":  # Herne Bay
        birchington_info = search_station_in_smart(graph, "89479")
        _LOGGER.info("=" * 80)
        _LOGGER.info("DIAGNOSTIC: Searching for Birchington (89479)")
        _LOGGER.info("Found: %s", birchington_info["found"])
        if birchington_info["found"]:
            _LOGGER.info("Station name: %s", birchington_info. get("station_name"))
            _LOGGER.info("Berths:  %s", birchington_info["berths"])
            
            # Check connections from Herne Bay's highest berth
            _LOGGER.info("-" * 60)
            _LOGGER.info("Checking connections from Herne Bay berth 5094:")
            berth_5094_key = "EK: 5094"
            connections_5094 = berth_to_connections.get(berth_5094_key, {})
            _LOGGER.info("  'to' connections: %s", connections_5094.get("to", []))
            _LOGGER.info("  'from' connections: %s", connections_5094.get("from", []))
            
            # Check connections TO Birchington's lowest berth
            _LOGGER.info("-" * 60)
            _LOGGER.info("Checking connections TO Birchington berth 5095:")
            berth_5095_key = "EK: 5095"
            connections_5095 = berth_to_connections.get(berth_5095_key, {})
            _LOGGER.info("  'to' connections: %s", connections_5095.get("to", []))
            _LOGGER.info("  'from' connections:  %s", connections_5095.get("from", []))
            
            # Check if there's a STANOX for 5095
            stanox_5095 = berth_to_stanox.get(berth_5095_key)
            _LOGGER.info("  Berth 5095 belongs to STANOX: %s", stanox_5095)
            
        else:
            _LOGGER. info("Birchington (89479) NOT FOUND in SMART data!")
        _LOGGER.info("=" * 80)    
    
    
    
    
    
    
    return {
        "stanox": stanox,
        "stanme": stanme,
        "berths": berths,
        "up_connections": up_connections,
        "down_connections": down_connections,
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
    
    
    
    
def search_station_in_smart(graph: dict[str, Any], stanox: str) -> dict[str, Any]:
    """Search for a station in SMART data - diagnostic function."""
    stanox_to_berths = graph.get("stanox_to_berths", {})
    berth_to_stanox = graph.get("berth_to_stanox", {})
    
    result = {
        "found": False,
        "stanox": stanox,
        "berths": [],
        "connections": []
    }
    
    # Check if station exists
    berth_records = stanox_to_berths.get(stanox, [])
    if berth_records:
        result["found"] = True
        result["station_name"] = berth_records[0].get("stanme", "Unknown")
        
        # List all berths
        for record in berth_records:
            result["berths"].append({
                "td_area": record.get("td_area"),
                "from_berth": record.get("from_berth"),
                "to_berth": record.get("to_berth"),
                "platform": record.get("platform"),
            })
    
    return result
    
    
    
def find_nearby_stations_by_berth_proximity(
    graph: dict[str, Any],
    center_stanox: str,
    center_berth_nums: list[int],
    center_td_area: str,
    max_distance: int = 50
) -> list[tuple[str, float]]:
    """Find stations in the same TD area with nearby berth numbers. 
    
    Returns: 
        List of (stanox, avg_berth_distance) tuples
    """
    stanox_to_berths = graph.get("stanox_to_berths", {})
    nearby_stations = {}
    
    if not center_berth_nums:
        return []
    
    center_avg = sum(center_berth_nums) / len(center_berth_nums)
    
    # Search all stations in the graph
    for adj_stanox, berth_records in stanox_to_berths.items():
        if adj_stanox == center_stanox:
            continue
        
        # Get berths for this station in the same TD area
        adj_berth_nums = []
        for record in berth_records:
            if record.get("td_area") != center_td_area:
                continue
            
            for berth_field in ["from_berth", "to_berth"]:
                berth = record.get(berth_field, "")
                if berth and berth.isdigit():
                    adj_berth_nums.append(int(berth))
        
        if not adj_berth_nums: 
            continue
        
        # Calculate average distance
        adj_avg = sum(adj_berth_nums) / len(adj_berth_nums)
        distance = abs(adj_avg - center_avg)
        
        if distance <= max_distance:
            nearby_stations[adj_stanox] = distance
    
    # Return sorted by distance
    return sorted(nearby_stations.items(), key=lambda x: x[1])
