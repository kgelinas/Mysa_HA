import logging
import time
from typing import Any, Dict, List, Optional, cast, Callable

from aiohttp import ClientSession

from .mysa_auth import BASE_URL
from .client import MysaClient
from .realtime import MysaRealtime
from .device import MysaDeviceLogic
from .const import (
    AC_FAN_MODES_REVERSE,
    AC_SWING_MODES_REVERSE,
    AC_MODE_OFF,
    AC_MODE_COOL,
    AC_MODE_HEAT,
    AC_MODE_AUTO,
    AC_MODE_DRY,
    AC_MODE_FAN_ONLY,
)

_LOGGER = logging.getLogger(__name__)


class MysaApi:
    """Mysa API Client."""

    # pylint: disable=too-many-arguments, too-many-public-methods
    # pylint: disable=too-many-instance-attributes, too-many-positional-arguments
    # Justification: Facade class exposing full API surface and maintaining state for all devices.
    def __init__(
        self,
        username: str,
        password: str,
        hass: Any,  # Changed from HomeAssistant
        coordinator_callback: Optional[Callable[[], Any]] = None,
        upgraded_lite_devices: Optional[List[str]] = None,
        estimated_max_current: int = 0,
        wattages: Optional[Dict[str, int]] = None,
        simulated_energy: bool = False,
        websession: Optional[ClientSession] = None
    ) -> None:
        """Initialize the API."""
        self.hass = hass
        self.coordinator_callback = coordinator_callback
        self.upgraded_lite_devices = upgraded_lite_devices or []
        self.estimated_max_current = estimated_max_current
        self.wattages = wattages or {}
        self.simulated_energy = simulated_energy
        self._metadata_requested: Dict[str, float] = {}
        self._latest_timestamp: Dict[str, int] = {}

        # Get websession if not provided
        if websession is None:
            # async_get_clientsession is removed.
            # Assuming hass has a way to get a session or it's passed.
            # ClientSession can be instantiated directly if not provided.
            websession = ClientSession()

        # State
        self.states: Dict[str, Any] = {}
        self._last_command_time: Dict[str, float] = {}  # device_id: timestamp

        # Components
        self.client = MysaClient(hass, username, password, websession)
        # Note: we initialize Realtime here but start it later
        # Realtime needs callbacks
        # We need to ensure _on_mqtt_update matches the callback signature in Realtime
        self.realtime = MysaRealtime(
            hass,
            get_signed_url_callback=self.client.get_signed_mqtt_url,
            on_update_callback=self._on_mqtt_update
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
    def devices(self) -> Dict[str, Any]:
        """Return devices."""
        return self.client.devices

    @devices.setter
    def devices(self, value: Dict[str, Any]) -> None:
        self.client.devices = value

    @property
    def homes(self) -> List[Any]:
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

    # Authentication & Setup
    async def authenticate(self, use_cache: bool = True) -> bool:
        """Authenticate with Mysa."""
        return await self.client.authenticate(use_cache=use_cache)

    async def get_devices(self) -> Dict[str, Any]:
        """Get devices."""
        devices = await self.client.get_devices()
        # Update realtime subscription list
        self.realtime.set_devices(list(devices.keys()))
        return devices

    async def fetch_homes(self) -> None:
        """Fetch homes and zones."""
        await self.client.fetch_homes()

    async def fetch_firmware_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Fetch firmware update info."""
        return await self.client.fetch_firmware_info(device_id)

    def get_electricity_rate(self, device_id: str) -> Optional[float]:
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

    async def get_state(self) -> Dict[str, Any]:
        """Get full state of all devices (HTTP merge)."""
        # Fetch fresh HTTP state
        new_states = await self.client.get_state()

        for device_id, new_data in new_states.items():
            self._update_state_cache(device_id, new_data, filter_stale=True)

        return self.states

    async def _on_mqtt_update(
        self, device_id: str, state_update: Dict[str, Any], resolve_safe_id: Optional[bool] = False
    ) -> None:
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
                _LOGGER.debug(
                    "Unknown device (safe ID: %s), likely stale",
                    safe_id
                )
                return

        # Normalize
        MysaDeviceLogic.normalize_state(state_update)

        # 1. TREAT AS COMMAND: Update timestamp so subsequent Cloud Polls respecting
        # the 90s "freshness guard" will filter out stale keys (e.g. SetPoint)
        # effectively prioritizing this MQTT update over lagging Cloud data.
        self._last_command_time[device_id] = time.time()

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

        missing_metadata = (not fw_version or fw_version == "None" or not ip_addr)

        if missing_metadata:
            now = time.time()
            last_req = self._metadata_requested.get(device_id, 0)
            if now - last_req > 300:  # 5 minutes
                _LOGGER.debug(
                    "Metadata (FW/IP) missing for %s, requesting dump (last req: %.0fs ago)...",
                    device_id, now - last_req
                )
                self._metadata_requested[device_id] = now
                # Use a task to not block the callback
                self.hass.async_create_task(self.update_request(device_id))

        # Trigger HA update
        if self.coordinator_callback:
            if callable(self.coordinator_callback):
                await self.coordinator_callback()

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
                "Timestamp": int(time.time())
            }
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)

        body = {
            "cmd": [{"sp": target_val, "stpt": target_val, "a_sp": target_val, "tm": -1}],
            "type": payload_type,
            "ver": 1
        }
        await self.realtime.send_command(device_id, body, self.client.user_id)

        # 2. No additional notification needed for direct MQTT commands.
        # The device will echo its state automatically.

    async def set_hvac_mode(self, device_id: str, hvac_mode: str) -> None:
        """Set HVAC mode via MQTT."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        mode_str = str(hvac_mode).lower()
        device = self.devices.get(device_id)

        if MysaDeviceLogic.is_ac_device(device):
            # AC mode mapping
            if "off" in mode_str:
                mode_val = AC_MODE_OFF
            elif "heat_cool" in mode_str or "auto" in mode_str:
                mode_val = AC_MODE_AUTO
            elif "cool" in mode_str:
                mode_val = AC_MODE_COOL
            elif "heat" in mode_str:
                mode_val = AC_MODE_HEAT
            elif "dry" in mode_str:
                mode_val = AC_MODE_DRY
            elif "fan" in mode_str:
                mode_val = AC_MODE_FAN_ONLY
            else:
                mode_val = AC_MODE_OFF
        else:
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
                "Timestamp": int(time.time())
            }
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)
        body = {"cmd": [{"md": mode_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        # 2. No additional notification needed for direct MQTT commands.
        # The device will echo its state automatically.

    async def notify_settings_changed(self, device_id: str) -> None:
        """Notify device to check cloud settings (MsgType 6)."""
        timestamp = int(time.time())
        body = {
            "Device": device_id.upper(),
            "EventType": 0,
            "MsgType": 6,
            "Timestamp": timestamp
        }
        # MsgType 6, wrap=False
        await self.realtime.send_command(
            device_id, body, self.client.user_id, msg_type=6, wrap=False
        )

    async def update_request(self, device_id: str) -> None:
        """Request metadata dump (MsgType 7): FW version, IP, Serial, MAC."""
        timestamp = int(time.time())
        body = {
            "Device": device_id,
            "Timestamp": timestamp,
            "MsgType": 7
        }
        # MsgType 7, wrap=False
        await self.realtime.send_command(
            device_id, body, self.client.user_id, msg_type=7, wrap=False
        )

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
                "Timestamp": int(time.time())
            }
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        await self.client.set_device_setting_http(device_id, {"Lock": lock_val})

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
                "Timestamp": int(time.time())
            }
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        await self.client.set_device_setting_http(device_id, {"IsThermostatic": enabled})

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

    # Helpers for AC
    def is_ac_device(self, device_id: str) -> bool:
        """Check if device is an AC unit."""
        return MysaDeviceLogic.is_ac_device(self.devices.get(device_id, {}))

    def get_ac_supported_caps(self, device_id: str) -> Dict[str, Any]:
        """Get supported capabilities for AC."""
        device = self.devices.get(device_id, {})
        return dict(device.get("SupportedCaps", {}))

    # Shortcuts for other setters implementation ...
    # Since I'm rewriting the whole file I MUST include all previous methods.

    async def set_proximity(self, device_id: str, enabled: bool) -> None:
        """Set proximity sensing state via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        self._last_command_time[device_id] = time.time()
        _LOGGER.debug("set_proximity(%s, %s) - Optimistic update", device_id, enabled)
        self._update_state_cache(
            device_id,
            {
                "ProximityMode": enabled,
                "px": enabled,
                "pr": 1 if enabled else 0,
                "Proximity": enabled,
                "Timestamp": int(time.time())
            }
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        await self.client.set_device_setting_http(device_id, {"ProximityMode": enabled})

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
                "Timestamp": int(time.time())
            }
        )
        self._update_brightness_cache(device_id, "a_b", 1 if enabled else 0)

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        await self.client.set_device_setting_http(device_id, {"AutoBrightness": enabled})

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

    async def set_min_brightness(self, device_id: str, value: int) -> None:
        """Set minimum brightness via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        self._update_brightness_cache(device_id, "i_br", value)
        self._update_state_cache(
            device_id,
            {"MinBrightness": value, "mnbr": value, "Timestamp": int(time.time())}
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        await self.client.set_device_setting_http(device_id, {"MinBrightness": value})

        # 2. Notify Device (Cloud -> Device via MsgType 6)
        await self.notify_settings_changed(device_id)

    async def set_max_brightness(self, device_id: str, value: int) -> None:
        """Set maximum brightness via HTTP."""
        # 0. IMMEDIATE OPTIMISTIC UPDATE
        self._last_command_time[device_id] = time.time()
        self._update_brightness_cache(device_id, "a_br", value)
        self._update_state_cache(
            device_id,
            {"MaxBrightness": value, "mxbr": value, "Timestamp": int(time.time())}
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. HTTP Command
        await self.client.set_device_setting_http(device_id, {"MaxBrightness": value})

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
                "Timestamp": int(time.time())
            }
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)
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
                "Timestamp": int(time.time())
            }
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)
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
                "Timestamp": int(time.time())
            }
        )

        # Trigger UI refresh NOW
        if self.coordinator_callback:
            await self.coordinator_callback()

        # 1. MQTT Command
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)
        body = {"cmd": [{"ssh": position, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        # 2. No additional notification needed for direct MQTT commands.

    # Magic Upgrade
    async def async_upgrade_lite_device(self, device_id: str) -> bool:
        """Convert a Lite device to a Full device."""
        device = self.devices.get(device_id)
        if not device:
            return False

        _LOGGER.warning("Initiating Magic Upgrade for %s", device_id)
        url = f"{BASE_URL}/devices/{device_id}"
        try:
            await self.client.async_request("POST", url, json={'Model': 'BB-V2-0'})
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
            await self.client.async_request("POST", url, json={'Model': 'BB-V2-0-L'})
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
            device_id
        )

        timestamp = int(time.time())
        body = {
            "Device": device_id.upper(),
            "Timestamp": timestamp,
            "MsgType": 5,
            "EchoID": 1
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

    def _extract_timestamp(self, updates: Dict[str, Any]) -> Optional[int]:
        """Extract and validate timestamp from updates."""
        ts = updates.get('Timestamp') or updates.get('time')
        if ts is not None:
            try:
                return int(ts)
            except (ValueError, TypeError):
                pass
        return None

    def _update_state_cache(
        self, device_id: str, updates: Dict[str, Any], filter_stale: bool = False
    ) -> None:
        if device_id not in self.states:
            self.states[device_id] = {}

        now = time.time()
        last_cmd_time = self._last_command_time.get(device_id, 0)

        # Timestamp-Based Freshness
        incoming_ts = self._extract_timestamp(updates)

        if not hasattr(self, "_latest_timestamp"):
            self._latest_timestamp = {}
        current_ts = self._latest_timestamp.get(device_id, 0)

        if incoming_ts is not None:
            if incoming_ts < current_ts or (incoming_ts == current_ts and filter_stale):
                return
            self._latest_timestamp[device_id] = incoming_ts

        # Filtering logic
        if incoming_ts is None and filter_stale and (now - last_cmd_time < 90):
            stale_keys = {
                'Mode', 'md', 'TstatMode', 'SetPoint', 'sp', 'stpt',
                'Lock', 'lc', 'lk', 'ButtonState',
                'Brightness', 'br', 'MinBrightness', 'MaxBrightness',
                'AutoBrightness', 'ab', 'ProximityMode', 'pr', 'Proximity', 'px',
                'ACState', 'ac', '1', '2', '3', '4', '5'
            }
            updates = {k: v for k, v in updates.items() if k not in stale_keys}

        self.states[device_id].update(updates)

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
        elif any(k in updates for k in ["MinBrightness", "MaxBrightness", "AutoBrightness"]):
            # If we got top-level keys but NO BrightnessSettings, ensure we don't
            # loose them if we build a BrightnessSettings object later.
            pass  # They are already updated in the state above.

    def _get_brightness_object(self, device_id: str) -> Dict[str, int]:
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
            self.states[device_id]["BrightnessSettings"] = self._get_brightness_object(device_id)

        br_data = cast(Dict[str, Any], self.states[device_id]["BrightnessSettings"])
        if isinstance(br_data, dict):
            br_data[key] = value

    # MQTT Lifecycle
    async def start_mqtt_listener(self) -> None:
        """Start MQTT listener."""
        # Ensure we have device list
        self.realtime.set_devices(list(self.devices.keys()))
        await self.realtime.start()

        # Wait for connection and force refresh
        if await self.realtime.wait_until_connected(timeout=35.0):
            _LOGGER.info("MQTT connected, requesting initial update for all devices")
            for device_id in self.devices:
                await self.update_request(device_id)
        else:
            _LOGGER.warning("MQTT connection timed out during startup, initial update skipped")

    async def stop_mqtt_listener(self) -> None:
        """Stop MQTT listener."""
        await self.realtime.stop()
