"""Device capability caching for Mysa integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate.const import HVACMode

if TYPE_CHECKING:
    from .mysa_api import MysaApi


@dataclass
class DeviceCapabilities:
    """Cached device capabilities (static and dynamic).

    This class caches device properties to avoid repeated calculations:
    - Static properties (hardware): Never change after initialization
    - Semi-static properties (upgrades): Check live from API options
    - Dynamic properties (config): Refresh when configuration changes
    """

    # Static - hardware properties (never change)
    device_id: str
    hardware_model: str
    is_ac: bool
    is_stv10: bool
    supports_humidity_hardware: bool
    supports_floor_sensor_hardware: bool

    # Semi-static - check live from API options
    _api: MysaApi  # Reference for live upgrade checks

    # Dynamic - refresh when config changes
    hvac_config_index: int | str
    hvac_modes: list[HVACMode]
    max_temp: float
    min_temp: float
    target_temperature_step: float
    has_aux_heat: bool
    has_stage_2_heat: bool
    has_stage_2_cool: bool

    @property
    def is_lite(self) -> bool:
        """Check if device is Lite (checks upgrade status live).

        Returns False if device is in upgraded_lite_devices option.
        """
        safe_id = self.device_id.replace(":", "").lower()
        if safe_id in self._api.upgraded_lite_devices:
            return False  # Upgraded to Full
        return bool(self.hardware_model == "BB-V2-0-L")

    def needs_refresh(self, new_state: dict[str, Any]) -> bool:
        """Check if dynamic capabilities need refresh.

        Returns True if HVAC configuration has changed.
        """
        new_config = new_state.get("hvac_config_index", 0)
        return bool(self.hvac_config_index != new_config)

    @classmethod
    def from_device(
        cls,
        device_id: str,
        device_data: dict[str, Any],
        state: dict[str, Any],
        api: MysaApi,
    ) -> DeviceCapabilities:
        """Create capabilities from device data and state."""
        hardware_model = device_data.get("Model", "")

        # Static calculations
        is_ac = "AC" in hardware_model
        is_stv10 = "ST-V1-0" in hardware_model

        # Dynamic from state
        hvac_modes = cls._determine_hvac_modes(state, is_stv10, is_ac)
        max_temp = cls._get_max_temp(state)
        min_temp = cls._get_min_temp(state)

        return cls(
            device_id=device_id,
            hardware_model=hardware_model,
            is_ac=is_ac,
            is_stv10=is_stv10,
            supports_humidity_hardware=is_ac or is_stv10,
            supports_floor_sensor_hardware=not is_ac and not is_stv10,
            _api=api,
            hvac_config_index=state.get("hvac_config_index", 0),
            hvac_modes=hvac_modes,
            max_temp=max_temp,
            min_temp=min_temp,
            target_temperature_step=0.5,  # Default for legacy devices
            has_aux_heat=state.get("aux_heat", False),
            has_stage_2_heat=state.get("stage_2_heat", False),
            has_stage_2_cool=state.get("stage_2_cool", False),
        )

    @classmethod
    def _get_stv10_temp_step(cls, heat_setpoints: list[float]) -> float:
        """Extract temperature step, defaulting to 0.5."""
        if len(heat_setpoints) >= 2:
            return heat_setpoints[1] - heat_setpoints[0]
        return 0.5

    @classmethod
    def from_stv10_capabilities(
        cls,
        device_id: str,
        caps: dict[str, Any],
        api: MysaApi,
    ) -> DeviceCapabilities:
        """Create ST-V1-0 capabilities from HTTP /capabilities endpoint."""
        climate_ctrl = caps.get("features", {}).get("climateControl", {})
        system_info = caps.get("system", {})

        # Dynamic from state/config
        hvac_config_index = str(system_info.get("configCode", "0"))
        config_info = cls._decode_stv10_config(hvac_config_index)

        # We need to pass a mock state for _determine_hvac_modes
        hvac_modes = cls._determine_hvac_modes(
            {"hvac_config_index": hvac_config_index}, is_stv10=True, is_ac=False
        )

        # Extract temperature ranges
        heat_setpoints = (
            climate_ctrl.get("heat", {}).get("setpoint", {}).get("validValues", [])
        )
        cool_setpoints = (
            climate_ctrl.get("cool", {}).get("setpoint", {}).get("validValues", [])
        )

        return cls(
            device_id=device_id,
            hardware_model=system_info.get("model", "ST-V1-0"),
            is_ac=False,
            is_stv10=True,
            supports_humidity_hardware=True,
            supports_floor_sensor_hardware=False,
            _api=api,
            hvac_config_index=hvac_config_index,
            hvac_modes=hvac_modes,
            max_temp=max(cool_setpoints) if cool_setpoints else 37.0,
            min_temp=min(heat_setpoints) if heat_setpoints else 5.0,
            target_temperature_step=cls._get_stv10_temp_step(heat_setpoints),
            has_aux_heat=config_info.get("has_aux", False),
            has_stage_2_heat=config_info.get("stage_2_heat", False),
            has_stage_2_cool=config_info.get("stage_2_cool", False),
        )

    @staticmethod
    def _decode_stv10_config(config_code: str) -> dict[str, Any]:
        """Decode ST-V1-0 3-digit config code (0-9, 0-9, A-P)."""
        if not isinstance(config_code, str) or len(config_code) < 3:
            return {}

        d1, d2, d3 = config_code[0], config_code[1], config_code[2]

        # Digit 1: Heating Type (0-9)
        has_heat = d1 in ("1", "2", "3", "4", "6", "7", "8", "9")
        is_hp_d1 = d1 in ("3", "8")
        stage_2_heat = d1 in ("6", "7", "8", "9")

        # Digit 2: Cooling Type (0-9)
        has_cool = d2 in ("1", "4", "5", "6")
        stage_2_cool = d2 == "6"

        # Digit 3: Options (A-P)
        is_hp_d3 = d3 in ("I", "J", "K", "L", "M", "N", "O", "P")
        has_aux = d3 in ("C", "D", "K", "L", "O", "P")

        return {
            "has_heat": has_heat,
            "has_cool": has_cool,
            "stage_2_heat": stage_2_heat,
            "stage_2_cool": stage_2_cool,
            "is_hp": is_hp_d1 or is_hp_d3,
            "has_aux": has_aux,
        }

    @staticmethod
    def _determine_hvac_modes(
        state: dict[str, Any], is_stv10: bool, is_ac: bool
    ) -> list[HVACMode]:
        """Determine available HVAC modes based on device type and config."""
        if is_ac:
            # AC devices support all modes
            return [
                HVACMode.OFF,
                HVACMode.COOL,
                HVACMode.HEAT,
                HVACMode.DRY,
                HVACMode.FAN_ONLY,
                HVACMode.AUTO,
            ]
        if is_stv10:
            # ST-V1-0 modes - simplified logic based on config
            modes = [HVACMode.OFF]

            # Heat pump configs support heat/cool/auto
            config_index = state.get("hvac_config_index", 0)

            is_hp = False
            has_cooling = False
            if isinstance(config_index, int):
                # Existing numeric index checks (legacy fallback)
                is_hp = config_index in [3, 4, 5, 6, 7, 8, 9, 15]
            elif isinstance(config_index, str) and len(config_index) >= 3:
                # Positional decoding
                config_info = DeviceCapabilities._decode_stv10_config(config_index)
                is_hp = config_info.get("is_hp", False)
                has_cooling = config_info.get("has_cool", False)

            if is_hp:
                modes.extend([HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO])
            elif has_cooling:
                # If cooling is available but not a heat pump, it's a dual system
                modes.extend([HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO])
            else:  # Heat only
                modes.append(HVACMode.HEAT)

            return modes

        # Baseboard thermostats
        return [HVACMode.OFF, HVACMode.HEAT]

    @staticmethod
    def _get_max_temp(state: dict[str, Any]) -> float:
        """Get maximum temperature from state."""
        # Check various key formats
        max_val = state.get("MaxSetpoint") or state.get("mxs")
        if max_val is not None:
            # Handle {v: value, t: timestamp} format
            if isinstance(max_val, dict):
                max_val = max_val.get("v")
            if max_val is not None:
                return float(max_val) / 100.0
        return 30.0  # Default

    @staticmethod
    def _get_min_temp(state: dict[str, Any]) -> float:
        """Get minimum temperature from state."""
        # Check various key formats
        min_val = state.get("MinSetpoint") or state.get("mns")
        if min_val is not None:
            # Handle {v: value, t: timestamp} format
            if isinstance(min_val, dict):
                min_val = min_val.get("v")
            if min_val is not None:
                return float(min_val) / 100.0
        return 5.0  # Default

    def refresh_dynamic(self, state: dict[str, Any]) -> None:
        """Refresh dynamic capabilities from new state."""
        self.hvac_config_index = state.get("hvac_config_index", 0)
        self.hvac_modes = self._determine_hvac_modes(state, self.is_stv10, self.is_ac)
        self.max_temp = self._get_max_temp(state)
        self.min_temp = self._get_min_temp(state)

        if self.is_stv10 and isinstance(self.hvac_config_index, str):
            config_info = self._decode_stv10_config(self.hvac_config_index)
            self.has_aux_heat = config_info.get("has_aux", False)
            self.has_stage_2_heat = config_info.get("stage_2_heat", False)
            self.has_stage_2_cool = config_info.get("stage_2_cool", False)
        else:
            self.has_aux_heat = state.get("heating_stage_two_exists") == 1
            self.has_stage_2_heat = state.get("heating_stage_two_exists") == 1
            self.has_stage_2_cool = state.get("cooling_stage_two_exists") == 1
