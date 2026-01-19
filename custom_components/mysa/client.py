"""HTTP Client for Mysa."""
import logging
from time import time
from homeassistant.helpers.storage import Store
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .mysa_auth import (
    CognitoUser, login, refresh_and_sign_url,
    CLIENT_HEADERS, BASE_URL,
)
from .device import MysaDeviceLogic

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "mysa.auth"
STORAGE_VERSION = 1


class MysaClient:
    """Mysa HTTP API Client."""

    def __init__(self, hass, username, password):
        """Initialize the API."""
        self.hass = hass
        self.username = username
        self.password = password
        self._user_obj = None
        self._user_id = None  # Mysa User UUID
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.devices = {}
        self.homes = []
        self.zones = {}
        self.zone_to_home = {}
        self.device_to_home = {}
        self.home_rates = {}
        self._last_command_time = {}

    @property
    def is_connected(self) -> bool:
        """Return if API session is active."""
        return self._user_obj is not None

    @property
    def user_id(self):
        """Return the user ID."""
        return self._user_id

    async def _get_auth_headers(self) -> dict:
        """Get authorization headers, refreshing token if needed."""
        if not self._user_obj:
            return {}

        # Check if token needs refresh (within 5 seconds of expiry)
        # pylint: disable=unsubscriptable-object
        if self._user_obj.id_claims and time() > self._user_obj.id_claims['exp'] - 5:
            # Renew token (now async, no executor needed)
            await self._user_obj.renew_access_token()

        headers = dict(CLIENT_HEADERS)
        if self._user_obj.id_token:
            headers['authorization'] = self._user_obj.id_token
        return headers

    async def authenticate(self):
        """Authenticate with Mysa (Async)."""
        # 1. Load cached tokens
        cached_data = await self._store.async_load()

        # Try to restore session from cached tokens
        if cached_data and isinstance(cached_data, dict):
            id_token = cached_data.get("id_token")
            access_token = cached_data.get("access_token")
            refresh_token = cached_data.get("refresh_token")
            if id_token and refresh_token and access_token:
                try:
                    # Create user object from cached tokens
                    user = CognitoUser(
                        username=self.username,
                        id_token=id_token,
                        access_token=access_token,
                        refresh_token=refresh_token
                    )
                    # Verify token
                    try:
                        user.verify_token(user.id_token, "id")
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
        if self._user_obj:
            await self._store.async_save({
                "id_token": self._user_obj.id_token,
                "access_token": self._user_obj.access_token,
                "refresh_token": self._user_obj.refresh_token
            })

        # 3. Fetch User ID (needed for MQTT commands)
        try:
            session = async_get_clientsession(self.hass)
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

        return True

    async def get_devices(self):
        """Get devices."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = async_get_clientsession(self.hass)
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

    async def fetch_homes(self):
        """Fetch homes and zones."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = async_get_clientsession(self.hass)
        url = f"{BASE_URL}/homes"

        async with session.get(url, headers=await self._get_auth_headers()) as resp:
            resp.raise_for_status()
            data = await resp.json()

        self.homes = data.get('Homes', data.get('homes', []))

        self.zones = {}
        self.zone_to_home = {}
        self.device_to_home = {}
        self.home_rates = {}

        for home in self.homes:
            h_id = home.get('Id')
            # Parse ERate
            e_rate = home.get('ERate')
            if h_id and e_rate is not None:
                try:
                    self.home_rates[h_id] = float(e_rate)
                except (ValueError, TypeError):
                    pass

            for zone in home.get('Zones', []):
                z_id = zone.get('Id')
                z_name = zone.get('Name')
                if z_id:
                    if z_name:
                        self.zones[z_id] = z_name
                    # Map zone to home for reverse lookup
                    self.zone_to_home[z_id] = h_id
                    # Map Devices in this zone to this home (if available)
                    for d_id in zone.get('DeviceIds', []):
                        self.device_to_home[d_id] = h_id

        return self.homes

    def get_zone_name(self, zone_id):
        """Get friendly name for a zone ID."""
        return self.zones.get(zone_id)

    def get_electricity_rate(self, device_id):
        """Get electricity rate for a device based on its home."""
        # Check explicit device mapping first (from Zone->DeviceIds)
        home_id = self.device_to_home.get(device_id)

        # Fallback: Find home via device's Zone setting
        if not home_id and device_id in self.devices:
            device = self.devices[device_id]
            # Check device's Zone attribute
            zone_id = device.get('Zone')
            if zone_id:
                home_id = self.zone_to_home.get(zone_id)

        if home_id:
            return self.home_rates.get(home_id)
        return None

    async def fetch_firmware_info(self, device_id):
        """Fetch firmware update info."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = async_get_clientsession(self.hass)
        url = f"{BASE_URL}/devices/update_available/{device_id}"

        try:
            async with session.get(
                url,
                headers=await self._get_auth_headers()
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as e:
            _LOGGER.debug("Failed to fetch firmware info for %s: %s", device_id, e)
            return None

    async def get_state(self, current_states=None):
        """Get full state of all devices."""
        if current_states is None:
            current_states = {}

        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = async_get_clientsession(self.hass)

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

        # 2. Fetch device settings
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

    async def get_signed_mqtt_url(self):
        """Get signed MQTT URL with fresh credentials."""
        if not self._user_obj:
            raise RuntimeError("Not authenticated")

        signed_url, new_user_obj = await refresh_and_sign_url(self._user_obj)

        # Update user object if it was refreshed
        if new_user_obj is not self._user_obj:
            self._user_obj = new_user_obj

        return signed_url

    async def set_device_setting_http(self, device_id, settings: dict):
        """Set device settings via HTTP POST."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = async_get_clientsession(self.hass)
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

    async def async_request(self, method, url, **kwargs):
        """Perform a request using the session."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = async_get_clientsession(self.hass)
        headers = kwargs.pop('headers', {})
        headers.update(await self._get_auth_headers())

        async with session.request(method, url, headers=headers, **kwargs) as resp:
            resp.raise_for_status()
            return resp

    async def set_device_setting_silent(self, device_id, settings: dict):
        """Set device settings via HTTP POST without raising on error (best effort)."""
        try:
            await self.set_device_setting_http(device_id, settings)
        except Exception as e:
            _LOGGER.warning(
                "HTTP sync failed for %s: %s (MQTT already sent)", device_id, e
            )
