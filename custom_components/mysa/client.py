"""HTTP Client for Mysa."""
import logging
import boto3
import requests  # type: ignore[import-untyped]
from homeassistant.helpers.storage import Store
from .mysa_auth import (
    Cognito, login, auther,
    REGION, USER_POOL_ID, CLIENT_ID, JWKS,
    CLIENT_HEADERS, BASE_URL,
)
from .mysa_mqtt import refresh_and_sign_url
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
        self._session = None
        self._user_id = None  # Mysa User UUID
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.devices = {}
        self.homes = []
        self.zones = {}
        self.device_to_home = {}
        self.home_rates = {}
        self._last_command_time = {} # Shared state need? Probably passed from top level

    @property
    def is_connected(self) -> bool:
        """Return if API session is active."""
        return self._session is not None

    @property
    def user_id(self):
        """Return the user ID."""
        return self._user_id

    async def authenticate(self):
        """Authenticate with Mysa (Async)."""
        # 1. Load cached tokens
        cached_data = await self._store.async_load()

        def do_sync_login():
            bsess = boto3.session.Session(region_name=REGION)

            # Try to restore session
            if cached_data and isinstance(cached_data, dict):
                id_token = cached_data.get("id_token")
                refresh_token = cached_data.get("refresh_token")
                if id_token and refresh_token:
                    try:
                        u = Cognito(
                            user_pool_id=USER_POOL_ID,
                            client_id=CLIENT_ID,
                            id_token=id_token,
                            refresh_token=refresh_token,
                            username=self.username,
                            session=bsess,
                            pool_jwk=JWKS
                        )
                        # Verify logic
                        try:
                            u.verify_token(u.id_token, "id_token", "id")
                        except Exception:
                            # Try refresh
                            u.renew_access_token()

                        _LOGGER.debug("Restored credentials from storage")
                        return u
                    except Exception as e:
                        _LOGGER.debug("Failed to restore credentials: %s", e)

            # Fallback to Password Login
            _LOGGER.debug("Logging in with password...")
            return login(self.username, self.password, bsess=bsess)

        try:
            self._user_obj = await self.hass.async_add_executor_job(do_sync_login)
        except Exception as e:
            _LOGGER.error("Authentication failed: %s", e)
            raise

        # 2. Save tokens back to Store
        if self._user_obj:
            await self._store.async_save({
                "id_token": self._user_obj.id_token,
                "refresh_token": self._user_obj.refresh_token
            })

        # 3. Setup Requests Session
        self._session = requests.Session()
        self._session.headers.update(CLIENT_HEADERS)
        self._session.auth = auther(self._user_obj)

        # 4. Fetch User ID (needed for MQTT commands)
        try:
            r = await self.hass.async_add_executor_job(
                lambda: self._session.get(f"{BASE_URL}/users")
            )
            r.raise_for_status()
            user_data = r.json()
            self._user_id = user_data.get("User", {}).get("Id")
            _LOGGER.debug("Fetched User ID: %s", self._user_id)
        except Exception as e:
            _LOGGER.error("Failed to fetch User ID: %s", e)

        return True

    async def get_devices(self):
        """Get devices."""
        return await self.hass.async_add_executor_job(self._get_devices_sync)

    def _get_devices_sync(self):
        """Get devices synchronously from HTTP API."""
        if not self._session:
            raise RuntimeError("Session not initialized")

        url = f"{BASE_URL}/devices"
        r = self._session.get(url)
        r.raise_for_status()

        devices_raw = r.json().get('DevicesObj', [])
        if isinstance(devices_raw, list):
            self.devices = {d['Id']: d for d in devices_raw}
        else:
            self.devices = devices_raw

        # Auto-fetch homes/zones
        try:
            self._fetch_homes_sync()
        except Exception as e:
            _LOGGER.warning("Failed to fetch homes/zones: %s", e)

        return self.devices

    async def fetch_homes(self):
        """Fetch homes and zones."""
        return await self.hass.async_add_executor_job(self._fetch_homes_sync)

    def _fetch_homes_sync(self):
        """Fetch homes synchronously from HTTP API."""
        if not self._session:
            raise RuntimeError("Session not initialized")

        url = f"{BASE_URL}/homes"
        r = self._session.get(url)
        r.raise_for_status()

        data = r.json()
        self.homes = data.get('Homes', data.get('homes', []))

        self.zones = {}
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
                    # Map Devices in this zone to this home
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

        # Fallback: If device not found in mapping, try to find it via its current Zone setting
        if not home_id and device_id in self.devices:
            # We would need the device's current state to know its zone
            # This is a best effort without circular dependency on state if not passed in
            pass

        if home_id:
            return self.home_rates.get(home_id)
        return None

    def fetch_firmware_info(self, device_id):
        """Fetch firmware update info (Sync)."""
        if not self._session:
            raise RuntimeError("Session not initialized")

        url = f"{BASE_URL}/devices/update_available/{device_id}"
        try:
            r = self._session.get(url, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            _LOGGER.debug("Failed to fetch firmware info for %s: %s", device_id, e)
            return None

    async def get_state(self, current_states=None):
        """Get full state of all devices."""
        return await self.hass.async_add_executor_job(
            self._get_state_sync, current_states
        )

    def _get_state_sync(self, current_states=None):
        """Get full state (settings + live data) from HTTP API."""
        if current_states is None:
            current_states = {}

        if not self._session:
            raise RuntimeError("Session not initialized")

        # 1. Fetch live metrics
        r_state = self._session.get(f"{BASE_URL}/devices/state")
        r_state.raise_for_status()
        state_json = r_state.json()
        new_states_raw = state_json.get('DeviceStatesObj', state_json.get('DeviceStates', []))
        if isinstance(new_states_raw, list):
            new_states = {d['Id']: d for d in new_states_raw}
        else:
            new_states = new_states_raw

        # 2. Fetch device settings
        r_devices = self._session.get(f"{BASE_URL}/devices")
        r_devices.raise_for_status()
        devices_json = r_devices.json()

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

            # Since we are returning the fulll new state for the coordinator to merge,
            # we don't necessarily need to check _last_command_time here if the coordinator does it.
            # But the logic was embedded here. Let's return the simplified merge and let caller handle staleness
            # OR handle it here if we pass the timestamp dict.
            # To keep it simple, we return the fresh HTTP state. The coordinator/api class will decide whether to overwrite MQTT state.

            result_states[device_id] = new_data

        return result_states

    async def get_signed_mqtt_url(self):
        """Get signed MQTT URL with fresh credentials."""
        def _sign():
            signed_url, new_user_obj = refresh_and_sign_url(
                self._user_obj, self.username, self.password
            )
            # Update user object if it was refreshed
            if new_user_obj is not self._user_obj:
                self._user_obj = new_user_obj
                # We could save to store here but it's async...
                # For now just updating memory is fine for session continuity
            return signed_url
        return await self.hass.async_add_executor_job(_sign)

    async def set_device_setting_http(self, device_id, settings: dict):
        """Set device settings via HTTP POST."""
        if not self._session:
            raise RuntimeError("Session not initialized")
        session = self._session

        def do_post():
            url = f"{BASE_URL}/devices/{device_id}"
            r = session.post(url, json=settings)
            r.raise_for_status()
            return r.json()

        try:
            result = await self.hass.async_add_executor_job(do_post)
            _LOGGER.debug("Set device %s settings %s: %s", device_id, settings, result)
            return result
        except Exception as e:
            _LOGGER.error("Failed to set device %s settings: %s", device_id, e)
            raise

    async def async_request(self, method, url, **kwargs):
        """Perform a request using the session."""
        if not self._session:
            raise RuntimeError("Session not initialized")
        session = self._session

        def _do_req():
            resp = session.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp

        return await self.hass.async_add_executor_job(_do_req)

    async def set_device_setting_silent(self, device_id, settings: dict):
        """Set device settings via HTTP POST without raising on error (best effort)."""
        try:
            await self.set_device_setting_http(device_id, settings)
        except Exception as e:
            _LOGGER.warning(
                "HTTP sync failed for %s: %s (MQTT already sent)", device_id, e
            )
