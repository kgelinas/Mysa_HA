import logging
import time

from .mysa_auth import BASE_URL
from .client import MysaClient
from .realtime import MysaRealtime
from .device import MysaDeviceLogic
from .const import AC_FAN_MODES_REVERSE, AC_SWING_MODES_REVERSE

_LOGGER = logging.getLogger(__name__)

class MysaApi:
    """Mysa API Client."""

    # pylint: disable=too-many-arguments, too-many-public-methods, too-many-instance-attributes, too-many-positional-arguments
    def __init__(
        self,
        username,
        password,
        hass,
        coordinator_callback=None,
        upgraded_lite_devices=None,
        estimated_max_current=0,
        wattages=None,
        simulated_energy=False,
        zone_overrides=None
    ):
        """Initialize the API."""
        self.hass = hass
        self.coordinator_callback = coordinator_callback
        self.upgraded_lite_devices = upgraded_lite_devices or []
        self.estimated_max_current = estimated_max_current
        self.wattages = wattages or {}
        self.simulated_energy = simulated_energy
        self.zone_overrides = zone_overrides or {}

        # State
        self.states = {}
        self._last_command_time = {}  # device_id: timestamp

        # Components
        self.client = MysaClient(hass, username, password)
        # Note: we initialize Realtime here but start it later
        # Realtime needs callbacks
        self.realtime = MysaRealtime(
            hass,
            get_signed_url_callback=self.client.get_signed_mqtt_url,
            on_update_callback=self._on_mqtt_update
        )

    # Properties delegating to components
    @property
    def username(self):
        """Return username."""
        return self.client.username

    @property
    def password(self):
        """Return password."""
        return self.client.password

    @property
    def devices(self):
        """Return devices."""
        return self.client.devices

    @devices.setter
    def devices(self, value):
        self.client.devices = value

    @property
    def homes(self):
        """Return homes."""
        return self.client.homes

    @property
    def zones(self):
        """Return zones."""
        return self.client.zones

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self.client.is_connected

    @property
    def is_mqtt_running(self) -> bool:
        """Return MQTT status."""
        return self.realtime.is_running

    # Authentication & Setup
    async def authenticate(self):
        """Authenticate with Mysa."""
        return await self.client.authenticate()

    async def get_devices(self):
        """Get devices."""
        devices = await self.client.get_devices()
        # Update realtime subscription list
        self.realtime.set_devices(list(devices.keys()))
        return devices

    async def fetch_homes(self):
        """Fetch homes and zones."""
        return await self.client.fetch_homes()

    def get_zone_name(self, zone_id):
        """Get friendly name for a zone ID."""
        if str(zone_id) in self.zone_overrides:
            return self.zone_overrides[str(zone_id)]
        return self.client.get_zone_name(zone_id)

    async def fetch_firmware_info(self, device_id):
        """Fetch firmware update info."""
        return await self.client.fetch_firmware_info(device_id)

    def get_electricity_rate(self, device_id):
        """Get electricity rate for a device."""
        return self.client.get_electricity_rate(device_id)

    # State Management
    async def get_state(self):
        """Get full state of all devices (HTTP merge)."""
        # Fetch fresh HTTP state
        new_states = await self.client.get_state()
        now = time.time()

        for device_id, new_data in new_states.items():
            if device_id not in self.states:
                self.states[device_id] = new_data
            else:
                # If we recently sent a command, ignore stale cloud status
                if now - self._last_command_time.get(device_id, 0) < 90:
                    _LOGGER.debug("Ignoring potentially stale HTTP state for %s", device_id)
                    stale_keys = [
                        'Mode', 'md', 'TstatMode', 'SetPoint', 'sp', 'stpt',
                        'Lock', 'lc', 'lk', 'ButtonState',
                        'Brightness', 'br', 'MinBrightness', 'MaxBrightness',
                        'AutoBrightness', 'ab', 'ProximityMode', 'pr', 'Proximity'
                    ]
                    filtered_data = {k: v for k, v in new_data.items() if k not in stale_keys}
                    self.states[device_id].update(filtered_data)
                else:
                    self.states[device_id].update(new_data)

        return self.states

    async def _on_mqtt_update(self, device_id, state_update, resolve_safe_id=False):
        """Handle MQTT update callback."""
        if resolve_safe_id:
            # Try to match safe ID to real ID
            safe_id = device_id
            found = False
            for real_id in self.devices:
                if real_id.replace(":", "").lower() == safe_id:
                    device_id = real_id
                    found = True
                    break
            if not found:
                _LOGGER.warning("Could not resolve device ID from safe ID: %s", safe_id)
                return

        # Normalize
        MysaDeviceLogic.normalize_state(state_update)

        # Update cache
        if device_id not in self.states:
            self.states[device_id] = state_update
        else:
            self.states[device_id].update(state_update)

        _LOGGER.info("MQTT state update for %s", device_id)

        # Trigger HA update
        if self.coordinator_callback:
            await self.coordinator_callback()

    # Commands
    async def set_target_temperature(self, device_id, temperature):
        """Set target temperature via MQTT."""
        self._last_command_time[device_id] = time.time()
        target_val = float(temperature)

        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)

        body = {
            "cmd": [{"sp": target_val, "stpt": target_val, "a_sp": target_val, "tm": -1}],
            "type": payload_type,
            "ver": 1
        }
        await self.realtime.send_command(device_id, body, self.client.user_id)
        await self.notify_settings_changed(device_id)

    async def set_hvac_mode(self, device_id, hvac_mode):
        """Set HVAC mode via MQTT."""
        self._last_command_time[device_id] = time.time()
        mode_str = str(hvac_mode).lower()
        device = self.devices.get(device_id)

        if MysaDeviceLogic.is_ac_device(device):
            # AC mode mapping
            if "off" in mode_str:
                mode_val = 0
            elif "cool" in mode_str:
                mode_val = 2
            elif "heat" in mode_str:
                mode_val = 1
            elif "auto" in mode_str:
                mode_val = 3
            elif "dry" in mode_str:
                mode_val = 4
            elif "fan" in mode_str:
                mode_val = 5
            else:
                mode_val = 0
        else:
            mode_val = 1 if "off" in mode_str else 3

        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)
        body = {"cmd": [{"md": mode_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)
        await self.notify_settings_changed(device_id)

    async def notify_settings_changed(self, device_id):
        """Notify device to check settings."""
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

    # ... Other Setters (Lock, Brightness, AC features) ...
    # Implementing pattern: _last_command -> Payload -> Send -> Optimistic Update -> Notify

    async def set_lock(self, device_id, locked: bool):
        """Set lock state."""
        self._last_command_time[device_id] = time.time()
        lock_val = 1 if locked else 0
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)

        # MQTT
        body = {"cmd": [{"lk": lock_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        # HTTP Silent
        await self.client.set_device_setting_silent(device_id, {"Lock": lock_val})

        # Optimistic
        self._update_state_cache(device_id, {"Lock": {"v": lock_val}})
        await self.notify_settings_changed(device_id)

    async def set_ac_climate_plus(self, device_id, enabled: bool):
        """Set Climate+ state."""
        self._last_command_time[device_id] = time.time()
        it_val = 1 if enabled else 0
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)

        body = {"cmd": [{"it": it_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        self._update_state_cache(device_id, {"IsThermostatic": {"v": it_val}, "it": it_val})
        await self.notify_settings_changed(device_id)

    # Helpers for AC
    def is_ac_device(self, device_id) -> bool:
        """Check if device is an AC unit."""
        return MysaDeviceLogic.is_ac_device(self.devices.get(device_id, {}))

    def get_ac_supported_caps(self, device_id) -> dict:
        """Get supported capabilities for AC."""
        device = self.devices.get(device_id, {})
        return device.get("SupportedCaps", {})

    # Shortcuts for other setters implementation ...
    # Since I'm rewriting the whole file I MUST include all previous methods.

    async def set_proximity(self, device_id, enabled: bool):
        """Set proximity sensing state."""
        self._last_command_time[device_id] = time.time()
        pr_val = 1 if enabled else 0
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)

        body = {"cmd": [{"pr": pr_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        await self.client.set_device_setting_silent(device_id, {"ProximityMode": enabled})
        self._update_state_cache(device_id, {"ProximityMode": enabled})
        await self.notify_settings_changed(device_id)

    async def set_auto_brightness(self, device_id, enabled: bool):
        """Set auto brightness state."""
        self._last_command_time[device_id] = time.time()
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)

        br_obj = self._get_brightness_object(device_id)
        br_obj["a_b"] = 1 if enabled else 0

        body = {"cmd": [{"tm": -1, "br": br_obj}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        await self.client.set_device_setting_silent(device_id, {"AutoBrightness": enabled})
        self._update_state_cache(device_id, {"AutoBrightness": enabled})
        await self.notify_settings_changed(device_id)

    async def set_min_brightness(self, device_id, value: int):
        """Set minimum brightness."""
        self._last_command_time[device_id] = time.time()
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)

        br_obj = self._get_brightness_object(device_id)
        br_obj["i_br"] = value

        body = {"cmd": [{"tm": -1, "br": br_obj}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        await self.client.set_device_setting_silent(device_id, {"MinBrightness": value})
        self._update_brightness_cache(device_id, "i_br", value)
        self._update_state_cache(device_id, {"MinBrightness": value})
        await self.notify_settings_changed(device_id)

    async def set_max_brightness(self, device_id, value: int):
        """Set maximum brightness."""
        self._last_command_time[device_id] = time.time()
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)

        br_obj = self._get_brightness_object(device_id)
        br_obj["a_br"] = value

        body = {"cmd": [{"tm": -1, "br": br_obj}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        await self.client.set_device_setting_silent(device_id, {"MaxBrightness": value})
        self._update_brightness_cache(device_id, "a_br", value)
        self._update_state_cache(device_id, {"MaxBrightness": value})
        await self.notify_settings_changed(device_id)

    # AC Setters
    async def set_ac_fan_speed(self, device_id, fan_mode: str):
        """Set AC fan speed."""
        self._last_command_time[device_id] = time.time()
        fan_val = AC_FAN_MODES_REVERSE.get(fan_mode.lower())
        if fan_val is None:
            return

        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)
        body = {"cmd": [{"fn": fan_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        self._update_state_cache(device_id, {"FanSpeed": {"v": fan_val}, "fn": fan_val})
        await self.notify_settings_changed(device_id)

    async def set_ac_swing_mode(self, device_id, swing_mode: str):
        """Set AC swing mode."""
        self._last_command_time[device_id] = time.time()
        swing_val = AC_SWING_MODES_REVERSE.get(swing_mode.lower())
        if swing_val is None:
            return

        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)
        body = {"cmd": [{"ss": swing_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        self._update_state_cache(device_id, {"SwingState": {"v": swing_val}, "ss": swing_val})
        await self.notify_settings_changed(device_id)

    async def set_ac_horizontal_swing(self, device_id, position: int):
        """Set AC horizontal swing position."""
        self._last_command_time[device_id] = time.time()
        device = self.devices.get(device_id)
        payload_type = MysaDeviceLogic.get_payload_type(device, self.upgraded_lite_devices)
        body = {"cmd": [{"ssh": position, "tm": -1}], "type": payload_type, "ver": 1}
        await self.realtime.send_command(device_id, body, self.client.user_id)

        self._update_state_cache(
            device_id, {"SwingStateHorizontal": {"v": position}, "ssh": position}
        )
        self._last_command_time[device_id] = time.time() # why twice? preserved from original
        await self.notify_settings_changed(device_id)

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

    # Helpers
    def _update_state_cache(self, device_id, updates: dict):
        if device_id not in self.states:
            self.states[device_id] = {}
        self.states[device_id].update(updates)

    def _get_brightness_object(self, device_id):
        # Duplicated helper for brightness
        state = self.states.get(device_id, {})
        br = state.get("Brightness", {})
        if isinstance(br, dict):
            return {
                "a_b": br.get("a_b", 1),
                "a_br": br.get("a_br", 100),
                "i_br": br.get("i_br", 50),
                "a_dr": br.get("a_dr", 60),
                "i_dr": br.get("i_dr", 30),
            }
        return {"a_b": 1, "a_br": 100, "i_br": 50, "a_dr": 60, "i_dr": 30}

    def _update_brightness_cache(self, device_id, key, value):
        if device_id not in self.states:
            self.states[device_id] = {}
        if "Brightness" not in self.states[device_id]:
            self.states[device_id]["Brightness"] = self._get_brightness_object(device_id)
        if isinstance(self.states[device_id]["Brightness"], dict):
            self.states[device_id]["Brightness"][key] = value

    # MQTT Lifecycle
    async def start_mqtt_listener(self):
        """Start MQTT listener."""
        # Ensure we have device list
        self.realtime.set_devices(list(self.devices.keys()))
        await self.realtime.start()

    async def stop_mqtt_listener(self):
        """Stop MQTT listener."""
        await self.realtime.stop()
