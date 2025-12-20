"""Train Describer message parser for Network Rail data."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# C-Class message types (berth operations)
TD_MSG_CA = "CA"  # Berth Step
TD_MSG_CB = "CB"  # Berth Cancel
TD_MSG_CC = "CC"  # Berth Interpose
TD_MSG_CT = "CT"  # Heartbeat

# S-Class message types (signalling state)
TD_MSG_SF = "SF"  # Signalling Update
TD_MSG_SG = "SG"  # Signalling Refresh
TD_MSG_SH = "SH"  # Signalling Refresh Finished

# All supported message types
TD_MESSAGE_TYPES = {TD_MSG_CA, TD_MSG_CB, TD_MSG_CC, TD_MSG_CT, TD_MSG_SF, TD_MSG_SG, TD_MSG_SH}


def parse_td_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a Train Describer message.
    
    Args:
        message: The raw message dictionary from STOMP
        
    Returns:
        Parsed message with type, area_id, and data, or None if not a TD message
        
    Example CA message (Berth Step):
        {
            "CA_MSG": {
                "time": "1349696911000",
                "area_id": "SK",
                "msg_type": "CA",
                "from": "3647",
                "to": "3649",
                "descr": "1F42"
            }
        }
    
    Example CB message (Berth Cancel):
        {
            "CB_MSG": {
                "time": "1349696911000",
                "area_id": "G1",
                "msg_type": "CB",
                "from": "G669",
                "descr": "2J01"
            }
        }
        
    Example CC message (Berth Interpose):
        {
            "CC_MSG": {
                "time": "1349696911000",
                "area_id": "G1",
                "msg_type": "CC",
                "descr": "2J01",
                "to": "G669"
            }
        }
        
    Example SF message (Signalling Update):
        {
            "SF_MSG": {
                "time": "1422404915000",
                "area_id": "SI",
                "address": "16",
                "msg_type": "SF",
                "data": "43"
            }
        }
    """
    if not isinstance(message, dict):
        return None
    
    # TD messages are wrapped in a key like "CA_MSG", "CB_MSG", etc.
    for key, content in message.items():
        if not key.endswith("_MSG") or not isinstance(content, dict):
            continue
            
        msg_type = content.get("msg_type")
        if msg_type not in TD_MESSAGE_TYPES:
            continue
        
        # Extract common fields
        parsed = {
            "msg_type": msg_type,
            "time": content.get("time"),
            "area_id": content.get("area_id"),
        }
        
        # Add message-specific fields
        if msg_type == TD_MSG_CA:
            # Berth Step: move train from one berth to another
            parsed.update({
                "from_berth": content.get("from"),
                "to_berth": content.get("to"),
                "description": content.get("descr"),
            })
        elif msg_type == TD_MSG_CB:
            # Berth Cancel: remove train from berth
            parsed.update({
                "from_berth": content.get("from"),
                "description": content.get("descr"),
            })
        elif msg_type == TD_MSG_CC:
            # Berth Interpose: insert train into berth
            parsed.update({
                "to_berth": content.get("to"),
                "description": content.get("descr"),
            })
        elif msg_type == TD_MSG_CT:
            # Heartbeat
            parsed.update({
                "report_time": content.get("report_time"),
            })
        elif msg_type in (TD_MSG_SF, TD_MSG_SG, TD_MSG_SH):
            # Signalling messages
            parsed.update({
                "address": content.get("address"),
                "data": content.get("data"),
            })
        
        # Add raw message for debugging
        parsed["raw"] = content
        
        return parsed
    
    return None


def apply_td_filters(
    parsed_message: dict[str, Any],
    area_filter: set[str] | None = None,
    message_types: set[str] | None = None,
) -> bool:
    """Check if a parsed TD message passes the configured filters.
    
    Args:
        parsed_message: Parsed TD message from parse_td_message()
        area_filter: Set of area IDs to allow (None = allow all)
        message_types: Set of message types to allow (None = allow all)
        
    Returns:
        True if message passes filters, False otherwise
    """
    if area_filter:
        area_id = parsed_message.get("area_id", "")
        if area_id not in area_filter:
            return False
    
    if message_types:
        msg_type = parsed_message.get("msg_type", "")
        if msg_type not in message_types:
            return False
    
    return True


class BerthState:
    """Tracks the state of berths in a TD area."""
    
    def __init__(self) -> None:
        """Initialize berth state tracker."""
        self._berths: dict[str, dict[str, str]] = {}  # berth_id -> {description, timestamp}
    
    def update(self, parsed_message: dict[str, Any]) -> None:
        """Update berth state based on a TD message.
        
        Args:
            parsed_message: Parsed TD message from parse_td_message()
        """
        msg_type = parsed_message.get("msg_type")
        area_id = parsed_message.get("area_id")
        time = parsed_message.get("time")
        
        if msg_type == TD_MSG_CA:
            # Berth Step: move from one berth to another
            from_berth = f"{area_id}:{parsed_message.get('from_berth')}"
            to_berth = f"{area_id}:{parsed_message.get('to_berth')}"
            description = parsed_message.get("description", "")
            
            # Clear from berth
            self._berths.pop(from_berth, None)
            
            # Set to berth
            self._berths[to_berth] = {
                "description": description,
                "timestamp": time,
            }
            
        elif msg_type == TD_MSG_CB:
            # Berth Cancel: remove from berth
            from_berth = f"{area_id}:{parsed_message.get('from_berth')}"
            self._berths.pop(from_berth, None)
            
        elif msg_type == TD_MSG_CC:
            # Berth Interpose: insert into berth
            to_berth = f"{area_id}:{parsed_message.get('to_berth')}"
            description = parsed_message.get("description", "")
            
            self._berths[to_berth] = {
                "description": description,
                "timestamp": time,
            }
    
    def get_berth(self, area_id: str, berth_id: str) -> dict[str, str] | None:
        """Get the current state of a berth.
        
        Args:
            area_id: TD area ID (e.g., "SK")
            berth_id: Berth ID (e.g., "3647")
            
        Returns:
            Dictionary with description and timestamp, or None if berth is empty
        """
        key = f"{area_id}:{berth_id}"
        return self._berths.get(key)
    
    def get_all_berths(self) -> dict[str, dict[str, str]]:
        """Get all current berth states.
        
        Returns:
            Dictionary mapping berth keys (area:berth) to state dictionaries
        """
        return self._berths.copy()
    
    def get_area_berths(self, area_id: str) -> dict[str, dict[str, str]]:
        """Get all berths in a specific TD area.
        
        Args:
            area_id: TD area ID (e.g., "SK")
            
        Returns:
            Dictionary mapping berth IDs to state dictionaries
        """
        prefix = f"{area_id}:"
        return {
            berth_id.replace(prefix, ""): state
            for berth_id, state in self._berths.items()
            if berth_id.startswith(prefix)
        }
