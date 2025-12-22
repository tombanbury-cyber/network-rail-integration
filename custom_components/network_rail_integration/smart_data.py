"""SMART data download and management for Network Rail Integration."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant

from .const import SMART_CACHE_EXPIRY_DAYS, SMART_CACHE_FILE, SMART_DATA_URL

_LOGGER = logging.getLogger(__name__)


class SmartDataManager:
    """Manages SMART data download, caching, and parsing."""

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        """Initialize SMART data manager.
        
        Args:
            hass: Home Assistant instance
            username: Network Rail username
            password: Network Rail password
        """
        self.hass = hass
        self.username = username
        self.password = password
        self._data: list[dict[str, Any]] = []
        self._graph: dict[str, Any] = {}
        self._last_updated: datetime | None = None
        
        # Cache file path in integration directory
        config_dir = Path(hass.config.path())
        integration_dir = config_dir / "custom_components" / "network_rail_integration"
        self.cache_path = integration_dir / SMART_CACHE_FILE
        
    async def load_data(self) -> bool:
        """Load SMART data from cache or download if needed.
        
        Returns:
            True if data was loaded successfully, False otherwise
        """
        # Try to load from cache first
        if await self._load_from_cache():
            _LOGGER.info("Loaded SMART data from cache (%d records)", len(self._data))
            return True
        
        # Cache is stale or doesn't exist, download fresh data
        _LOGGER.info("SMART data cache is stale or missing, downloading fresh data")
        return await self.refresh_data()
    
    async def refresh_data(self) -> bool:
        """Download fresh SMART data from Network Rail.
        
        Returns:
            True if data was downloaded and parsed successfully, False otherwise
        """
        try:
            _LOGGER.info("Downloading SMART data from %s", SMART_DATA_URL)
            
            auth = aiohttp.BasicAuth(self.username, self.password)
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(auth=auth, timeout=timeout) as session:
                async with session.get(SMART_DATA_URL) as response:
                    if response.status == 401:
                        _LOGGER.error("Authentication failed when downloading SMART data (401 Unauthorized)")
                        return False
                    elif response.status != 200:
                        _LOGGER.error("Failed to download SMART data: HTTP %d", response.status)
                        return False
                    
                    content = await response.text()
                    _LOGGER.debug("Downloaded %d bytes of SMART data", len(content))
            
            # Parse the data
            if not self._parse_smart_data(content):
                _LOGGER.error("Failed to parse SMART data")
                return False
            
            # Build the graph structure
            self._build_graph()
            
            # Save to cache
            self._last_updated = datetime.now(timezone.utc)
            await self._save_to_cache(content)
            
            _LOGGER.info("Successfully downloaded and cached SMART data (%d records)", len(self._data))
            return True
            
        except aiohttp.ClientError as exc:
            _LOGGER.error("Network error downloading SMART data: %s", exc)
            return False
        except Exception as exc:
            _LOGGER.error("Unexpected error downloading SMART data: %s", exc)
            return False
    
    def _parse_smart_data(self, content: str) -> bool:
        """Parse SMART data from JSON or newline-delimited JSON.
        
        Args:
            content: Raw content from SMART data file
            
        Returns:
            True if parsing succeeded, False otherwise
        """
        self._data = []
        
        try:
            # Try to parse as JSON array first
            data = json.loads(content)
            if isinstance(data, list):
                self._data = data
                _LOGGER.debug("Parsed SMART data as JSON array")
                return True
            elif isinstance(data, dict):
                # Single object, wrap in list
                self._data = [data]
                _LOGGER.debug("Parsed SMART data as single JSON object")
                return True
        except json.JSONDecodeError:
            # Not a JSON array, try newline-delimited JSON
            _LOGGER.debug("Content is not a JSON array, trying newline-delimited JSON")
        
        # Try newline-delimited JSON
        try:
            for line in content.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    self._data.append(obj)
            
            if self._data:
                _LOGGER.debug("Parsed SMART data as newline-delimited JSON")
                return True
        except json.JSONDecodeError as exc:
            _LOGGER.error("Failed to parse SMART data as newline-delimited JSON: %s", exc)
            return False
        
        _LOGGER.error("SMART data is empty or in unrecognized format")
        return False
    
    def _build_graph(self) -> None:
        """Build efficient in-memory graph structure for querying."""
        self._graph = {
            "berth_to_connections": {},  # berth_key -> {"from": [...], "to": [...]}
            "stanox_to_berths": {},      # stanox -> [berth_info, ...]
            "berth_to_stanox": {},       # berth_key -> stanox
        }
        
        for record in self._data:
            td_area = record.get("TD", "").strip()
            from_berth = record.get("FROMBERTH", "").strip()
            to_berth = record.get("TOBERTH", "").strip()
            stanox = record.get("STANOX", "").strip()
            stanme = record.get("STANME", "").strip()
            steptype = record.get("STEPTYPE", "").strip()
            event = record.get("EVENT", "").strip()
            platform = record.get("PLATFORM", "").strip()
            from_line = record.get("FROMLINE", "").strip()
            to_line = record.get("TOLINE", "").strip()
            
            # Build berth connections
            if td_area and from_berth and to_berth:
                from_key = f"{td_area}:{from_berth}"
                to_key = f"{td_area}:{to_berth}"
                
                # Add "to" connection for from_berth
                if from_key not in self._graph["berth_to_connections"]:
                    self._graph["berth_to_connections"][from_key] = {"from": [], "to": []}
                self._graph["berth_to_connections"][from_key]["to"].append({
                    "berth": to_berth,
                    "td_area": td_area,
                    "line": to_line,
                    "steptype": steptype,
                })
                
                # Add "from" connection for to_berth
                if to_key not in self._graph["berth_to_connections"]:
                    self._graph["berth_to_connections"][to_key] = {"from": [], "to": []}
                self._graph["berth_to_connections"][to_key]["from"].append({
                    "berth": from_berth,
                    "td_area": td_area,
                    "line": from_line,
                    "steptype": steptype,
                })
            
            # Build STANOX to berths mapping
            if stanox:
                if stanox not in self._graph["stanox_to_berths"]:
                    self._graph["stanox_to_berths"][stanox] = []
                
                # Add berth info for this STANOX
                berth_info = {
                    "td_area": td_area,
                    "from_berth": from_berth,
                    "to_berth": to_berth,
                    "stanme": stanme,
                    "platform": platform,
                    "event": event,
                    "steptype": steptype,
                }
                self._graph["stanox_to_berths"][stanox].append(berth_info)
                
                # Build reverse mapping (berth -> STANOX)
                if from_berth and td_area:
                    berth_key = f"{td_area}:{from_berth}"
                    self._graph["berth_to_stanox"][berth_key] = stanox
                if to_berth and td_area:
                    berth_key = f"{td_area}:{to_berth}"
                    self._graph["berth_to_stanox"][berth_key] = stanox
        
        _LOGGER.debug(
            "Built SMART graph: %d berth connections, %d STANOX entries",
            len(self._graph["berth_to_connections"]),
            len(self._graph["stanox_to_berths"])
        )
    
    async def _load_from_cache(self) -> bool:
        """Load SMART data from cache file.
        
        Returns:
            True if cache is valid and loaded, False otherwise
        """
        if not self.cache_path.exists():
            _LOGGER.debug("SMART cache file does not exist: %s", self.cache_path)
            return False
        
        try:
            # Check cache age
            mtime = os.path.getmtime(self.cache_path)
            cache_age = datetime.now(timezone.utc) - datetime.fromtimestamp(mtime, timezone.utc)
            
            if cache_age > timedelta(days=SMART_CACHE_EXPIRY_DAYS):
                _LOGGER.debug("SMART cache is expired (age: %s)", cache_age)
                return False
            
            # Load and parse cache
            with open(self.cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            
            timestamp_str = cache_data.get("timestamp")
            if timestamp_str:
                self._last_updated = datetime.fromisoformat(timestamp_str)
            
            content = cache_data.get("content", "")
            if not content:
                _LOGGER.warning("SMART cache file is missing content")
                return False
            
            # Parse the cached content
            if not self._parse_smart_data(content):
                _LOGGER.warning("Failed to parse cached SMART data")
                return False
            
            # Build the graph
            self._build_graph()
            
            _LOGGER.debug("Loaded SMART data from cache (age: %s)", cache_age)
            return True
            
        except Exception as exc:
            _LOGGER.warning("Failed to load SMART data from cache: %s", exc)
            return False
    
    async def _save_to_cache(self, content: str) -> None:
        """Save SMART data to cache file.
        
        Args:
            content: Raw SMART data content to cache
        """
        try:
            # Ensure directory exists
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            cache_data = {
                "timestamp": self._last_updated.isoformat() if self._last_updated else None,
                "content": content,
            }
            
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f)
            
            _LOGGER.debug("Saved SMART data to cache: %s", self.cache_path)
            
        except Exception as exc:
            _LOGGER.error("Failed to save SMART data to cache: %s", exc)
    
    def get_graph(self) -> dict[str, Any]:
        """Get the parsed SMART graph structure.
        
        Returns:
            Dictionary with berth connections and STANOX mappings
        """
        return self._graph
    
    def get_last_updated(self) -> datetime | None:
        """Get the timestamp when SMART data was last updated.
        
        Returns:
            Datetime of last update, or None if never updated
        """
        return self._last_updated
    
    def is_available(self) -> bool:
        """Check if SMART data is available.
        
        Returns:
            True if data is loaded, False otherwise
        """
        return len(self._data) > 0
