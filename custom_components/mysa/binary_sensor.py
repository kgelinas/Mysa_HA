"""Binary sensor platform for Mysa."""
import logging
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa binary sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    devices = await api.get_devices()

    entities = []
    for device_id, device_data in devices.items():
        # Lock
        entities.append(MysaBinaryDiagnosticSensor(coordinator, device_id, device_data, "Lock", "Lock", BinarySensorDeviceClass.LOCK, entry))
        # Proximity
        entities.append(MysaBinaryDiagnosticSensor(coordinator, device_id, device_data, "Proximity", "Proximity", BinarySensorDeviceClass.MOTION, entry))
        # AutoBrightness
        entities.append(MysaBinaryDiagnosticSensor(coordinator, device_id, device_data, "AutoBrightness", "Auto Brightness", None, entry))
        # EcoMode
        entities.append(MysaBinaryDiagnosticSensor(coordinator, device_id, device_data, "EcoMode", "Eco Mode", None, entry))

    async_add_entities(entities)

class MysaBinaryDiagnosticSensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Mysa Binary Diagnostic Sensor."""

    def __init__(self, coordinator, device_id, device_data, sensor_key, name_suffix, device_class, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._sensor_key = sensor_key
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} {name_suffix}"
        self._attr_unique_id = f"{device_id}_{sensor_key.lower()}"
        self._attr_device_class = device_class

    @property
    def device_info(self):
        """Return device info."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        zone_name = self._entry.options.get(f"zone_name_{zone_id}") if zone_id else None
        
        info = {
            "identifiers": {(DOMAIN, self._device_id)},
            "manufacturer": "Mysa",
            "model": self._device_data.get("Model"),
        }
        if zone_name:
            info["suggested_area"] = zone_name
        return info

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        zone_name = self._entry.options.get(f"zone_name_{zone_id}") if zone_id else None
        
        return {
            "device_id": self._device_id,
            "zone_id": zone_id,
            "zone_name": zone_name if zone_name else "Unassigned",
        }

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None
            
        keys = [self._sensor_key]
        if self._sensor_key == "Lock":
            keys = ["Lock", "ButtonState", "alk", "lk", "lc"]
        elif self._sensor_key == "Proximity":
            keys = ["ProximityMode", "px", "Prox", "Proximity"]
        elif self._sensor_key == "AutoBrightness":
            keys = ["AutoBrightness", "ab"]
        elif self._sensor_key == "EcoMode":
            keys = ["EcoMode", "ecoMode", "eco"]

        val = self._extract_value(state, keys)
        
        # For Lock: Mysa uses 0=unlocked, 1=locked
        # HA's LOCK device class uses is_on=True for "unsafe/unlocked"
        # So we need to invert: Lock=0 should return True (unlocked/unsafe)
        if self._sensor_key == "Lock":
            return not bool(val) if val is not None else True
        
        return bool(val) if val is not None else False

    def _extract_value(self, state, keys):
        """Helper to extract a value from state dictionary."""
        for key in keys:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    v = val.get('v')
                    if v is None:
                        v = val.get('Id')
                    return v
                return val
        return None
