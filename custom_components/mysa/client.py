"""HTTP Client for Mysa."""
import logging
import re
from typing import Any, Dict, List, Optional, cast
from time import time
from functools import partial
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from aiohttp import ClientSession, ClientResponse

from pycognito import Cognito
from .mysa_auth import (
    CognitoUser, login, refresh_and_sign_url,
    CLIENT_HEADERS, BASE_URL,
    USER_POOL_ID, CLIENT_ID, REGION
)
from .device import MysaDeviceLogic

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "mysa.auth"
STORAGE_VERSION = 1


class MysaClient:
    """Mysa HTTP API Client."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        websession: Optional[ClientSession] = None
    ) -> None:
        """Initialize the API."""
        self.hass = hass
        self.username = username
        self.password = password
        self.websession = websession
        self._user_obj: Optional[CognitoUser] = None
        self._user_id: Optional[str] = None  # Mysa User UUID
        self._store: Store[Dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.devices: Dict[str, Any] = {}
        self.homes: List[Any] = []
        self.device_to_home: Dict[str, str] = {}
        self.home_rates: Dict[str, float] = {}
        self._last_command_time: Dict[str, float] = {}

    @property
    def is_connected(self) -> bool:
        """Return if API session is active."""
        return self._user_obj is not None

    @property
    def user_id(self) -> Optional[str]:
        """Return the user ID."""
        return self._user_id

    async def _get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers, refreshing token if needed."""
        if not self._user_obj:
            return {}

        # Check if token needs refresh (within 5 seconds of expiry)
        # Check if token needs refresh (within 60 seconds of expiry)
        if self._user_obj.id_claims and time() > self._user_obj.id_claims.get('exp', 0) - 60:
            # Renew token (now async, no executor needed)
            await self._user_obj.renew_access_token()

        headers = dict(CLIENT_HEADERS)
        if self._user_obj.id_token:
            headers['authorization'] = self._user_obj.id_token
        return headers

    async def authenticate(self, use_cache: bool = True) -> bool:
        """Authenticate with Mysa (Async)."""
        # 1. Load cached tokens (if enabled)
        if use_cache:
            cached_data = await self._store.async_load()
        else:
            cached_data = None

        # Try to restore session from cached tokens
        if cached_data and isinstance(cached_data, dict):
            id_token = cached_data.get("id_token")
            access_token = cached_data.get("access_token")
            refresh_token = cached_data.get("refresh_token")
            if id_token and refresh_token and access_token:
                try:
                    # Create pycognito client from cached tokens in executor
                    cognito_client = await self.hass.async_add_executor_job(partial(
                        Cognito,
                        USER_POOL_ID,
                        CLIENT_ID,
                        user_pool_region=REGION,
                        username=self.username,
                        id_token=id_token,
                        access_token=access_token,
                        refresh_token=refresh_token
                    ))

                    user = CognitoUser(cognito_client)

                    # Verify token / Try refresh if needed
                    try:
                        # Pyrefly note: verify_token is a method on CognitoUser
                        await user.async_verify_token(id_token, "id")
                        _LOGGER.debug("Restored credentials from storage")
                        self._user_obj = user
                    except Exception:
                        # Try refresh
                        _LOGGER.debug("Token expired, refreshing...")
                        await user.renew_access_token()
                        self._user_obj = user
                        _LOGGER.debug("Successfully refreshed credentials")
                except Exception as e:
                    _LOGGER.debug("Failed to restore credentials: %s", e)
                    self._user_obj = None

        # Fallback to Password Login if restoration failed
        if not self._user_obj:
            _LOGGER.debug("Logging in with password...")
            try:
                self._user_obj = await login(self.username, self.password)
            except Exception as e:
                _LOGGER.error("Authentication failed: %s", e)
                raise

        # 2. Save tokens back to Store
        if self._user_obj and self._user_obj.id_token:
            await self._store.async_save({
                "id_token": self._user_obj.id_token,
                "access_token": self._user_obj.access_token,
                "refresh_token": self._user_obj.refresh_token
            })

        # 3. Fetch User ID (needed for MQTT commands)
        try:
            session = self.websession or async_get_clientsession(self.hass)
            async with session.get(
                f"{BASE_URL}/users",
                headers=await self._get_auth_headers()
            ) as resp:
                resp.raise_for_status()
                user_data = await resp.json()
                self._user_id = user_data.get("User", {}).get("Id")
                _LOGGER.debug("Fetched User ID: %s", self._user_id)
        except Exception as e:
            _LOGGER.error("Failed to fetch User ID: %s", e)
            # Don't strictly fail authentication if just USER ID fetch fails,
            # though MQTT might fail later.

        return True

    async def get_devices(self) -> Dict[str, Any]:
        """Get devices."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        url = f"{BASE_URL}/devices"

        async with session.get(url, headers=await self._get_auth_headers()) as resp:
            resp.raise_for_status()
            json_resp = await resp.json()

        devices_raw = json_resp.get('DevicesObj', json_resp.get('Devices', []))
        if isinstance(devices_raw, list):
            self.devices = {d['Id']: d for d in devices_raw}
        else:
            self.devices = devices_raw

        # Auto-fetch homes/zones
        try:
            await self.fetch_homes()
            # Filter out ghost devices (devices not assigned to any home)
            if self.devices and self.device_to_home:
                filtered_devices = {}
                for dev_id, dev in self.devices.items():
                    if dev_id in self.device_to_home:
                        filtered_devices[dev_id] = dev
                    else:
                        _LOGGER.warning(
                            "Ignoring ghost device %s (not assigned to any home)", dev_id
                        )
                self.devices = filtered_devices
        except Exception as e:
            _LOGGER.warning("Failed to fetch homes/zones: %s", e)

        return self.devices

    def _map_devices_to_homes(self, zone_to_home: Dict[str, str]) -> None:
        """Map devices to homes based on available metadata."""
        for dev_id, dev in self.devices.items():
            if dev_id in self.device_to_home:
                continue

            home_id = dev.get("Home")
            if home_id in self.home_rates:
                self.device_to_home[dev_id] = home_id
                continue

            dev_zone = dev.get('Zone')
            z_id = dev_zone.get('Id') if isinstance(dev_zone, dict) else dev_zone
            if z_id and str(z_id) in zone_to_home:
                self.device_to_home[dev_id] = zone_to_home[str(z_id)]

    async def fetch_homes(self) -> List[Any]:
        """Fetch homes and zones."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        async with session.get(f"{BASE_URL}/homes", headers=await self._get_auth_headers()) as resp:
            resp.raise_for_status()
            data = await resp.json()

        self.homes = data.get('Homes', data.get('homes', []))
        self.device_to_home = {}
        self.home_rates = {}
        zone_to_home = {}

        for home in self.homes:
            h_id = home.get('Id')
            rate = home.get('ERate')
            if h_id and rate is not None:
                try:
                    # Use regex to strip everything except digits, dots, and commas
                    clean_rate = re.sub(r'[^\d.,]', '', str(rate))
                    val = float(clean_rate.replace(',', '.'))
                    self.home_rates[h_id] = val
                except (ValueError, TypeError):
                    pass

            for zone in home.get('Zones', []):
                z_id = zone.get('Id')
                if z_id and h_id:
                    zone_to_home[z_id] = h_id
                for d_id in zone.get('DeviceIds', []):
                    self.device_to_home[d_id] = h_id

        # Fallback: Link devices via Zone ID or Home property
        self._map_devices_to_homes(zone_to_home)

        return self.homes

    def get_electricity_rate(self, device_id: str) -> Optional[float]:
        """Get electricity rate for a device based on its home."""
        # Check explicit device mapping first
        home_id = self.device_to_home.get(device_id)

        if home_id:
            return self.home_rates.get(home_id)
        return None

    async def fetch_firmware_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Fetch firmware update info."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        url = f"{BASE_URL}/devices/update_available/{device_id}"

        try:
            async with session.get(
                url,
                headers=await self._get_auth_headers()
            ) as resp:
                resp.raise_for_status()
                return cast(Optional[Dict[str, Any]], await resp.json())
        except Exception as e:
            _LOGGER.debug("Failed to fetch firmware info for %s: %s", device_id, e)
            return None

    async def get_state(self, current_states: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get full state of all devices."""
        if current_states is None:
            current_states = {}

        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)

        # 1. Fetch live metrics
        async with session.get(
            f"{BASE_URL}/devices/state",
            headers=await self._get_auth_headers()
        ) as resp:
            resp.raise_for_status()
            state_json = await resp.json()

        new_states_raw = state_json.get('DeviceStatesObj', state_json.get('DeviceStates', []))
        if isinstance(new_states_raw, list):
            new_states = {d['Id']: d for d in new_states_raw}
        else:
            new_states = new_states_raw

        # 2. Refresh homes/zones (to keep ERate updated)
        try:
            await self.fetch_homes()
        except Exception as e:
            _LOGGER.debug("Failed to refresh homes/zones in get_state: %s", e)

        # 3. Fetch device settings
        async with session.get(
            f"{BASE_URL}/devices",
            headers=await self._get_auth_headers()
        ) as resp:
            resp.raise_for_status()
            devices_json = await resp.json()

        devices_raw = devices_json.get('DevicesObj', devices_json.get('Devices', []))
        if isinstance(devices_raw, list):
            self.devices = {d['Id']: d for d in devices_raw}
        else:
            self.devices = devices_raw

        # Merge
        result_states = {}

        for device_id, live_data in new_states.items():
            new_data = live_data
            if device_id in self.devices:
                dev_info = self.devices[device_id].copy()
                if "Attributes" in dev_info and isinstance(dev_info["Attributes"], dict):
                    dev_info.update(dev_info["Attributes"])
                dev_info.update(live_data)
                new_data = dev_info

            MysaDeviceLogic.normalize_state(new_data)
            result_states[device_id] = new_data

        return result_states

    async def get_signed_mqtt_url(self) -> str:
        """Get signed MQTT URL with fresh credentials."""
        if not self._user_obj:
            raise RuntimeError("Not authenticated")

        signed_url, new_user_obj = await refresh_and_sign_url(self._user_obj)

        # Update user object if it was refreshed
        if new_user_obj is not self._user_obj:
            self._user_obj = new_user_obj

        return signed_url

    async def set_device_setting_http(self, device_id: str, settings: Dict[str, Any]) -> Any:
        """Set device settings via HTTP POST."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        url = f"{BASE_URL}/devices/{device_id}"

        try:
            async with session.post(
                url,
                json=settings,
                headers=await self._get_auth_headers()
            ) as resp:
                resp.raise_for_status()
                result = await resp.json()
                _LOGGER.debug("Set device %s settings %s: %s", device_id, settings, result)
                return result
        except Exception as e:
            _LOGGER.error("Failed to set device %s settings: %s", device_id, e)
            raise

    async def async_request(self, method: str, url: str, **kwargs: Any) -> "ClientResponse":
        """Perform a request using the session."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        headers = kwargs.pop('headers', {})
        headers.update(await self._get_auth_headers())

        async with session.request(method, url, headers=headers, **kwargs) as resp:
            resp.raise_for_status()
            return resp

    async def set_device_setting_silent(self, device_id: str, settings: Dict[str, Any]) -> None:
        """Set device settings via HTTP POST without raising on error (best effort)."""
        try:
            await self.set_device_setting_http(device_id, settings)
        except Exception as e:
            _LOGGER.warning(
                "HTTP sync failed for %s: %s (MQTT already sent)", device_id, e
            )
