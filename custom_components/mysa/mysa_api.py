"""Mysa API Module.

Handles high-level API interactions.
"""
# pylint: disable=too-many-lines
# Justification: Central API controller handles all device types, MQTT commands, and HTTP endpoints.
# Splitting would require significant architectural changes.

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, cast

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant

from .capabilities import DeviceCapabilities
from .client import MysaClient
from .const import (
    AC_FAN_MODES_REVERSE,
    AC_SWING_MODES_REVERSE,
)
from .device import MysaDeviceLogic
from .mysa_auth import BASE_URL
from .realtime import MysaRealtime

_LOGGER = logging.getLogger(__name__)


class MysaApi:
    """Mysa API Client."""

    # pylint: disable=too-many-arguments, too-many-public-methods
    # Justification: Facade class exposing full API surface for Home Assistant.
    # pylint: disable=too-many-instance-attributes, too-many-positional-arguments
    # Justification: Requires tracking extensive state for API authentication and device management.
    # Justification: Facade class exposing full API surface and maintaining state for all devices.
    def __init__(
        self,
        username: str,
        password: str,
        hass: HomeAssistant,  # Changed from Any
        coordinator_callback: Callable[[], Any] | None = None,
        upgraded_lite_devices: list[str] | None = None,
        estimated_max_current: int = 0,
        wattages: dict[str, int] | None = None,
        simulated_energy: bool = False,
        websession: ClientSession | None = None,
    ) -> None:
        """Initialize the API."""
        self.hass = hass
        self.coordinator_callback = coordinator_callback
        self.upgraded_lite_devices = upgraded_lite_devices or []
        self.estimated_max_current = estimated_max_current
        self.wattages = wattages or {}
        self.simulated_energy = simulated_energy
        self._metadata_requested: dict[str, float] = {}
        self._latest_timestamp: dict[str, int] = {}
        self._shadow_versions: dict[str, dict[str, int]] = {}
        self._clock_skew: dict[str, float] = {}  # device_id: (mqtt_ts - local_ts)
        self._last_mqtt_poll_time: dict[str, float] = {}  # device_id: timestamp

        # Get websession if not provided
        if websession is None:
            # async_get_clientsession is removed.
            # Assuming hass has a way to get a session or it's passed.
            # ClientSession can be instantiated directly if not provided.
            websession = ClientSession()

        # State
        self.states: dict[str, Any] = {}
        self._last_command_time: dict[str, float] = {}  # device_id: timestamp
        self.device_caps: dict[str, DeviceCapabilities] = {}  # Capability cache
        self._shadow_version_timestamps: dict[str, dict[str, float]] = {}

        # Components
        self.client = MysaClient(hass, username, password, websession)
        self._capabilities_initialized: bool = False
        self._bg_polling_task: asyncio.Task[None] | None = None
        # Note: we initialize Realtime here but start it later
        # Realtime needs callbacks
        # We need to ensure _on_mqtt_update matches the callback signature in Realtime
        self.realtime = MysaRealtime(
            hass,
            get_signed_url_callback=self.client.get_signed_mqtt_url,
            on_update_callback=self._on_mqtt_update,
        )

    # Properties delegating to components
    @property
    def username(self) -> str:
        """Return username."""
        return self.client.username

    @property
    def password(self) -> str:
        """Return password."""
        return self.client.password

    @property
    def devices(self) -> dict[str, Any]:
        """Return devices."""
        return self.client.devices

    @devices.setter
    def devices(self, value: dict[str, Any]) -> None:
        self.client.devices = value

    @property
    def homes(self) -> list[Any]:
        """Return homes."""
        return self.client.homes

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self.client.is_connected

    @property
    def is_mqtt_running(self) -> bool:
        """Return MQTT status."""
        return self.realtime.is_running

    @property
    def mqtt_status(self) -> str:
        """Return detailed MQTT status string for UI."""
        if not self.realtime.is_running:
            return "Stopped"
        if not self.is_connected:
            # Note: is_connected usually means HTTP/Auth is OK.
            # Realtime connection is separate.
            pass

        # Check MQTT specific connection
        if not self.realtime._mqtt_connected.is_set():
            return "Connecting"

        # Check staleness (5 minutes)
        last_pkt = self.realtime.last_packet_time
        if last_pkt == 0:
            return "Starting"

        if time.time() - last_pkt > 300:
            return "Stale"

        return "Running"

    # Authentication & Setup
    async def authenticate(self, use_cache: bool = True) -> bool:
        """Authenticate with Mysa."""
        return await self.client.authenticate(use_cache=use_cache)

    async def get_devices(self) -> dict[str, Any]:
        """Get devices and initialize capabilities."""
        if getattr(self, "_capabilities_initialized", False):
            return self.devices

        devices = await self.client.get_devices()

        # Identify S1 devices
        s1_devices = [
            did
            for did, data in devices.items()
            if "st-v1-0" in data.get("Model", "").lower()
            or "st-v1" in data.get("Model", "").lower()
        ]
        _LOGGER.debug(
            "Identified ST-V1-0 devices for shadow subscription: %s", s1_devices
        )

        # Update realtime subscription list
        self.realtime.set_devices(list(devices.keys()), stv10_devices=s1_devices)

        # Initialize device capabilities cache
        await self._initialize_capabilities()

        # Batch initialize firmware versions
        await self._initialize_firmware_versions()

        self._capabilities_initialized = True
        return devices

    async def _initialize_firmware_versions(self) -> None:
        """Fetch all firmware versions at once and populate states."""
        _LOGGER.debug("Fetching all firmware versions in batch")
        firmware_data = await self.client.get_all_firmware_versions()

        for device_id, info in firmware_data.items():
            version = info.get("InstalledVersion")
            if version:
                if device_id not in self.states:
                    self.states[device_id] = {}
                self.states[device_id]["FirmwareVersion"] = version
                _LOGGER.debug("Batch firmware update for %s: %s", device_id, version)

    async def fetch_homes(self) -> None:
        """Fetch homes and zones."""
        await self.client.fetch_homes()

    async def _initialize_capabilities(self) -> None:
        """Initialize capability cache for all devices."""
        _LOGGER.debug("Initializing device capabilities cache")

        # Get current state for all devices
        state = await self.get_state()

        # Identify ST-V1 devices for capabilities fetch
        stv10_devices = [
            device_id
            for device_id, device_data in self.devices.items()
            if "st-v1" in device_data.get("Model", "").lower()
        ]

        # Fetch capabilities for ST-V1 devices in parallel
        cap_results = {}
        if stv10_devices:
            cap_tasks = [
                self.client.fetch_capabilities(device_id) for device_id in stv10_devices
            ]
            cap_data = await asyncio.gather(*cap_tasks, return_exceptions=True)

            for device_id, cap_json in zip(stv10_devices, cap_data, strict=False):
                if isinstance(cap_json, BaseException):
                    _LOGGER.warning(
                        "Failed to fetch capabilities for %s: %s", device_id, cap_json
                    )
                    continue
                if cap_json:
                    cap_results[device_id] = cap_json

        # Initialize capabilities for all devices
        for device_id, device_data in self.devices.items():
            device_state = state.get(device_id, {})

            # Use HTTP capabilities for ST-V1 if available
            if device_id in cap_results:
                _LOGGER.debug("Using HTTP capabilities for ST-V1 device %s", device_id)
                self.device_caps[device_id] = (
                    DeviceCapabilities.from_stv10_capabilities(
                        device_id, cap_results[device_id], self
                    )
                )
            else:
                # Fallback to state-based capabilities
                self.device_caps[device_id] = DeviceCapabilities.from_device(
                    device_id, device_data, device_state, self
                )

        _LOGGER.debug("Initialized capabilities for %d devices", len(self.device_caps))

    async def fetch_firmware_info(self, device_id: str) -> dict[str, Any] | None:
        """Fetch firmware update info."""
        return await self.client.fetch_firmware_info(device_id)

    def get_electricity_rate(self, device_id: str) -> float | None:
        """Get electricity rate for a device.

        Checks for a custom_erate override in the mysa_extended integration first.
        Falls back to the cloud-provided rate if no override is set.
        """
        # Check for custom rate override from mysa_extended
        extended_domain = "mysa_extended"
        # Type check for config_entries to satisfy stricter checking if needed
        # Assuming self.hass.config_entries is available and standard
        if hasattr(self.hass, "config_entries"):
            # We need to access private or specific API, usually public.
            # async_entries is standard.
            for entry in self.hass.config_entries.async_entries(extended_domain):
                custom_rate = entry.options.get("custom_erate")
                if custom_rate is not None:
                    try:
                        return float(custom_rate)
                    except (ValueError, TypeError):
                        pass

        # Fall back to cloud-provided rate
        return self.client.get_electricity_rate(device_id)

    # State Management

    async def get_state(self) -> dict[str, Any]:
        """Get full state of all devices (HTTP merge)."""
        # Fetch fresh HTTP state
        new_states = await self.client.get_state()

        if not isinstance(new_states, dict):
            _LOGGER.debug(
                "get_state returned non-dict during lifecycle/test: %s",
                type(new_states),
            )
            return self.states

        for device_id, new_data in new_states.items():
            self._update_state_cache(device_id, new_data, filter_stale=True)

        return self.states

    async def _on_mqtt_update(
        self,
        device_id: str,
        state_update: dict[str, Any],
        resolve_safe_id: bool | None = False,
    ) -> None:
        # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        # Justification: Central message dispatcher handling all MQTT message types and payloads.
        # Justification: Handles complex ST-V1-0 shadow mapping and state normalization
        """Handle MQTT update callback."""
        if resolve_safe_id:
            # Try to match safe ID to real ID
            safe_id = device_id.lower()
            found = False
            for real_id in self.devices:
                if real_id.replace(":", "").lower() == safe_id:
                    device_id = real_id
                    found = True
                    break
            if not found:
                _LOGGER.debug("Unknown device (safe ID: %s), likely stale", safe_id)
                return

        # Normalize
        # Handle 'delta' payload structure where 'state' is a root key
        if "state" in state_update and isinstance(state_update["state"], dict):
            # Flatten: merge inner state into root for processing
            state_update.update(state_update.pop("state"))

        if (
            "mode" in state_update or "Mode" in state_update
        ) and "source" in state_update:
            # ST-V1-0 'modes' shadow or generic mode with source
            state_update["md"] = state_update.get("mode") or state_update.get("Mode")
        elif any(
            k in state_update
            for k in ["value", "setpoint", "heatSetpoint", "coolSetpoint"]
        ):
            # ST-V1-0 'targetHeat', 'targetCool', or 'targetAuto' shadow
            raw_val = state_update.get("setpoint", state_update.get("value"))

            # Handle targetAuto (separate high/low keys)
            heat_raw = state_update.get("heatSetpoint")
            cool_raw = state_update.get("coolSetpoint")

            if raw_val is not None:
                val = float(raw_val) / 100.0
                shadow_name = state_update.get("_shadow_name")

                if shadow_name == "targetHeat":
                    state_update["target_heat"] = val
                elif shadow_name == "targetCool":
                    state_update["target_cool"] = val

                # Keep stpt/sp for generic compatibility
                state_update["stpt"] = val
                state_update["sp"] = val
                state_update["SetPoint"] = val

            if heat_raw is not None:
                val = float(heat_raw) / 100.0
                state_update["target_heat"] = val
                state_update["heatsetpoint"] = val
            if cool_raw is not None:
                val = float(cool_raw) / 100.0
                state_update["target_cool"] = val
                state_update["coolsetpoint"] = val

        if "hvacState" in state_update:
            state_update["hvac_state"] = state_update["hvacState"]
        if "activeMode" in state_update:
            state_update["active_mode"] = state_update["activeMode"]
        if "ProximityMode" in state_update:
            state_update["pr"] = state_update["ProximityMode"]
        if "ButtonState" in state_update:
            state_update["lk"] = state_update["ButtonState"]
        if "hvacConfig" in state_update:
            cfg = state_update["hvacConfig"]
            if isinstance(cfg, dict) and "idx" in cfg:
                state_update["hvac_config_index"] = cfg["idx"]

        # Extract ST-V1-0 specific fields in _update_state_cache below

        if not MysaDeviceLogic.is_stv10_device(self.devices.get(device_id)):
            MysaDeviceLogic.normalize_state(state_update)

        # Trust MQTT updates - they're real-time from the device
        # (HTTP polls use filter_stale=True in get_state to avoid cloud lag)
        self._update_state_cache(device_id, state_update, filter_stale=False)

        _LOGGER.debug("MQTT state update for %s", device_id)

        # Proactive Metadata Check:
        # If firmware OR IP is missing, nudge the device.
        # We use a time-based backoff (e.g., 5 minutes) to avoid spamming.
        current_state = self.states.get(device_id, {})
        fw_version = current_state.get("FirmwareVersion")
        ip_addr = current_state.get("ip")

        missing_metadata = not fw_version or fw_version == "None" or not ip_addr

        if missing_metadata:
            now = time.time()
            last_req = self._metadata_requested.get(device_id, 0)
            if now - last_req > 300:  # 5 minutes
                _LOGGER.debug(
                    "Metadata (FW/IP) missing for %s, requesting dump (last req: %.0fs ago)...",
                    device_id,
                    now - last_req,
                )
                self._metadata_requested[device_id] = now
                # Use a task to not block the callback
                self.hass.async_create_task(self.update_request(device_id))

        # Trigger HA update
        if self.coordinator_callback:
            if callable(self.coordinator_callback):
                await self.coordinator_callback()

    def _extract_stv10_shadow_data(
        self, state_update: dict[str, Any], skip_sensors: bool = False
    ) -> None:
        """Extract ST-V1-0 diagnostic fields and sensors."""
        self._flatten_stv10_shadows(state_update)
        # direct mappings
        mapping = {
            "rssi": "rssi",
            "hum": "hum",
            "humidityDisplay": "current_humidity",
            "externalTemperature": "external_temperature",
            "outdoorTemperature": "external_temperature",
            "ip_address": "ip",
            "lockoutModes": "lockout_modes",
            "filter": "filter_life",
            "temperatureFormat": "temperature_format",
            "ambientTemperature": "current_temp_raw",
            "currentTemperature": "current_temp_raw",
            "electricitySaver": "electricity_saver",
            "relativeHumidity": "current_humidity",
            "humidity": "current_humidity",
            "temperature": "current_temp_raw",
        }
        for src, dst in mapping.items():
            if src in state_update:
                if skip_sensors and dst in [
                    "current_humidity",
                    "current_temp_raw",
                    "hum",
                ]:
                    continue
                state_update[dst] = state_update[src]

        # Extract auto_mode_enabled from flattened 'enabled' key (targetAuto)
        if "enabled" in state_update and "auto_mode_enabled" not in state_update:
            state_update["auto_mode_enabled"] = state_update["enabled"]

        # Extract activeMode from modes shadow (if present)
        if "activeMode" in state_update:
            state_update["active_mode"] = state_update["activeMode"]

        self._extract_stv10_hvac_config(state_update)
        self._extract_stv10_conversions(state_update)
        if not skip_sensors:
            self._extract_stv10_sensors(state_update)
        self._extract_stv10_identity(state_update)
        self._extract_stv10_diagnostics(state_update, skip_sensors=skip_sensors)

    def _flatten_stv10_shadows(self, state_update: dict[str, Any]) -> None:
        """Flatten ST-V1-0 shadows (reported/desired and latestTelemetry)."""
        # 1. Process standard shadow objects
        shadow_keys = [
            "targetHeat",
            "targetCool",
            "targetAuto",
            "modes",
            "hvacConfig",
            "identity",
            "diagnostics",
            "telemetry",
            "tracking",
            "matter",
            "physicalInterface",
        ]
        for key in shadow_keys:
            shadow = state_update.get(key)
            if isinstance(shadow, dict):
                reported = shadow.get("reported", {})
                desired = shadow.get("desired", {})

                # Ensure they are dicts
                if not isinstance(reported, dict):
                    reported = {}
                if not isinstance(desired, dict):
                    desired = {}

                # Check timestamps to determine precedence
                r_ts = reported.get("timestamp", 0)
                d_ts = desired.get("timestamp", 0)

                merged = {}
                # The newer one takes precedence (merged last)
                if r_ts > d_ts:
                    merged.update(desired)
                    merged.update(reported)
                else:
                    merged.update(reported)
                    merged.update(desired)

                # Prevent targetHeat and targetCool 'setpoint' key collisions
                if key == "targetHeat" and "setpoint" in merged:
                    merged["target_heat"] = merged.pop("setpoint")
                elif key == "targetCool" and "setpoint" in merged:
                    merged["target_cool"] = merged.pop("setpoint")

                state_update.update(merged)

        # 2. Process latestTelemetry (contains 'reading' object)
        lt = state_update.get("latestTelemetry")
        if isinstance(lt, dict):
            # Flatten root telemetry keys (isConnected, lastConnected, etc)
            for k, v in lt.items():
                if k != "reading":
                    state_update[k] = v
            # Flatten the nested reading object (contains raw sensor data)
            reading = lt.get("reading")
            if isinstance(reading, dict):
                state_update.update(reading)
                # Keep 'reading' key at root for extraction methods
                state_update["reading"] = reading

    def _extract_stv10_hvac_config(self, state_update: dict[str, Any]) -> None:
        """Extract ST-V1-0 HVAC config."""
        if "hvacConfig" in state_update and isinstance(
            state_update["hvacConfig"], dict
        ):
            hvac_cfg = state_update["hvacConfig"]
            hvac_mapping = {
                "idx": "hvac_config_index",
                "heatUsesFan": "adv_heat_uses_fan",
                "coolUsesFan": "adv_cool_uses_fan",
                "auxUsesFan": "adv_aux_uses_fan",
                "fanRuntime": "adv_fan_runtime",
                "fanPeriod": "adv_fan_period",
                "advHeatStageTwoDelta": "adv_heat_stage_two_delta",
                "advHeatStageTwoDelay": "adv_heat_stage_two_delay",
                "advHeatStageTwoDelayMinutes": "adv_heat_stage_two_delay",
                "advCoolStageTwoDelta": "adv_cool_stage_two_delta",
                "advCoolStageTwoDelay": "adv_cool_stage_two_delay",
                "advCoolStageTwoDelayMinutes": "adv_cool_stage_two_delay",
                "coolWhenReversed": "adv_cool_when_reversed",
                "heating_stage_two_exists": "heating_stage_two_exists",
                "cooling_stage_two_exists": "cooling_stage_two_exists",
                "is_reversible_heat_pump": "is_reversible_heat_pump",
                "advFanRampMinutes": "adv_fan_ramp",
                "advCoolFanDelayMinutes": "adv_cool_fan_delay",
                "advHeatFanDelayMinutes": "adv_heat_fan_delay",
                "advCoolFanRunOnMinutes": "adv_cool_fan_run_on",
                "advHeatFanRunOnMinutes": "adv_heat_fan_run_on",
                "multiple_fan_speeds": "multiple_fan_speeds",
                "fan_sequence": "fan_sequence",
            }
            for src, dst in hvac_mapping.items():
                if src in hvac_cfg:
                    state_update[dst] = hvac_cfg[src]

    def _extract_stv10_conversions(self, state_update: dict[str, Any]) -> None:
        """Extract ST-V1-0 conversions."""
        if "lockoutMin" in state_update:
            # Convert units from device (C*100) to HA (C)
            # Heuristic: if > 100, it's likely centidegrees (5-30 range expected)
            val = float(state_update["lockoutMin"])
            if val > 100:
                val /= 100.0
            state_update["min_setpoint"] = val
            state_update["MinSetpoint"] = val
        if "lockoutMax" in state_update:
            val = float(state_update["lockoutMax"])
            if val > 100:
                val /= 100.0
            state_update["max_setpoint"] = val
            state_update["MaxSetpoint"] = val

        # Handle both 'autoDeadband' (modes shadow) and 'deadband' (targetAuto shadow)
        db_val = state_update.get("autoDeadband", state_update.get("deadband"))
        if db_val is not None:
            # Heuristic: if > 50, it's likely centidegrees (2.0-6.0 range expected)
            val = float(db_val)
            if val > 50:
                val /= 100.0
            state_update["auto_deadband"] = val
            state_update["autoDeadband"] = val

        if "adv_heat_stage_two_delta" in state_update:
            state_update["adv_heat_stage_two_delta"] = (
                float(state_update["adv_heat_stage_two_delta"]) / 100.0
            )

        # Extract from physicalInterface shadow (target of format)
        if "format" in state_update:
            state_update["temperature_format"] = state_update["format"]

    # Justification: Central extraction method covering many different sensor keys.
    def _extract_stv10_sensors(self, state_update: dict[str, Any]) -> None:  # pylint: disable=too-many-branches
        """Extract ST-V1-0 sensors."""
        # Extract from latestTelemetry for Sensors
        if "reading" in state_update:
            reading = state_update["reading"]
            if "temperature" in reading:
                # Convert ST-V1-0 temp (C*100) to C
                state_update["current_temp"] = float(reading["temperature"]) / 100.0
            if "humidityDisplay" in reading:
                state_update["current_humidity"] = reading["humidityDisplay"]
            if "humidity" in reading:
                state_update["current_humidity"] = reading["humidity"]

        # Extract from room/currentTemperature or direct keys
        if "current_temp_raw" in state_update:
            # Most ST-V1-0 temps are C*100
            val = float(state_update["current_temp_raw"])
            if val > 100:  # Heuristic for C*100 vs C
                state_update["current_temp"] = val / 100.0
            else:
                state_update["current_temp"] = val

        # Handle 'roomTemperature' (AC/HVAC telemetry)
        if "roomTemperature" in state_update:
            val = float(state_update["roomTemperature"])
            # Heuristic: ST-V1-0 usually sends C, but sometimes C*100 in other contexts.
            # roomTemperature in telemetry is typically C.
            # If > 100, assume C*100.
            if val > 100:
                state_update["current_temp"] = val / 100.0
            else:
                state_update["current_temp"] = val

        # Handle 'roomTemperature' nested in reading (if flatten failed or direct extraction)
        if "reading" in state_update:
            reading = state_update["reading"]
            if "roomTemperature" in reading:
                val = float(reading["roomTemperature"])
                if val > 100:
                    state_update["current_temp"] = val / 100.0
                else:
                    state_update["current_temp"] = val

        if "currentTemperature" in state_update:
            state_update["current_temp"] = (
                float(state_update["currentTemperature"]) / 100.0
            )

        # Extract Runtimes (Energy info)
        if "reading" in state_update:
            reading = state_update["reading"]
            runtime_map = {
                "onTime": "on_time",
                "fanOnTime": "fan_on_time",
                "stageTwoOnTime": "stage_two_on_time",
                "stageOneCoolOnTime": "stage_one_cool_on_time",
                "stageTwoCoolOnTime": "stage_two_cool_on_time",
                "emergencyHeatOnTime": "emergency_heat_on_time",
            }
            for src, dst in runtime_map.items():
                if src in reading:
                    state_update[dst] = reading[src]

        # Extract HVAC States and Duty Cycle
        if "hvacStates" in state_update and isinstance(
            state_update["hvacStates"], dict
        ):
            hvac_states = state_update["hvacStates"]
            if "DutyCycle" in hvac_states:
                state_update["Duty"] = hvac_states["DutyCycle"]
            # Also extract raw states if needed
            for key in ["W1", "W2", "G", "Y1", "Y2", "AuxHeat", "Fan"]:
                if key in hvac_states:
                    state_update[f"hvac_raw_{key}"] = hvac_states[key]

    def _extract_stv10_identity(self, state_update: dict[str, Any]) -> None:
        """Extract ST-V1-0 identity fields."""
        if "identity" in state_update and isinstance(state_update["identity"], dict):
            identity = state_update["identity"].get(
                "reported", state_update["identity"]
            )
            if "model" in identity:
                state_update["Model"] = identity["model"]
            if "serial" in identity:
                state_update["serial_number"] = identity["serial"]
            if "fw" in identity:
                state_update["FirmwareVersion"] = identity["fw"]

    def _extract_stv10_diagnostics(
        self, state_update: dict[str, Any], skip_sensors: bool = False
    ) -> None:
        """Extract ST-V1-0 diagnostic fields from shadow."""
        if "diagnostics" in state_update and isinstance(
            state_update["diagnostics"], dict
        ):
            diag = state_update["diagnostics"]
            reported = diag.get("reported", {})
            diag_mapping = {
                "freeHeap": "free_heap",
                "secureBootEnabled": "secure_boot",
                "encryptionEnabled": "encryption_enabled",
                "privKeyOk": "priv_key_ok",
                "pubKeyHash": "pub_key_hash",
                "faultTest": "fault_test",
            }
            for src, dst in diag_mapping.items():
                if src in reported:
                    if skip_sensors and dst == "free_heap":
                        continue
                    state_update[dst] = reported[src]

    # Commands
    async def set_target_temperature(self, device_id: str, temperature: float) -> None:
        """Set target temperature via MQTT."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        target_val = float(temperature)
        self._update_state_cache(
            device_id,
            {
                "SetPoint": target_val,
                "sp": target_val,
                "stpt": target_val,
                "a_sp": target_val,
                "ACTemp": target_val,
                "3": target_val,
                "Timestamp": int(time.time()),
            },
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        if MysaDeviceLogic.is_stv10_device(device):
            _LOGGER.debug("ST-V1-0 device detected, using ST-V1 setters")
            await self.set_stv10_target_temperature(device_id, target_val)
            return

        payload_type = MysaDeviceLogic.get_payload_type(
            device, self.upgraded_lite_devices
        )

        body = {
            "cmd": [
                {"sp": target_val, "stpt": target_val, "a_sp": target_val, "tm": -1}
            ],
            "type": payload_type,
            "ver": 1,
        }
        await self.realtime.send_command(device_id, body, self.client.user_id)

        # 2. No additional notification needed for direct MQTT commands.
        # The device will echo its state automatically.

    async def set_target_temperature_range(
        self, device_id: str, low_temp: float, high_temp: float
    ) -> None:
        """Set target temperature range via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        self._update_state_cache(
            device_id,
            {
                "target_heat": low_temp,
                "target_cool": high_temp,
                "heatsetpoint": low_temp,
                "coolsetpoint": high_temp,
                "Timestamp": int(time.time()),
            },
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        model = str(self.devices.get(device_id, {}).get("Model", ""))
        if "ST-V1-0" in model:
            payload = {
                "source": 3,
                "targetAuto": {
                    "heatSetpoint": low_temp,
                    "coolSetpoint": high_temp,
                },
            }
            await self.client.post_state_update(device_id, payload)
        else:
            # Legacy devices (AC-V1 etc) may use Min/Max setpoint for range or separate ones
            # We call both for compatibility if this method is invoked
            await self.set_min_setpoint(device_id, low_temp)
            await self.set_max_setpoint(device_id, high_temp)

    async def set_hvac_mode(self, device_id: str, hvac_mode: str) -> None:
        """Set HVAC mode via MQTT."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        mode_str = str(hvac_mode).lower()
        device = self.devices.get(device_id)

        if MysaDeviceLogic.is_ac_device(device):
            mode_val = MysaDeviceLogic.get_ac_mode_value(mode_str)
        elif MysaDeviceLogic.is_stv10_device(device):
            mode_val = MysaDeviceLogic.get_stv10_mode_value(mode_str)
        else:
            # Legacy Baseboard (BB-V1/V2, INF-V1)
            mode_val = 1 if "off" in mode_str else 3

        self._update_state_cache(
            device_id,
            {
                "Mode": mode_val,
                "md": mode_val,
                "mode": mode_val,
                "TstatMode": mode_val,
                "ACMode": mode_val,
                "2": mode_val,
                "Timestamp": int(time.time()),
            },
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        if MysaDeviceLogic.is_stv10_device(device):
            await self.set_stv10_hvac_mode(device_id, mode_val)
            return

        payload_type = MysaDeviceLogic.get_payload_type(
            device, self.upgraded_lite_devices
        )
        body = {"cmd": [{"md": mode_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        # 2. No additional notification needed for direct MQTT commands.
        # The device will echo its state automatically.

    async def notify_settings_changed(self, device_id: str) -> None:
        """Notify device to check cloud settings (MsgType 6)."""
        timestamp = int(time.time())
        body = {
            "Device": device_id.lower(),
            "EventType": 0,
            "MsgType": 6,
            "Timestamp": timestamp,
        }
        # MsgType 6, wrap=False
        await self.realtime.send_command(
            device_id, body, self.client.user_id, msg_type=6, wrap=False
        )

    async def update_request(self, device_id: str) -> None:
        """Request metadata dump (MsgType 7): FW version, IP, Serial, MAC."""
        # ST-V1-0 devices use Shadow GET requests instead of legacy MsgType 7
        # ST-V1-0 devices use Shadow GET requests instead of legacy MsgType 7
        device = self.devices.get(device_id, {})
        if "ST-V1-0" in device.get("Model", ""):
            _LOGGER.debug(
                "S1 device %s: Using shadow GET instead of MsgType 7", device_id
            )
            await self.fetch_stv10_shadows(device_id)
            return

        # Legacy V1/V2 devices: Send MsgType 7
        timestamp = int(time.time())
        body = {"Device": device_id, "Timestamp": timestamp, "MsgType": 7}
        # MsgType 7, wrap=False
        await self.realtime.send_command(
            device_id, body, self.client.user_id, msg_type=7, wrap=False
        )

    async def async_send_state_poll(self, device_id: str) -> None:
        """Force device to broadcast current state via MQTT (MsgType 11).

        This is a legacy protocol command (used by the official app) that wakes
        up the device and forces it to aggressively report state for the given timeout.
        """
        # Debounce: Only one poll every 60 seconds per device
        now = time.time()
        last_poll = self._last_mqtt_poll_time.get(device_id, 0)
        if now - last_poll < 60:
            return

        device = self.devices.get(device_id, {})
        model = str(device.get("Model", "")).lower()
        if "st-v1-0" in model:
            # Shadow devices don't need MsgType 11, they use AWS IoT sync
            return

        # ONLY poll if we have a persistent connection.
        # One-off polls are too expensive and hit AWS Rate Limits.
        if not self.realtime.is_connected:
            return

        self._last_mqtt_poll_time[device_id] = now

        timestamp = int(time.time())
        # Timeout of 300 seconds to force a quick burst of updates without
        # spamming the network permanently.
        body = {
            "Device": device_id.lower(),
            "Timestamp": timestamp,
            "MsgType": 11,
            "Timeout": 300,
        }

        try:
            await self.realtime.send_command(
                device_id,
                body,
                self.client.user_id,
                msg_type=11,
                wrap=False,
                use_persistent_only=True,
            )
        except Exception as e:
            _LOGGER.debug(
                "Failed to send state poll (MsgType 11) to %s: %s", device_id, e
            )

    # ST-V1-0 Commands
    async def set_stv10_target_temperature(
        self, device_id: str, temperature: float
    ) -> None:
        """Set ST-V1-0 target temperature (Shadow)."""
        self._last_command_time[device_id] = time.time()

        # Determine correct shadow based on current mode
        # Default to Heat if unknown
        state = self.states.get(device_id, {})
        # Check 'md' or 'mode'
        mode = state.get("md", state.get("mode", 4))

        if mode == 3:  # Cool
            await self.set_stv10_cool_setpoint(device_id, temperature)
        else:
            await self.set_stv10_heat_setpoint(device_id, temperature)

    async def set_stv10_hvac_mode(self, device_id: str, mode_int: int) -> None:
        """Set ST-V1-0 HVAC mode (Shadow)."""
        self._last_command_time[device_id] = time.time()

        payload = {"source": 3, "modes": {"mode": mode_int}}

        # Update cache eagerly
        timestamp = int(time.time())
        self._update_state_cache(
            device_id, {"md": mode_int, "mode": mode_int, "Timestamp": timestamp}
        )
        if self.coordinator_callback and callable(self.coordinator_callback):
            await self.coordinator_callback()

        await self.client.post_state_update(device_id, payload)

    async def set_stv10_auto_deadband(self, device_id: str, deadband: float) -> None:
        """Set ST-V1-0 Auto Mode Deadband (Shadow)."""
        self._last_command_time[device_id] = time.time()

        # Send as decimal degrees (not centidegrees) - matches official app
        payload = {"source": 3, "targetAuto": {"deadband": deadband}}

        # Update cache eagerly - store as centidegrees for consistency with other setpoints
        # our conversion logic will scale it back down to degrees
        timestamp = int(time.time())
        self._update_state_cache(
            device_id,
            {
                "autoDeadband": int(deadband * 100),
                "deadband": int(deadband * 100),
                "Timestamp": timestamp,
            },
        )
        if self.coordinator_callback and callable(self.coordinator_callback):
            await self.coordinator_callback()

        await self.client.post_state_update(device_id, payload)

    async def set_stv10_heat_setpoint(self, device_id: str, temperature: float) -> None:
        """Set ST-V1-0 Heat Setpoint (Shadow)."""
        self._last_command_time[device_id] = time.time()

        # Send as decimal degrees (not centidegrees)
        payload = {"source": 3, "targetHeat": {"setpoint": temperature}}

        # Update cache eagerly
        timestamp = int(time.time())
        self._update_state_cache(
            device_id,
            {
                "target_heat": temperature,
                "targetHeat": int(temperature * 100),
                "Timestamp": timestamp,
            },
        )
        if self.coordinator_callback and callable(self.coordinator_callback):
            await self.coordinator_callback()

        await self.client.post_state_update(device_id, payload)

    async def set_stv10_cool_setpoint(self, device_id: str, temperature: float) -> None:
        """Set ST-V1-0 Cool Setpoint (Shadow)."""
        self._last_command_time[device_id] = time.time()

        # Send as decimal degrees (not centidegrees)
        payload = {"source": 3, "targetCool": {"setpoint": temperature}}

        # Update cache eagerly
        timestamp = int(time.time())
        self._update_state_cache(
            device_id,
            {
                "target_cool": temperature,
                "targetCool": int(temperature * 100),
                "Timestamp": timestamp,
            },
        )
        if self.coordinator_callback and callable(self.coordinator_callback):
            await self.coordinator_callback()

        await self.client.post_state_update(device_id, payload)

    async def set_stv10_fan_mode(self, device_id: str, fan_mode: str) -> None:
        """Set ST-V1-0 Fan Mode (Shadow)."""
        self._last_command_time[device_id] = time.time()

        # Guessing mapping based on 0=Auto
        # HA Fan Modes: auto, low, medium, high
        mapping = {"auto": 0, "low": 1, "medium": 2, "high": 3}
        fan_int = mapping.get(fan_mode.lower(), 0)

        payload = {"source": 3, "modes": {"fan_mode": fan_int}}

        # Update cache eagerly
        self._update_state_cache(device_id, {"fan_mode": fan_int})
        if self.coordinator_callback and callable(self.coordinator_callback):
            await self.coordinator_callback()

        await self.client.post_state_update(device_id, payload)

    async def fetch_stv10_shadows(self, device_id: str) -> None:
        """Fetch ST-V1-0 device shadows by requesting them from AWS IoT."""
        safe_id = device_id.replace(":", "").lower()

        _LOGGER.debug(
            "fetch_stv10_shadows: Requesting shadows for device %s (safe_id: %s)",
            device_id,
            safe_id,
        )

        # Request shadows in parallel
        modes_topic = f"$aws/things/{safe_id}/shadow/name/modes/get"
        heat_topic = f"$aws/things/{safe_id}/shadow/name/targetHeat/get"
        cool_topic = f"$aws/things/{safe_id}/shadow/name/targetCool/get"
        interface_topic = f"$aws/things/{safe_id}/shadow/name/physicalInterface/get"
        telemetry_topic = f"$aws/things/{safe_id}/shadow/name/latestTelemetry/get"
        room_topic = f"$aws/things/{safe_id}/shadow/name/room/get"
        auto_topic = f"$aws/things/{safe_id}/shadow/name/targetAuto/get"
        classic_topic = f"$aws/things/{safe_id}/shadow/get"

        await asyncio.gather(
            self.realtime.publish(modes_topic, {}),
            self.realtime.publish(heat_topic, {}),
            self.realtime.publish(cool_topic, {}),
            self.realtime.publish(interface_topic, {}),
            self.realtime.publish(telemetry_topic, {}),
            self.realtime.publish(room_topic, {}),
            self.realtime.publish(auto_topic, {}),
            self.realtime.publish(classic_topic, {}),
        )

        _LOGGER.debug("Requested ST-V1-0 shadows for %s", device_id)

    # ... Other Setters (Lock, Brightness, AC features) ...
    # Implementing pattern: _last_command -> Payload -> Send -> Optimistic Update -> Notify

    async def set_lock(self, device_id: str, locked: bool) -> None:
        """Set lock state via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        lock_val = 1 if locked else 0
        self._update_state_cache(
            device_id,
            {
                "Lock": {"v": lock_val},
                "lk": lock_val,
                "alk": lock_val,
                "lc": lock_val,
                "ButtonState": lock_val,
                "Timestamp": int(time.time()),
            },
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        model = str(self.devices.get(device_id, {}).get("Model", ""))
        if "ST-V1-0" in model:
            # Should have gone through set_stv10_lock
            await self.set_stv10_lock(device_id, locked)
        else:
            # Use legacy HTTP for Baseboard and AC-V1
            payload = {"ButtonState": "Locked" if locked else "Unlocked"}
            await self.client.set_device_setting_http(device_id, payload, legacy=True)

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

    async def set_ac_climate_plus(self, device_id: str, enabled: bool) -> None:
        """Set Climate+ state via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        # User EcoMode/ecoMode: 0=On, 1=Off (inverted)
        eco_str = "0" if enabled else "1"
        self._update_state_cache(
            device_id,
            {
                "EcoMode": enabled,
                "it": 1 if enabled else 0,
                "IsThermostatic": enabled,
                "ecoMode": eco_str,
                "eco": eco_str,
                "Timestamp": int(time.time()),
            },
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command (IsThermostatic)
        # AC-V1 is legacy
        await self.client.set_device_setting_http(
            device_id, {"IsThermostatic": enabled}, legacy=True
        )

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

        # 2. No additional notification needed for direct MQTT commands.

    # Helpers for AC
    def is_ac_device(self, device_id: str) -> bool:
        """Check if device is an AC unit."""
        return MysaDeviceLogic.is_ac_device(self.devices.get(device_id, {}))

    def get_ac_supported_caps(self, device_id: str) -> dict[str, Any]:
        """Get supported capabilities for AC."""
        device = self.devices.get(device_id, {})
        return dict(device.get("SupportedCaps", {}))

    # Shortcuts for other setters implementation ...
    # Since I'm rewriting the whole file I MUST include all previous methods.

    async def set_stv10_lock(self, device_id: str, locked: bool) -> None:
        """Set ST-V1-0 lock state via HTTP (Shadow)."""
        self._last_command_time[device_id] = time.time()
        lock_val = 3 if locked else 1  # 3=Locked, 1=Unlocked
        payload = {"source": 3, "physicalInterface": {"lockout": lock_val}}

        # Update cache eagerly
        self._update_state_cache(
            device_id,
            {
                "Lock": {"v": 1 if locked else 0},
                "lk": 1 if locked else 0,
                "ButtonState": 1 if locked else 0,  # Legacy key mapping
                "Timestamp": int(time.time()),
            },
        )
        if self.coordinator_callback and callable(self.coordinator_callback):
            await self.coordinator_callback()

        await self.client.post_state_update(device_id, payload)

    async def set_stv10_allow_auto_mode(self, device_id: str, enabled: bool) -> None:
        """Set ST-V1-0 Allow Auto Mode (Shadow/targetAuto)."""
        self._last_command_time[device_id] = time.time()
        # 1=Enabled, 0=Disabled per user manual capture
        val = 1 if enabled else 0
        payload = {"source": 3, "targetAuto": {"enabled": val}}

        # Update cache eagerly
        self._update_state_cache(device_id, {"auto_mode_enabled": val})
        if self.coordinator_callback and callable(self.coordinator_callback):
            await self.coordinator_callback()

        await self.client.post_state_update(device_id, payload)

    async def set_stv10_proximity(self, device_id: str, enabled: bool) -> None:
        """Set ST-V1-0 Proximity Mode (Shadow)."""
        self._last_command_time[device_id] = time.time()

        # We assume 1=Enabled, 0=Disabled for ST-V1-0
        payload = {"source": 3, "physicalInterface": {"proximity": 1 if enabled else 0}}

        # Update cache eagerly
        self._update_state_cache(
            device_id,
            {
                "ProximityMode": enabled,
                "px": enabled,
                "pr": 1 if enabled else 0,
                "Proximity": enabled,
                "Timestamp": int(time.time()),
            },
        )
        if self.coordinator_callback and callable(self.coordinator_callback):
            await self.coordinator_callback()

        await self.client.post_state_update(device_id, payload)

    async def set_stv10_temperature_format(
        self, device_id: str, is_fahrenheit: bool
    ) -> None:
        """Set ST-V1-0 temperature format (Shadow)."""
        self._last_command_time[device_id] = time.time()
        fmt_val = "F" if is_fahrenheit else "C"
        payload = {"source": 3, "physicalInterface": {"format": fmt_val}}

        # Update cache eagerly
        self._update_state_cache(
            device_id, {"temperature_format": fmt_val, "format": fmt_val}
        )
        if self.coordinator_callback and callable(self.coordinator_callback):
            await self.coordinator_callback()

        await self.client.post_state_update(device_id, payload)

    async def set_proximity(self, device_id: str, enabled: bool) -> None:
        """Set proximity sensing state via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        _LOGGER.debug("set_proximity(%s, %s) - Optimistic update", device_id, enabled)
        self._update_state_cache(
            device_id,
            {
                "ProximityMode": enabled,
                "px": enabled,
                "pr": 1 if enabled else 0,
                "Proximity": enabled,
                "Timestamp": int(time.time()),
            },
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        # 1. HTTP Command
        await self.client.set_device_setting_http(
            device_id, {"ProximityMode": enabled}, legacy=True
        )

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

    async def set_sensor_mode(self, device_id: str, mode: int) -> None:
        """Set sensor mode (0=Ambient, 1=Floor) via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        _LOGGER.debug("set_sensor_mode(%s, %s) - Optimistic update", device_id, mode)
        self._update_state_cache(
            device_id, {"SensorMode": mode, "Timestamp": int(time.time())}
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        # Map internal mode (1=Floor, 0=Ambient) to Mysa values (3=Floor, 5=Ambient)
        # Note: We use TrackedSensor as the key per user instruction
        payload_val = 3 if mode == 1 else 5
        await self.client.set_device_setting_http(
            device_id, {"TrackedSensor": payload_val}, legacy=True
        )

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

    async def set_auto_brightness(self, device_id: str, enabled: bool) -> None:
        """Set auto brightness state via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        self._update_state_cache(
            device_id,
            {
                "AutoBrightness": enabled,
                "ab": 1 if enabled else 0,
                "Timestamp": int(time.time()),
            },
        )
        self._update_brightness_cache(device_id, "a_b", 1 if enabled else 0)

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        await self.client.set_device_setting_http(
            device_id, {"AutoBrightness": enabled}, legacy=True
        )

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

    async def set_min_brightness(self, device_id: str, value: int) -> None:
        """Set minimum brightness via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        self._update_brightness_cache(device_id, "i_br", value)
        self._update_state_cache(
            device_id,
            {"MinBrightness": value, "mnbr": value, "Timestamp": int(time.time())},
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        await self.client.set_device_setting_http(
            device_id, {"MinBrightness": value}, legacy=True
        )

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

    async def set_max_brightness(self, device_id: str, value: int) -> None:
        """Set maximum brightness via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        self._update_brightness_cache(device_id, "a_br", value)
        self._update_state_cache(
            device_id,
            {"MaxBrightness": value, "mxbr": value, "Timestamp": int(time.time())},
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        await self.client.set_device_setting_http(
            device_id, {"MaxBrightness": value}, legacy=True
        )

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

    # AC Setters
    async def set_ac_fan_speed(self, device_id: str, fan_mode: str) -> None:
        """Set AC fan speed."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        fan_val = AC_FAN_MODES_REVERSE.get(fan_mode.lower())
        if fan_val is None:
            return

        self._update_state_cache(
            device_id,
            {
                "FanSpeed": {"v": fan_val},
                "fn": fan_val,
                "4": fan_val,
                "Timestamp": int(time.time()),
            },
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(
            device, self.upgraded_lite_devices
        )
        body = {"cmd": [{"fn": fan_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        # 2. No additional notification needed for direct MQTT commands.

    async def set_ac_swing_mode(self, device_id: str, swing_mode: str) -> None:
        """Set AC swing mode."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        swing_val = AC_SWING_MODES_REVERSE.get(swing_mode.lower())
        if swing_val is None:
            return

        self._update_state_cache(
            device_id,
            {
                "SwingState": {"v": swing_val},
                "ss": swing_val,
                "5": swing_val,
                "Timestamp": int(time.time()),
            },
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(
            device, self.upgraded_lite_devices
        )
        body = {"cmd": [{"ss": swing_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        # 2. No additional notification needed for direct MQTT commands.

    async def set_ac_horizontal_swing(self, device_id: str, position: int) -> None:
        """Set AC horizontal swing position."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        self._update_state_cache(
            device_id,
            {
                "SwingStateHorizontal": {"v": position},
                "ssh": position,
                "Timestamp": int(time.time()),
            },
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(
            device, self.upgraded_lite_devices
        )
        body = {"cmd": [{"ssh": position, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

    async def set_ac_power_button(self, device_id: str) -> None:
        """Toggle AC power via MQTT."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(
            device, self.upgraded_lite_devices
        )
        body = {"cmd": [{"1": 0, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

    async def set_ac_mode_button(self, device_id: str) -> None:
        """Cycle AC mode via MQTT."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(
            device, self.upgraded_lite_devices
        )
        body = {"cmd": [{"2": 0, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

    async def set_ac_stpt_buttons(self, device_id: str, direction: str) -> None:
        """Adjust AC setpoint via MQTT buttons."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(
            device, self.upgraded_lite_devices
        )
        # 0=Down, 1=Up
        val = 1 if direction.lower() == "up" else 0
        body = {"cmd": [{"3": val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

    # Magic Upgrade
    async def async_upgrade_lite_device(self, device_id: str) -> bool:
        """Convert a Lite device to a Full device."""
        device = self.devices.get(device_id)
        if not device:
            return False

        _LOGGER.warning("Initiating Magic Upgrade for %s", device_id)
        url = f"{BASE_URL}/devices/{device_id}"
        try:
            await self.client.async_request("POST", url, json={"Model": "BB-V2-0"})
            return True
        except Exception as e:
            _LOGGER.error("Magic Upgrade failed: %s", e)
            return False

    async def async_downgrade_lite_device(self, device_id: str) -> bool:
        """Convert a Full device back to Light device."""
        device = self.devices.get(device_id)
        if not device:
            return False

        _LOGGER.warning("Initiating Magic Revert for %s", device_id)
        url = f"{BASE_URL}/devices/{device_id}"
        try:
            await self.client.async_request("POST", url, json={"Model": "BB-V2-0-L"})
            return True
        except Exception as e:
            _LOGGER.error("Magic Revert failed: %s", e)
            return False

    async def async_send_killer_ping(self, device_id: str) -> bool:
        """Send killer ping to restart device into pairing mode.

        WARNING: This will disconnect the device from the network.
        The device will need to be re-paired using the Mysa app.
        """
        device = self.devices.get(device_id)
        if not device:
            return False

        _LOGGER.warning(
            "Sending Killer Ping to %s - Device will restart into pairing mode!",
            device_id,
        )

        timestamp = int(time.time())
        body = {
            "Device": device_id.lower(),
            "Timestamp": timestamp,
            "MsgType": 5,
            "EchoID": 1,
        }

        try:
            await self.realtime.send_command(
                device_id, body, self.client.user_id, msg_type=5, wrap=False
            )
            return True
        except Exception as e:
            _LOGGER.error("Killer Ping failed: %s", e)
            return False

    # Helpers

    def _check_staleness(
        self,
        device_id: str,
        incoming_ts: int | None,
        filter_stale: bool,
        incoming_version: int | None = None,
        shadow_name: str | None = None,
    ) -> bool:
        """Check if update is stale. Returns True if stale (should ignore)."""
        # incoming_ts passed in

        if not hasattr(self, "_latest_timestamp"):
            self._latest_timestamp = {}
        if not hasattr(self, "_shadow_versions"):
            self._shadow_versions = {}
        if not hasattr(self, "_clock_skew"):
            self._clock_skew = {}

        if self._check_shadow_version_staleness(
            device_id, incoming_version, shadow_name, filter_stale
        ):
            return True

        return self._check_timestamp_staleness(device_id, incoming_ts, filter_stale)

    def _check_shadow_version_staleness(
        self,
        device_id: str,
        incoming_version: int | None,
        shadow_name: str | None,
        filter_stale: bool,
    ) -> bool:
        """Check if shadow version is stale."""
        # 1. Version Check (Preferred for Shadows)
        if incoming_version is not None and shadow_name is not None:
            if device_id not in self._shadow_versions:
                self._shadow_versions[device_id] = {}
            current_version = self._shadow_versions[device_id].get(shadow_name, 0)

            # Record when we last saw this version
            if not hasattr(self, "_shadow_version_timestamps"):
                self._shadow_version_timestamps = {}
            if device_id not in self._shadow_version_timestamps:
                self._shadow_version_timestamps[device_id] = {}

            last_v_ts = self._shadow_version_timestamps[device_id].get(shadow_name, 0)
            now = time.time()

            if incoming_version < current_version:
                # RELAXATION: If the current version in cache hasn't changed for 5 mins,
                # or if the jump back is massive (reset), accept the update anyway.
                if (now - last_v_ts > 300) or (
                    current_version - incoming_version > 1000
                ):
                    _LOGGER.debug(
                        "Device %s shadow %s: Accepting lower version due to age or reset"
                        " (v: %s, current: %s, age: %.0fs)",
                        device_id,
                        shadow_name,
                        incoming_version,
                        current_version,
                        now - last_v_ts,
                    )
                else:
                    _LOGGER.debug(
                        "Device %s shadow %s: Ignoring stale version (v: %s, current: %s)",
                        device_id,
                        shadow_name,
                        incoming_version,
                        current_version,
                    )
                    return True

            if incoming_version == current_version and filter_stale:
                return True

            self._shadow_versions[device_id][shadow_name] = max(
                current_version, incoming_version
            )
            self._shadow_version_timestamps[device_id][shadow_name] = now
        return False

    def _check_timestamp_staleness(
        self, device_id: str, incoming_ts: int | None, filter_stale: bool
    ) -> bool:
        """Check if timestamp is stale."""
        current_ts = self._latest_timestamp.get(device_id, 0)
        last_cmd_time = self._last_command_time.get(device_id, 0)
        now = time.time()

        # 2. Timestamp Check
        if incoming_ts is not None:
            # Update clock skew estimate
            # skew = mqtt_ts - local_ts
            # So mqtt_ts = local_ts + skew
            self._clock_skew[device_id] = incoming_ts - now

            # For ST-V1-0 (Shadow) devices, we tighten the stale check.
            # AWS Shadow timestamps can often slightly lag behind the wall clock
            # (especially after an optimistic update with time.time()).
            is_shadow = "ST-V1-0" in str(
                self.devices.get(device_id, {}).get("Model", "")
            )

            if is_shadow and not filter_stale and (now - last_cmd_time >= 90):
                # Accept MQTT shadow updates even if slightly behind (up to 10s)
                # AWS Shadows can have significant clock skew vs NTP.
                if incoming_ts < current_ts - 10:
                    _LOGGER.debug(
                        "Device %s: Ignoring genuinely stale shadow update (ts: %s, current: %s)",
                        device_id,
                        incoming_ts,
                        current_ts,
                    )
                    return True
            elif is_shadow and filter_stale:
                # ST-V1 HTTP poll. Telemetry timestamps natively lag behind shadow timestamps.
                # Do NOT reject the payload, otherwise exclusive telemetry (humidity) is lost.
                # `_filter_stale_updates` inherently protects volatile keys from snap-back.
                pass
            else:
                if incoming_ts < current_ts:
                    _LOGGER.debug(
                        "Device %s: Ignoring stale update (ts: %s, current: %s, filter_stale: %s)",
                        device_id,
                        incoming_ts,
                        current_ts,
                        filter_stale,
                    )
                    return True

            if incoming_ts > current_ts:
                _LOGGER.debug(
                    "Device %s: Accepted fresh update (ts: %s, previous: %s)",
                    device_id,
                    incoming_ts,
                    current_ts,
                )
            self._latest_timestamp[device_id] = max(current_ts, incoming_ts)
        elif filter_stale:
            _LOGGER.debug(
                "Device %s: Processing update with no timestamp (last cmd: %.0fs ago)",
                device_id,
                time.time() - last_cmd_time,
            )
        return False

    def _update_state_cache(
        self, device_id: str, updates: dict[str, Any], filter_stale: bool = False
    ) -> None:
        if not hasattr(self, "_latest_timestamp"):
            self._latest_timestamp = {}
        if not hasattr(self, "_clock_skew"):
            self._clock_skew = {}
        if not hasattr(self, "_last_command_time"):
            self._last_command_time = {}

        if device_id not in self.states:
            self.states[device_id] = {}

        # ST-V1 Mixed Shadow Data extraction
        # We perform full extraction (including sensors) for state updates
        if "st-v1" in self.devices.get(device_id, {}).get("Model", "").lower():
            # Never skip sensors here. Both MQTT and HTTP need sensor data.
            # skip_sensors was erroneously tied to 'not filter_stale'
            self._extract_stv10_shadow_data(updates, skip_sensors=False)

        now = time.time()
        incoming_ts = MysaDeviceLogic.extract_timestamp(updates)
        incoming_version = updates.get("version")
        shadow_name = updates.get("_shadow_name")

        # Check staleness
        if self._check_staleness(
            device_id, incoming_ts, filter_stale, incoming_version, shadow_name
        ):
            return

        self._advance_timeline(device_id, incoming_ts, now, filter_stale)
        updates = self._filter_stale_updates(
            device_id, updates, filter_stale, incoming_ts, now
        )

        self.states[device_id].update(updates)
        self._update_brightness_entities(device_id, updates)

    def _advance_timeline(
        self, device_id: str, incoming_ts: int | None, now: float, filter_stale: bool
    ) -> None:
        """Advance timeline for optimistic updates."""
        # Only advance timeline for optimistic updates (no timestamp + not an HTTP poll).
        # We also enforce that a command was actually sent recently (within 1 second)
        # to distinguish from arbitrary network packets arriving with no timestamp.
        if incoming_ts is None and not filter_stale:
            last_cmd_time = self._last_command_time.get(device_id, 0)
            if now - last_cmd_time < 1.0:
                # Estimate what the MQTT timestamp would be for this local action
                skew = self._clock_skew.get(device_id, 0)
                estimated_mqtt_ts = int(now + skew)
                current_latest = self._latest_timestamp.get(device_id, 0)
                # Advance the timeline so older MQTT messages are blocked
                self._latest_timestamp[device_id] = max(
                    current_latest, estimated_mqtt_ts
                )
                _LOGGER.debug(
                    "Device %s: Advanced timeline for optimistic update "
                    "(estimated ts: %s, current: %s)",
                    device_id,
                    estimated_mqtt_ts,
                    current_latest,
                )

    def _filter_stale_updates(
        self,
        device_id: str,
        updates: dict[str, Any],
        filter_stale: bool,
        incoming_ts: int | None,
        now: float,
    ) -> dict[str, Any]:
        """Filter out stale keys from updates."""
        last_cmd_time = self._last_command_time.get(device_id, 0)
        # Filtering logic
        if now - last_cmd_time < 90:
            skew = self._clock_skew.get(device_id, 0)
            # Estimate what time it was on the device when we sent the command
            cmd_mqtt_ts = last_cmd_time + skew

            # Condition for filtering out stale-prone keys:
            # 1. It's a Cloud Poll (filter_stale=True) which likely lacks a timestamp.
            # 2. It HAS a timestamp (Cloud or MQTT) but that timestamp is older
            #    than our last command (Source: Snap-back).
            # Note: We use strict < here to align with _check_staleness strict mode.
            should_filter = (filter_stale and incoming_ts is None) or (
                # We use strict < here to align with _check_staleness strict mode.
                incoming_ts is not None and incoming_ts < (cmd_mqtt_ts)
            )

            if should_filter:
                stale_keys = {
                    "Mode",
                    "md",
                    "mode",
                    "TstatMode",
                    "SetPoint",
                    "sp",
                    "stpt",
                    "target_heat",
                    "target_cool",
                    "targetHeat",
                    "targetCool",
                    "heatSetpoint",
                    "coolSetpoint",
                    "Lock",
                    "lc",
                    "lk",
                    "ButtonState",
                    "Brightness",
                    "br",
                    "MinBrightness",
                    "MaxBrightness",
                    "AutoBrightness",
                    "ab",
                    "ProximityMode",
                    "pr",
                    "Proximity",
                    "px",
                    "ACState",
                    "ac",
                    "1",
                    "2",
                    "3",
                    "4",
                    "5",
                }
                filtered_updates = {
                    k: v for k, v in updates.items() if k not in stale_keys
                }
                if (
                    filtered_updates != updates
                ):  # Only log if keys were actually filtered
                    _LOGGER.debug(
                        "Device %s: Filtered %d stale keys from update "
                        "within 90s window (ts: %s, cmd_ts: %s)",
                        device_id,
                        len(stale_keys.intersection(updates.keys())),
                        incoming_ts,
                        int(cmd_mqtt_ts),
                    )
                return filtered_updates
        return updates

    def _update_brightness_entities(
        self, device_id: str, updates: dict[str, Any]
    ) -> None:
        """Update flattened brightness entities from BrightnessSettings."""
        # If BrightnessSettings was updated, extract flattened keys for number entities
        if "BrightnessSettings" in self.states[device_id]:
            br_settings = self.states[device_id]["BrightnessSettings"]
            if isinstance(br_settings, dict):
                if "i_br" in br_settings:
                    self.states[device_id]["MinBrightness"] = br_settings["i_br"]
                if "a_br" in br_settings:
                    self.states[device_id]["MaxBrightness"] = br_settings["a_br"]
                if "a_b" in br_settings:
                    self.states[device_id]["AutoBrightness"] = br_settings["a_b"] == 1
        elif any(
            k in updates for k in ["MinBrightness", "MaxBrightness", "AutoBrightness"]
        ):
            # If we got top-level keys but NO BrightnessSettings, ensure we don't
            # loose them if we build a BrightnessSettings object later.
            pass  # They are already updated in the state above.

    def _get_brightness_object(self, device_id: str) -> dict[str, int]:
        """Build the brightness settings object for MQTT commands."""
        state = self.states.get(device_id, {})
        br = state.get("BrightnessSettings")
        if not br or not isinstance(br, dict):
            br = state.get("Brightness", {})

        if not isinstance(br, dict):
            br = {}

        # Fallbacks: merge with top-level state keys normalized by MysaDeviceLogic
        a_b = br.get("a_b")
        if a_b is None:
            a_b = 1 if state.get("AutoBrightness", True) else 0

        a_br = br.get("a_br")
        if a_br is None:
            a_br = state.get("MaxBrightness", 100)

        i_br = br.get("i_br")
        if i_br is None:
            i_br = state.get("MinBrightness", 10)  # Default to 10% instead of 50%

        return {
            "a_b": int(a_b),
            "a_br": int(a_br),
            "i_br": int(i_br),
            "a_dr": int(br.get("a_dr", 60)),
            "i_dr": int(br.get("i_dr", 30)),
        }

    def _update_brightness_cache(self, device_id: str, key: str, value: int) -> None:
        if device_id not in self.states:
            self.states[device_id] = {}

        # Always use BrightnessSettings for the config object
        if "BrightnessSettings" not in self.states[device_id]:
            self.states[device_id]["BrightnessSettings"] = self._get_brightness_object(
                device_id
            )

        br_data = cast(dict[str, Any], self.states[device_id]["BrightnessSettings"])
        if isinstance(br_data, dict):
            br_data[key] = value

    # MQTT Lifecycle
    async def start_mqtt_listener(self) -> None:
        """Start MQTT listener (non-blocking)."""
        # Ensure we have device list
        self.realtime.set_devices(list(self.devices.keys()))
        await self.realtime.start()

        # Use async_create_background_task so this infinite loop does NOT block HA startup.
        # HA will still cancel it cleanly on shutdown.
        self._bg_polling_task = self.hass.async_create_background_task(
            self._periodic_legacy_mqtt_poll(),
            name="mysa_legacy_poll",
        )

        # Create background task for waiting logic to avoid blocking startup
        self.hass.async_create_task(self._wait_and_refresh_mqtt())

    async def _wait_and_refresh_mqtt(self) -> None:
        """Wait for MQTT connection and request initial updates with retries for ST-V1-0."""

        # 1. Wait for initial connection
        connected = await self.realtime.wait_until_connected(timeout=35.0)
        if not connected:
            _LOGGER.warning(
                "MQTT connection timed out during startup, initial update skipped"
            )
            return

        _LOGGER.debug("MQTT connected, requesting initial update for all devices")

        # 2. Initial Request Round
        tasks = []
        s1_devices_pending = []
        for device_id in self.devices:
            if "ST-V1-0" in self.devices[device_id].get("Model", ""):
                s1_devices_pending.append(device_id)
                tasks.append(self.fetch_stv10_shadows(device_id))
            else:
                tasks.append(self.update_request(device_id))

        if tasks:
            await asyncio.gather(*tasks)

        # Initial round complete. Subsequent retries are handled per-entity in climate.py
        # using a more efficient Fibonacci backoff and data-existence checks.
        return

    async def stop_mqtt_listener(self) -> None:
        """Stop MQTT listener."""
        if self._bg_polling_task is not None:
            self._bg_polling_task.cancel()
            self._bg_polling_task = None
        await self.realtime.stop()

    async def _periodic_legacy_mqtt_poll(self) -> None:
        """Periodically trigger MQTT polls for legacy devices."""
        _LOGGER.debug("Starting periodic legacy MQTT polling task")
        while True:
            try:
                # Poll every 120 seconds
                await asyncio.sleep(120)

                if not self.realtime.is_connected:
                    continue

                poll_tasks = []
                for device_id, device_data in self.devices.items():
                    if not MysaDeviceLogic.is_stv10_device(device_data):
                        poll_tasks.append(self.async_send_state_poll(device_id))

                if poll_tasks:
                    results = await asyncio.gather(*poll_tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, Exception):
                            # We can't easily get the ID here without zipping,
                            # but this is enough for coverage
                            _LOGGER.error("Error in legacy MQTT polling task: %s", res)
            except asyncio.CancelledError:
                _LOGGER.debug("Legacy MQTT polling task cancelled")
                break
            # Justification: Polling runs in background;
            # broad except prevents it from crashing HA completely.
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.error("Fatal error in legacy MQTT polling task: %s", e)

    async def set_min_setpoint(self, device_id: str, temperature: float) -> None:
        """Set minimum setpoint limit via HTTP."""
        self._last_command_time[device_id] = time.time()

        # Consistent optimistic update for ST-V1-0
        update = {"MinSetpoint": temperature, "Timestamp": int(time.time())}
        if "ST-V1-0" in str(self.devices.get(device_id, {}).get("Model", "")):
            update["lockoutMin"] = int(temperature * 100)

        self._update_state_cache(device_id, update)
        if self.coordinator_callback:
            await self.coordinator_callback()

        if "ST-V1-0" in str(self.devices.get(device_id, {}).get("Model", "")):
            # ST-V1-0 uses targetHeat/targetCool shadow updates
            await self.client.post_state_update(
                device_id,
                {"source": 3, "targetHeat": {"lockoutMin": int(temperature * 100)}},
            )
            await self.client.post_state_update(
                device_id,
                {"source": 3, "targetCool": {"lockoutMin": int(temperature * 100)}},
            )
        else:
            await self.client.set_device_setting_http(
                device_id, {"MinSetpoint": temperature}, legacy=True
            )
        await self.notify_settings_changed(device_id)

    async def set_max_setpoint(self, device_id: str, temperature: float) -> None:
        """Set maximum setpoint limit via HTTP."""
        self._last_command_time[device_id] = time.time()

        # Consistent optimistic update for ST-V1-0
        update = {"MaxSetpoint": temperature, "Timestamp": int(time.time())}
        if "ST-V1-0" in str(self.devices.get(device_id, {}).get("Model", "")):
            update["lockoutMax"] = int(temperature * 100)

        self._update_state_cache(device_id, update)
        if self.coordinator_callback:
            await self.coordinator_callback()

        if "ST-V1-0" in str(self.devices.get(device_id, {}).get("Model", "")):
            # ST-V1-0 uses targetHeat/targetCool shadow updates
            await self.client.post_state_update(
                device_id,
                {"source": 3, "targetHeat": {"lockoutMax": int(temperature * 100)}},
            )
            await self.client.post_state_update(
                device_id,
                {"source": 3, "targetCool": {"lockoutMax": int(temperature * 100)}},
            )
        else:
            await self.client.set_device_setting_http(
                device_id, {"MaxSetpoint": temperature}, legacy=True
            )
        await self.notify_settings_changed(device_id)

    async def set_temperature_format(self, device_id: str, is_fahrenheit: bool) -> None:
        """Set temperature format via HTTP."""
        self._last_command_time[device_id] = time.time()
        fmt = "fahrenheit" if is_fahrenheit else "celsius"
        self._update_state_cache(
            device_id, {"Format": fmt, "Timestamp": int(time.time())}
        )
        if self.coordinator_callback:
            await self.coordinator_callback()

        await self.client.set_device_setting_http(
            device_id, {"Format": fmt}, legacy=True
        )
        await self.notify_settings_changed(device_id)

    async def set_duty_cycle_opt(self, device_id: str, value: int) -> None:
        """Set duty cycle optimization (Baseboard) via HTTP."""
        self._last_command_time[device_id] = time.time()
        self._update_state_cache(
            device_id, {"DutyCycleOpt": value, "Timestamp": int(time.time())}
        )
        if self.coordinator_callback:
            await self.coordinator_callback()

        await self.client.set_device_setting_http(
            device_id, {"DutyCycleOpt": value}, legacy=True
        )
        await self.notify_settings_changed(device_id)
