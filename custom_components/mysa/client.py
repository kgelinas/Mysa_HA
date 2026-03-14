"""HTTP Client for Mysa."""

import asyncio
import json
import logging
import re
from functools import partial
from time import time
from typing import Any, cast

from aiohttp import ClientResponse, ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from pycognito import Cognito

from .device import MysaDeviceLogic
from .mysa_auth import (
    BASE_URL,
    CLIENT_HEADERS,
    CLIENT_ID,
    CREDENTIALS_VERSION,
    LEGACY_BASE_URL,
    REGION,
    USER_POOL_ID,
    CognitoUser,
    login,
    refresh_and_sign_url,
)

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
        websession: ClientSession | None = None,
    ) -> None:
        """Initialize the API."""
        self.hass = hass
        self.username = username
        self.password = password
        self.websession = websession
        self._user_obj: CognitoUser | None = None
        self._user_id: str | None = None  # Mysa User UUID
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.devices: dict[str, Any] = {}
        self.homes: list[Any] = []
        self.device_to_home: dict[str, str] = {}
        self.home_rates: dict[str, float] = {}
        self._last_command_time: dict[str, float] = {}

    @property
    def is_connected(self) -> bool:
        """Return if API session is active."""
        return self._user_obj is not None

    @property
    def user_id(self) -> str | None:
        """Return the user ID."""
        return self._user_id

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers, refreshing token if needed."""
        if not self._user_obj:
            return {}

        # Check if token needs refresh (within 60 seconds of expiry)
        if (
            self._user_obj.id_claims
            and time() > self._user_obj.id_claims.get("exp", 0) - 60
        ):
            # Renew token (now async, no executor needed)
            await self._user_obj.renew_access_token()

        headers = dict(CLIENT_HEADERS)
        if self._user_obj.id_token:
            headers["authorization"] = self._user_obj.id_token
        return headers

    async def authenticate(self, use_cache: bool = True) -> bool:
        """Authenticate with Mysa (Async)."""
        # 1. Try to restore session from cached tokens
        if use_cache:
            self._user_obj = await self._restore_cached_session()

        # 2. Fetch User ID (needed for MQTT commands)
        if self._user_obj:
            # For restored session, clear on fail to trigger password fallback
            await self._fetch_user_id_internal(clear_on_fail=True)

        # 3. Save tokens if we still have a session (might have been refreshed)
        if self._user_obj and self._user_obj.id_token:
            await self._store_async_save_current_tokens()

        # 4. Fallback to Password Login if restoration failed OR tokens were rejected
        if not self._user_obj:
            await self._login_with_password()

        return True

    async def _restore_cached_session(self) -> CognitoUser | None:
        """Try to restore session from cached tokens."""
        cached_data = await self._store.async_load()
        if not cached_data or not isinstance(cached_data, dict):
            return None

        # Check credential version compatibility
        stored_version = cached_data.get("credentials_version")
        if stored_version != CREDENTIALS_VERSION:
            _LOGGER.info(
                "Credential version mismatch (stored: %s, current: %s). "
                "Clearing cached credentials.",
                stored_version,
                CREDENTIALS_VERSION,
            )
            await self._store.async_save({})
            return None

        id_token = cached_data.get("id_token")
        access_token = cached_data.get("access_token")
        refresh_token = cached_data.get("refresh_token")
        if not (id_token and refresh_token and access_token):
            return None

        try:
            # Create pycognito client in executor
            cognito_client = await self.hass.async_add_executor_job(
                partial(
                    Cognito,
                    USER_POOL_ID,
                    CLIENT_ID,
                    user_pool_region=REGION,
                    username=self.username,
                    id_token=id_token,
                    access_token=access_token,
                    refresh_token=refresh_token,
                )
            )

            user = CognitoUser(cognito_client)

            # Verify token / Try refresh if needed
            try:
                await user.async_verify_token(id_token, "id")
                _LOGGER.debug("Restored credentials from storage")
                return user
            except Exception:
                _LOGGER.debug("Token expired, refreshing...")
                await user.renew_access_token()
                _LOGGER.debug("Successfully refreshed credentials")
                return user
        except Exception as e:
            _LOGGER.debug("Failed to restore credentials: %s", e)
            return None

    async def _login_with_password(self) -> None:
        """Login with username/password and save tokens."""
        _LOGGER.debug("Logging in with password...")
        try:
            self._user_obj = await login(self.username, self.password)
            # After fresh login, try fetching User ID (don't clear on fail)
            try:
                await self._fetch_user_id_internal(clear_on_fail=False)
            except Exception as e:
                _LOGGER.error("Failed to fetch User ID after fresh login: %s", e)

            # Save new tokens
            if self._user_obj and self._user_obj.id_token:
                await self._store_async_save_current_tokens()
        except Exception as e:
            _LOGGER.error("Authentication failed: %s", e)
            raise

    async def _fetch_user_id_internal(self, clear_on_fail: bool = True) -> None:
        """Fetch User ID using current session."""
        if not self._user_obj:
            return

        try:
            session = self.websession or async_get_clientsession(self.hass)
            async with session.get(
                f"{BASE_URL}/users", headers=await self._get_auth_headers()
            ) as resp:
                if resp.status == 401:
                    _LOGGER.warning("Tokens rejected by backend (401).")
                    if clear_on_fail:
                        self._user_obj = None
                        self._user_id = None
                else:
                    resp.raise_for_status()
                    user_data = await resp.json()
                    self._user_id = user_data.get("User", {}).get("Id")
                    _LOGGER.debug("Fetched User ID: %s", self._user_id)
        except Exception as e:
            _LOGGER.error("Failed to fetch User ID: %s", e)
            if clear_on_fail:
                _LOGGER.warning("Clearing session due to fetch failure.")
                self._user_obj = None
                self._user_id = None

    async def _store_async_save_current_tokens(self) -> None:
        """Save current tokens to store."""
        if self._user_obj and self._user_obj.id_token:
            await self._store.async_save(
                {
                    "credentials_version": CREDENTIALS_VERSION,
                    "id_token": self._user_obj.id_token,
                    "access_token": self._user_obj.access_token,
                    "refresh_token": self._user_obj.refresh_token,
                }
            )

    async def get_devices(self) -> dict[str, Any]:
        """Get devices."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        async def fetch_devices() -> dict[str, Any]:
            session = self.websession or async_get_clientsession(self.hass)
            url = f"{BASE_URL}/devices"
            async with session.get(url, headers=await self._get_auth_headers()) as resp:
                resp.raise_for_status()
                return cast(dict[str, Any], await resp.json())

        results = await asyncio.gather(
            fetch_devices(), self.fetch_homes(), return_exceptions=True
        )

        devices_json = results[0]
        if isinstance(devices_json, BaseException):
            _LOGGER.error("Failed to fetch devices: %s", devices_json)
            raise devices_json

        devices_raw = devices_json.get("DevicesObj", devices_json.get("Devices", []))
        if isinstance(devices_raw, list):
            self.devices = {d["Id"]: d for d in devices_raw}
        elif isinstance(devices_raw, dict):
            self.devices = devices_raw
        else:
            self.devices = {}

        # Filter out ghost devices
        if self.devices and self.device_to_home:
            for dev_id in self.devices:
                if dev_id not in self.device_to_home:
                    # Log but don't exclude anymore, as users may have valid unassigned devices
                    _LOGGER.debug(
                        "Device %s not assigned to any home (allowing as 'Unassigned')",
                        dev_id,
                    )
                    # Optionally assign a default home name for UI grouping if needed
                    # self.device_to_home[dev_id] = "Unassigned"

        return self.devices

    async def post_state_update(self, device_id: str, payload: dict[str, Any]) -> None:
        """Send state update via HTTP POST."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        # Use backend URL: /state/{device_id}/update
        url = f"{BASE_URL}/state/{device_id}/update"
        _LOGGER.debug("Sending HTTP POST update to %s: %s", url, payload)
        async with session.post(
            url, json=payload, headers=await self._get_auth_headers()
        ) as resp:
            resp.raise_for_status()
            _LOGGER.debug("HTTP POST update successful")

    async def fetch_capabilities(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device capabilities from HTTP endpoint."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        url = f"{BASE_URL}/capabilities/{device_id}"
        try:
            async with session.get(url, headers=await self._get_auth_headers()) as resp:
                resp.raise_for_status()
                return cast(dict[str, Any], await resp.json())
        except Exception as e:
            _LOGGER.debug("Failed to fetch capabilities for %s: %s", device_id, e)
            return None

    def _map_devices_to_homes(self, zone_to_home: dict[str, str]) -> None:
        """Map devices to homes based on available metadata."""
        for dev_id, dev in self.devices.items():
            if dev_id in self.device_to_home:
                continue

            home_id = dev.get("Home")
            if home_id in self.home_rates:
                self.device_to_home[dev_id] = home_id
                continue

            dev_zone = dev.get("Zone")
            z_id = dev_zone.get("Id") if isinstance(dev_zone, dict) else dev_zone
            if z_id and str(z_id) in zone_to_home:
                self.device_to_home[dev_id] = zone_to_home[str(z_id)]

    async def fetch_homes(self) -> list[Any]:
        """Fetch homes and zones."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        async with session.get(
            f"{BASE_URL}/homes", headers=await self._get_auth_headers()
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

        self.homes = data.get("Homes", data.get("homes", []))
        self.device_to_home = {}
        self.home_rates = {}
        zone_to_home = {}

        for home in self.homes:
            h_id = home.get("Id")
            rate = home.get("ERate")
            if h_id and rate is not None:
                try:
                    # Use regex to strip everything except digits, dots, and commas
                    clean_rate = re.sub(r"[^\d.,]", "", str(rate))
                    val = float(clean_rate.replace(",", "."))
                    self.home_rates[h_id] = val
                except (ValueError, TypeError):
                    pass

            for zone in home.get("Zones", []):
                z_id = zone.get("Id")
                if z_id and h_id:
                    zone_to_home[z_id] = h_id
                for d_id in zone.get("DeviceIds", []):
                    self.device_to_home[d_id] = h_id

        # Fallback: Link devices via Zone ID or Home property
        self._map_devices_to_homes(zone_to_home)

        return self.homes

    def get_electricity_rate(self, device_id: str) -> float | None:
        """Get electricity rate for a device based on its home."""
        # Check explicit device mapping first
        home_id = self.device_to_home.get(device_id)

        if home_id:
            return self.home_rates.get(home_id)
        return None

    async def fetch_firmware_info(self, device_id: str) -> dict[str, Any] | None:
        """Fetch firmware update info."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        url = f"{BASE_URL}/devices/update_available/{device_id}"

        try:
            async with session.get(url, headers=await self._get_auth_headers()) as resp:
                resp.raise_for_status()
                return cast(dict[str, Any] | None, await resp.json())
        except Exception as e:
            _LOGGER.debug("Failed to fetch firmware info for %s: %s", device_id, e)
            return None

    async def get_all_firmware_versions(self) -> dict[str, Any]:
        """Fetch all firmware versions at once via legacy endpoint."""
        if not self._user_obj:
            return {}

        session = self.websession or async_get_clientsession(self.hass)
        url = f"{LEGACY_BASE_URL}/devices/firmware"

        try:
            async with session.get(url, headers=await self._get_auth_headers()) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return cast(dict[str, Any], data.get("Firmware", {}))
        except Exception as e:
            _LOGGER.debug("Failed to fetch all firmware versions: %s", e)
            return {}

    # Justification: Processing states for multiple devices and structures
    # requires several branches.
    async def get_state(  # pylint: disable=too-many-branches
        self, current_states: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Get full state of all devices."""
        if current_states is None:
            current_states = {}

        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)

        # Parallelize independent HTTP calls
        async def fetch_live_metrics() -> dict[str, Any]:
            # Use legacy API for /devices/state (doesn't exist on new backend)
            async with session.get(
                "https://app-prod.mysa.cloud/devices/state",
                headers=await self._get_auth_headers(),
            ) as resp:
                resp.raise_for_status()
                return cast(dict[str, Any], await resp.json())

        async def fetch_device_settings() -> dict[str, Any]:
            async with session.get(
                f"{BASE_URL}/devices", headers=await self._get_auth_headers()
            ) as resp:
                resp.raise_for_status()
                return cast(dict[str, Any], await resp.json())

        # Round 1: Discovery & Basic State
        # We fetch settings and live metrics first to ensure we have the device list
        # and base state before deciding which devices to query for batch telemetry.
        results_r1 = await asyncio.gather(
            fetch_live_metrics(),
            fetch_device_settings(),
            self.fetch_homes(),
            return_exceptions=True,
        )

        # Process Round 1 Results
        state_json = results_r1[0]
        if isinstance(state_json, BaseException):
            _LOGGER.error("Failed to fetch live metrics: %s", state_json)
            raise state_json

        devices_json = results_r1[1]
        if isinstance(devices_json, BaseException):
            _LOGGER.error("Failed to fetch device settings: %s", devices_json)
            raise devices_json

        new_states_raw = state_json.get(
            "DeviceStatesObj", state_json.get("DeviceStates", [])
        )
        if isinstance(new_states_raw, list):
            new_states = {d["Id"]: d for d in new_states_raw}
        elif isinstance(new_states_raw, dict):
            new_states = new_states_raw
        else:
            new_states = {}

        devices_raw = devices_json.get("DevicesObj", devices_json.get("Devices", []))
        if isinstance(devices_raw, list):
            self.devices = {d["Id"]: d for d in devices_raw}
        elif isinstance(devices_raw, dict):
            self.devices = devices_raw
        else:
            self.devices = {}

        # Round 2: Batch Telemetry (ST1 / All Devices)
        # Now that self.devices is populated, we can target them.
        # We query ALL devices to allow the backend to decide what data to return.
        # This supports ST1 and potentially other device types discovered later.
        target_ids = list(self.devices.keys())
        st1_states = {}

        if target_ids:
            try:
                st1_states = await self.get_st1_state(target_ids)
            except Exception as e:
                _LOGGER.debug("Failed to fetch batch telemetry (R2): %s", e)

        # Merge standard states
        result_states = self._merge_and_normalize_states(new_states)

        # Merge ST1/Batch states
        if st1_states:
            self._merge_st1_states(result_states, st1_states)

        return result_states

    def _merge_st1_states(
        self, result_states: dict[str, Any], st1_batch: dict[str, Any]
    ) -> None:
        """Merge ST1 batch telemetry into result states."""
        for device_id, device_payload in st1_batch.items():
            if device_id not in result_states:
                # Provide base if missing from standard poll
                result_states[device_id] = self.devices.get(device_id, {}).copy()

            data = device_payload.get("data", {})

            # 1. Flatten latestTelemetry
            telemetry = data.get("latestTelemetry", {})
            result_states[device_id].update(telemetry)

            # Flatten 'reading' if present (contains actual values)
            if "reading" in telemetry:
                result_states[device_id].update(telemetry["reading"])

            # 2. Extract hvacStates from modes
            modes = data.get("modes", {})
            reported = modes.get("reported", {})
            hvac_states = reported.get("hvacStates")
            if hvac_states:
                result_states[device_id]["hvacStates"] = hvac_states

            # 3. Extract other useful reported sections
            for section in [
                "diagnostics",
                "hvacConfig",
                "identity",
                "physicalInterface",
            ]:
                section_data = data.get(section, {})
                section_reported = section_data.get("reported", {})
                if section_reported:
                    result_states[device_id].update(section_reported)

            # 4. Re-normalize to process these new fields
            # We explicitly call the ST-V1 extractor again
            # self._extract_stv10_shadow_data is logic in MysaApi, not MysaClient
            # Wait, this method is in MysaClient. MysaApi logic is separate.
            # MysaClient should just return data. MysaApi does the logic.
            # BUT: _merge_and_normalize_states calls MysaDeviceLogic.normalize_state

            # Since we are in MysaClient, we just prepare the dict.
            # MysaDeviceLogic.normalize_state will be called by consumer?
            # No, get_state calls it.

            # Re-run normalization on this device
            MysaDeviceLogic.normalize_state(result_states[device_id])

    def _merge_and_normalize_states(self, new_states: dict[str, Any]) -> dict[str, Any]:
        """Merge new states with device info and normalize."""
        result_states = {}
        for device_id, live_data in new_states.items():
            new_data = live_data
            if device_id in self.devices:
                dev_info = self.devices[device_id].copy()
                if "Attributes" in dev_info and isinstance(
                    dev_info["Attributes"], dict
                ):
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

    async def set_device_setting_http(
        self, device_id: str, settings: dict[str, Any], legacy: bool = False
    ) -> Any:
        """Set device settings via HTTP POST."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        base = LEGACY_BASE_URL if legacy else BASE_URL
        url = f"{base}/devices/{device_id}"
        if legacy:
            url = url.rstrip("/") + "/"  # Legacy API often requires trailing slash

        try:
            async with session.post(
                url, json=settings, headers=await self._get_auth_headers()
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
                # Bypassing aiohttp's strict Content-Type check
                result = {} if not text else json.loads(text)

                _LOGGER.debug(
                    "Set device %s settings %s: %s", device_id, settings, result
                )
                return result
        except Exception as e:
            _LOGGER.error("Failed to set device %s settings: %s", device_id, e)
            raise

    async def async_request(
        self, method: str, url: str, **kwargs: Any
    ) -> "ClientResponse":
        """Perform a request using the session."""
        if not self._user_obj:
            raise RuntimeError("Session not initialized")

        session = self.websession or async_get_clientsession(self.hass)
        headers = kwargs.pop("headers", {})
        headers.update(await self._get_auth_headers())

        async with session.request(method, url, headers=headers, **kwargs) as resp:
            resp.raise_for_status()
            return resp

    async def set_device_setting_silent(
        self, device_id: str, settings: dict[str, Any]
    ) -> None:
        """Set device settings via HTTP POST without raising on error (best effort)."""
        try:
            await self.set_device_setting_http(device_id, settings)
        except Exception as e:
            _LOGGER.warning(
                "HTTP sync failed for %s: %s (MQTT already sent)", device_id, e
            )

    async def get_st1_state(self, device_ids: list[str]) -> dict[str, Any]:
        """Get full state for ST1 devices via batch endpoint."""
        if not self._user_obj:
            return {}

        session = self.websession or async_get_clientsession(self.hass)
        url = f"{BASE_URL}/state/batch"
        payload = {"deviceIds": device_ids}

        try:
            async with session.post(
                url, json=payload, headers=await self._get_auth_headers()
            ) as resp:
                resp.raise_for_status()
                return cast(dict[str, Any], await resp.json())
        except Exception as e:
            _LOGGER.debug("Failed to fetch ST1 state batch: %s", e)
            return {}
