"""Utility for parsing Mysa binary batch readings."""

import struct
from dataclasses import dataclass
from typing import Any


@dataclass
class MysaReading:
    # pylint: disable=too-many-instance-attributes
    """Binary structure representing one raw reading from a Mysa thermostat."""

    ts: int  # Unix time (seconds)
    sensor_t: float  # Unit = °C
    ambient_t: float  # Unit = °C
    setpoint_t: float  # Unit = °C
    humidity: int  # Percent
    duty: int  # Percent
    on_ms: int  # Unit = 1 ms
    off_ms: int  # Unit = 1 ms
    heatsink_t: float  # Unit = °C
    free_heap: int  # Free heap
    rssi: int  # Unit = 1 dBm
    onoroff: int  # Probably boolean
    ver: int  # Version byte
    unknown2: int = 0  # Common trailer byte in all versions (V0/V1/V3)
    rest: bytes | None = None  # Trailing bytes

    def to_dict(self) -> dict[str, Any]:
        """Convert reading to a dictionary compatible with integration state mapping."""
        return {
            "SensorTemp": self.sensor_t,
            "ambTemp": self.ambient_t,
            "stpt": self.setpoint_t,
            "hum": self.humidity,
            "DutyCycle": self.duty,
            "HeatSink": self.heatsink_t,
            "rssi": self.rssi,
            "Timestamp": self.ts,
            "BatchVersion": self.ver,
        }


@dataclass
class MysaReadingV0(MysaReading):
    """Version 0 reading."""

    unknown2: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert reading to a dictionary compatible with integration state mapping."""
        d = super().to_dict()
        d["unknown2"] = self.unknown2
        return d


@dataclass
class MysaReadingV1(MysaReading):
    """Version 1 reading (adds Voltage)."""

    voltage: int = 0
    unknown2: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert reading to a dictionary compatible with integration state mapping."""
        d = super().to_dict()
        d["Voltage"] = self.voltage
        d["unknown2"] = self.unknown2
        return d


@dataclass
class MysaReadingV3(MysaReading):
    """Version 3 reading (adds Voltage and Current)."""

    voltage: int = 0
    current: int = 0
    always0: bytes = b""
    unknown2: int = 0
    valid: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert reading to a dictionary compatible with integration state mapping."""
        d = super().to_dict()
        d["Voltage"] = self.voltage
        d["Current"] = self.current / 1000.0  # Convert mA to A
        d["unknown2"] = self.unknown2
        d["Valid"] = self.valid
        return d


def _unpack_vspec(
    ver: int, data: bytes, offset: int, kwargs: dict[str, Any]
) -> MysaReading | None:
    """Helper to unpack version-specific fields."""
    try:
        if ver == 0:
            (unknown2,) = struct.unpack_from("<B", data, offset)
            return MysaReadingV0(**kwargs, unknown2=unknown2)
        if ver == 1:
            voltage, unknown2 = struct.unpack_from("<hB", data, offset)
            return MysaReadingV1(**kwargs, voltage=voltage, unknown2=unknown2)
        if ver == 3:
            voltage, current, always0, unknown2 = struct.unpack_from(
                "<hh3sB", data, offset
            )
            return MysaReadingV3(
                **kwargs,
                voltage=voltage,
                current=current,
                always0=always0,
                unknown2=unknown2,
            )
        return MysaReading(**kwargs)
    except struct.error:
        return None


def parse_batch_readings(readings: bytes) -> list[dict[str, Any]]:
    """Parse binary readings into a list of dictionaries."""
    if len(readings) < 26 or readings[0:2] != b"\xca\xa0":
        return []

    ver = readings[2]
    output = []
    offset = 0

    while offset < len(readings):
        if readings[offset : offset + 2] != b"\xca\xa0" or readings[offset + 2] != ver:
            break

        start_pos = offset
        offset += 3
        try:
            # <LhhhbbhhhHbb = 22 bytes
            unpacked = struct.unpack_from("<LhhhbbhhhHbb", readings, offset)
        except struct.error:
            break

        offset += 22
        kwargs = {
            "ts": unpacked[0],
            "sensor_t": unpacked[1] / 10.0,
            "ambient_t": unpacked[2] / 10.0,
            "setpoint_t": unpacked[3] / 10.0,
            "humidity": unpacked[4],
            "duty": unpacked[5],
            "on_ms": unpacked[6] * 100,
            "off_ms": unpacked[7] * 100,
            "heatsink_t": unpacked[8] / 10.0,
            "free_heap": unpacked[9] * 10,
            "rssi": -unpacked[10],
            "onoroff": unpacked[11],
            "ver": ver,
        }

        next_pos = readings.find(b"\xca\xa0" + bytes([ver]), offset)
        if next_pos < 0:
            next_pos = len(readings)
        kwargs["rest"] = readings[offset:next_pos]

        reading = _unpack_vspec(ver, readings, offset, kwargs)
        if not reading:
            break

        # Checksum Validation (V3)
        # ------------------------
        # MsgType 3 payloads for V3 devices end with an 8-byte trailer.
        # The last byte of this trailer is an XOR checksum of the preceding 32 bytes
        # (which includes the 3-byte header, 22-byte body, and first 7 bytes of the trailer).
        # This was reverse-engineered from device traffic analysis.
        if ver == 3 and isinstance(reading, MysaReadingV3):
            # Calculate XOR sum of bytes 0-31 relative to start_pos
            data_slice = readings[start_pos : start_pos + 32]
            calc_sum = 0
            for b in data_slice:
                calc_sum ^= b

            if calc_sum == reading.unknown2:
                # pylint: disable=attribute-defined-outside-init
                reading.valid = True

        output.append(reading.to_dict())

        # Update offset based on version
        v_offsets = {0: 1, 1: 3, 3: 8}
        offset += v_offsets.get(ver, next_pos - offset)

    return output
