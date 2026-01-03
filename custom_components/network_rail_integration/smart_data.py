"""SMART data download and management for Network Rail Integration."""

from __future__ import annotations

import base64
import gzip
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
        integration_dir = config_dir / "custom_components" / DOMAIN
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
    
    def _decompress_and_decode(self, raw_data: bytes) -> str | None:
        """Decompress gzip data if needed and decode to UTF-8.
        
        Args:
            raw_data: Raw bytes from response
            
        Returns:
            Decoded string content, or None if decompression/decoding failed
        """
        try:
            # Check if data is gzip compressed (magic bytes: 0x1f 0x8b)
            if len(raw_data) >= 2 and raw_data[0] == 0x1f and raw_data[1] == 0x8b:
                _LOGGER.debug("Data is gzip compressed, decompressing...")
                decompressed = gzip.decompress(raw_data)
                content = decompressed.decode('utf-8')
                _LOGGER.debug(
                    "Decompressed %d bytes to %d bytes",
                    len(raw_data),
                    len(decompressed)
                )
                return content
            else:
                # Not compressed, decode as UTF-8
                _LOGGER.debug("Data is not gzip compressed")
                content = raw_data.decode('utf-8')
                return content
        except gzip.error as exc:
            _LOGGER.error("Failed to decompress gzip data: %s", exc)
            return None
        except UnicodeDecodeError as exc:
            _LOGGER.error("Failed to decode data as UTF-8: %s", exc)
            return None
    
    async def refresh_data(self) -> bool:
        """Download fresh SMART data from Network Rail.
        
        Returns:
            True if data was downloaded and parsed successfully, False otherwise
        """
        try:
            _LOGGER.info("Downloading SMART data from %s", SMART_DATA_URL)
            
            # Create Basic Auth header manually to avoid aiohttp auto-sending it on redirects
            auth_string = f"{self.username}:{self.password}"
            auth_bytes = auth_string.encode('utf-8')
            auth_header = base64.b64encode(auth_bytes).decode('ascii')
            
            timeout = aiohttp.ClientTimeout(total=60)
            
            # Step 1: Request from authenticating proxy with Basic Auth, but disable auto-redirects
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"Authorization": f"Basic {auth_header}"}
                
                _LOGGER.debug("Requesting SMART data with Basic Auth (redirects disabled)")
                async with session.get(
                    SMART_DATA_URL,
                    headers=headers,
                    allow_redirects=False
                ) as response:
                    _LOGGER.debug("Initial response status: %d", response.status)
                    
                    # Check for authentication failure
                    if response.status == 401:
                        response_text = await response.text()
                        _LOGGER.error(
                            "Authentication failed when downloading SMART data (401 Unauthorized). "
                            "Response: %s",
                            response_text[:500]
                        )
                        return False
                    
                    # Check if it's a redirect
                    if response.status in (301, 302, 303, 307, 308):
                        redirect_url = response.headers.get("Location")
                        if not redirect_url:
                            _LOGGER.error("Redirect response missing Location header")
                            return False
                        
                        _LOGGER.debug("Following redirect to: %s", redirect_url)
                        
                        # Step 2: Follow redirect to S3 WITHOUT auth headers
                        async with session.get(redirect_url) as s3_response:
                            _LOGGER.debug("S3 response status: %d", s3_response.status)
                            
                            if s3_response.status != 200:
                                error_text = await s3_response.text()
                                _LOGGER.error(
                                    "Failed to download SMART data from S3: HTTP %d. Response: %s",
                                    s3_response.status,
                                    error_text[:500]
                                )
                                return False
                            
                            # Read response as bytes (may be gzip compressed)
                            raw_data = await s3_response.read()
                            _LOGGER.debug("Downloaded %d bytes from S3", len(raw_data))
                            
                            # Decompress and decode the data
                            content = self._decompress_and_decode(raw_data)
                            if content is None:
                                return False
                    
                    elif response.status == 200:
                        # No redirect, data returned directly (unlikely but handle it)
                        _LOGGER.debug("No redirect, reading data directly from initial response")
                        raw_data = await response.read()
                        
                        # Decompress and decode the data
                        content = self._decompress_and_decode(raw_data)
                        if content is None:
                            return False
                    
                    else:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Unexpected response status %d. Response: %s",
                            response.status,
                            error_text[:500]
                        )
                        return False
            
            _LOGGER.debug("Successfully retrieved SMART data, size: %d bytes", len(content))
            
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
            _LOGGER.error("Unexpected error downloading SMART data: %s", exc, exc_info=True)
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
                # Check if this is a wrapper object with BERTHDATA key
                if "BERTHDATA" in data and isinstance(data["BERTHDATA"], list):
                    berthdata = data["BERTHDATA"]
                    # Validate that BERTHDATA is not empty
                    if not berthdata:
                        _LOGGER.warning("BERTHDATA array is empty")
                        return False
                    self._data = berthdata
                    _LOGGER.debug("Parsed SMART data from BERTHDATA wrapper (%d records)", len(berthdata))
                    return True
                # Single object without BERTHDATA, wrap in list
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
