"""Train Describer message parser for Network Rail data."""

from __future__ import annotations

import logging
from collections import deque
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
        _LOGGER.debug("parse_td_message: message is not a dict (type=%s)", type(message))
        return None
    
    # TD messages are wrapped in a key like "CA_MSG", "CB_MSG", etc.
    for key, content in message.items():
        if not key.endswith("_MSG") or not isinstance(content, dict):
            continue
            
        msg_type = content.get("msg_type")
        if msg_type not in TD_MESSAGE_TYPES:
            _LOGGER.debug("parse_td_message: unknown msg_type '%s' in key '%s'", msg_type, key)
            continue
        
        _LOGGER.debug("parse_td_message: found TD message type=%s, area=%s", msg_type, content.get("area_id"))
        
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
    
    _LOGGER.debug("parse_td_message: no TD message found in keys: %s", list(message.keys()))
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
    
    def __init__(self, event_history_size: int = 10) -> None:
        """Initialize berth state tracker.
        
        Args:
            event_history_size: Maximum number of events to keep in history (1-50)
        """
        self._berths: dict[str, dict[str, str]] = {}  # berth_id -> {description, timestamp}
        self._event_history_size = self._validate_history_size(event_history_size)
        self._event_history: deque[dict[str, Any]] = deque(maxlen=self._event_history_size)
        self._platform_state: dict[str, dict[str, Any]] = {}  # platform_id -> {current_train, current_event, etc.}
        self._berth_to_platform: dict[str, str] = {}  # berth_key -> platform_id mapping
    
    @staticmethod
    def _validate_history_size(size: int) -> int:
        """Validate and clamp event history size.
        
        Args:
            size: Requested history size
            
        Returns:
            Validated size clamped to valid range (1-50)
        """
        return max(1, min(50, size))
    
    def set_berth_to_platform_mapping(self, mapping: dict[str, str]) -> None:
        """Set the mapping of berths to platforms.
        
        Args:
            mapping: Dictionary mapping berth keys (area:berth) to platform IDs
        """
        self._berth_to_platform = mapping.copy()
    
    def set_event_history_size(self, size: int) -> None:
        """Update the event history size.
        
        Args:
            size: New maximum number of events to keep (1-50)
        """
        new_size = self._validate_history_size(size)
        if new_size != self._event_history_size:
            self._event_history_size = new_size
            # Create new deque with new size and copy old events
            old_events = list(self._event_history)
            self._event_history = deque(old_events[-new_size:], maxlen=new_size)
    
    def _update_platform_idle(self, platform_id: str, timestamp: Any) -> None:
        """Update platform state to idle.
        
        Args:
            platform_id: Platform identifier
            timestamp: Timestamp of the state change
        """
        if platform_id:
            self._platform_state[platform_id] = {
                "platform_id": platform_id,
                "current_train": None,
                "current_event": None,
                "last_updated": timestamp,
                "status": "idle",
            }
    
    def _update_platform_active(self, platform_id: str, train_id: str, event_type: str, timestamp: Any) -> None:
        """Update platform state to active.
        
        Args:
            platform_id: Platform identifier
            train_id: Train description
            event_type: Event type (arrive, interpose, step)
            timestamp: Timestamp of the state change
        """
        if platform_id:
            self._platform_state[platform_id] = {
                "platform_id": platform_id,
                "current_train": train_id,
                "current_event": event_type,
                "last_updated": timestamp,
                "status": "active",
            }
    
    def update(self, parsed_message: dict[str, Any]) -> None:
        """Update berth state based on a TD message.
        
        Args:
            parsed_message: Parsed TD message from parse_td_message()
        """
        msg_type = parsed_message.get("msg_type")
        area_id = parsed_message.get("area_id")
        time = parsed_message.get("time")
        
        # Create event record for history
        event_record = {
            "msg_type": msg_type,
            "area_id": area_id,
            "timestamp": time,
        }
        
        if msg_type == TD_MSG_CA:
            # Berth Step: move from one berth to another
            from_berth = f"{area_id}:{parsed_message.get('from_berth')}"
            to_berth = f"{area_id}:{parsed_message.get('to_berth')}"
            description = parsed_message.get("description", "")
            
            # Add to event record
            event_record.update({
                "event_type": "step",
                "from_berth": parsed_message.get("from_berth"),
                "to_berth": parsed_message.get("to_berth"),
                "train_id": description,
            })
            
            # Get platform associations
            from_platform = self._berth_to_platform.get(from_berth)
            to_platform = self._berth_to_platform.get(to_berth)
            
            if from_platform:
                event_record["from_platform"] = from_platform
            if to_platform:
                event_record["to_platform"] = to_platform
            
            # Clear from berth
            self._berths.pop(from_berth, None)
            
            # Update platform state for departure
            self._update_platform_idle(from_platform, time)
            
            # Set to berth
            self._berths[to_berth] = {
                "description": description,
                "timestamp": time,
            }
            
            # Update platform state for arrival
            self._update_platform_active(to_platform, description, "arrive", time)
            
        elif msg_type == TD_MSG_CB:
            # Berth Cancel: remove from berth
            from_berth = f"{area_id}:{parsed_message.get('from_berth')}"
            description = parsed_message.get("description", "")
            
            # Add to event record
            event_record.update({
                "event_type": "cancel",
                "from_berth": parsed_message.get("from_berth"),
                "train_id": description,
            })
            
            # Get platform association
            from_platform = self._berth_to_platform.get(from_berth)
            if from_platform:
                event_record["platform"] = from_platform
            
            self._berths.pop(from_berth, None)
            
            # Update platform state
            self._update_platform_idle(from_platform, time)
            
        elif msg_type == TD_MSG_CC:
            # Berth Interpose: insert into berth
            to_berth = f"{area_id}:{parsed_message.get('to_berth')}"
            description = parsed_message.get("description", "")
            
            # Add to event record
            event_record.update({
                "event_type": "interpose",
                "to_berth": parsed_message.get("to_berth"),
                "train_id": description,
            })
            
            # Get platform association
            to_platform = self._berth_to_platform.get(to_berth)
            if to_platform:
                event_record["platform"] = to_platform
            
            self._berths[to_berth] = {
                "description": description,
                "timestamp": time,
            }
            
            # Update platform state
            self._update_platform_active(to_platform, description, "interpose", time)
        
        # Add event to history (only for berth operations, not heartbeats)
        if msg_type in (TD_MSG_CA, TD_MSG_CB, TD_MSG_CC):
            self._event_history.append(event_record)
    
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
    
    def get_platform_state(self, platform_id: str) -> dict[str, Any] | None:
        """Get the current state of a platform.
        
        Args:
            platform_id: Platform identifier (e.g., "1", "2A")
            
        Returns:
            Dictionary with platform state or None if no state tracked
        """
        return self._platform_state.get(platform_id)
    
    def get_all_platform_states(self) -> dict[str, dict[str, Any]]:
        """Get state for all tracked platforms.
        
        Returns:
            Dictionary mapping platform IDs to their state
        """
        return self._platform_state.copy()
    
    def get_event_history(self) -> list[dict[str, Any]]:
        """Get recent event history.
        
        Returns:
            List of event records, most recent last
        """
        return list(self._event_history)
    
    def get_event_history_size(self) -> int:
        """Get the configured event history size.
        
        Returns:
            Maximum number of events kept in history
        """
        return self._event_history_size
