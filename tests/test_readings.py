"""Tests for Mysa binary batch reading parsing."""
import struct
from custom_components.mysa.readings import parse_batch_readings

def test_parse_batch_readings_invalid():
    """Test parsing empty or invalid readings."""
    assert parse_batch_readings(b"") == []
    assert parse_batch_readings(b"too_short") == []
    # Wrong magic at start
    assert parse_batch_readings(b"\x00\x00\x00" + b"A"*23) == []
    # Magic mismatch inside loop
    reading0 = b'\xca\xa0\x00' + struct.pack('<LhhhbbhhhHbb', 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1) + b'\x01'
    assert len(parse_batch_readings(reading0 + b"\x00\x00\x00" + b"A"*23)) == 1
    # Version mismatch inside loop
    assert len(parse_batch_readings(reading0 + b"\xca\xa0\x03" + b"A"*30)) == 1

def test_parse_batch_v0():
    """Test parsing V0 readings."""
    # CA A0 00 (Ver 0)
    data = b'\xca\xa0\x00' + struct.pack('<LhhhbbhhhHbb', 1769542000, 236, 211, 210, 44, 0, 10, 10, 300, 5000, 29, 0) + b'\x01'
    parsed = parse_batch_readings(data)
    assert len(parsed) == 1
    r = parsed[0]
    assert r["ambTemp"] == 21.1
    assert r["unknown2"] == 1

def test_parse_batch_v1():
    """Test parsing V1 readings (Voltage)."""
    # CA A0 01 (Ver 1)
    data = b'\xca\xa0\x01' + struct.pack('<LhhhbbhhhHbb', 1769542001, 236, 211, 210, 44, 0, 10, 10, 300, 5000, 29, 0) + struct.pack('<hB', 240, 2)
    parsed = parse_batch_readings(data)
    assert len(parsed) == 1
    assert parsed[0]["Voltage"] == 240

def test_parse_batch_v3():
    """Test parsing V3 readings (Voltage + Current)."""
    # CA A0 03 (Ver 3)
    data = b'\xca\xa0\x03' + struct.pack('<LhhhbbhhhHbb', 1769542003, 236, 211, 210, 44, 50, 10, 10, 300, 5000, 29, 1) + struct.pack('<hh3sB', 244, 5090, b'\x00\x00\x00', 4)
    parsed = parse_batch_readings(data)
    assert len(parsed) == 1
    assert parsed[0]["Current"] == 5.09

def test_parse_batch_multiple_and_mismatch():
    """Test parsing multiple readings and handling mismatches."""
    # First valid Ver 0
    reading0 = b'\xca\xa0\x00' + struct.pack('<LhhhbbhhhHbb', 1769542000, 236, 211, 210, 44, 0, 10, 10, 300, 5000, 29, 0) + b'\x01'

    # Second reading with wrong magic
    data_bad_magic = reading0 + b'\x00\x00\x00' + b'A' * 23
    assert len(parse_batch_readings(data_bad_magic)) == 1

    # Second reading with wrong version
    data_bad_ver = reading0 + b'\xca\xa0\x03' + b'A' * 30
    assert len(parse_batch_readings(data_bad_ver)) == 1

def test_parse_batch_unsupported_version():
    """Test parsing valid magic but unknown version."""
    data = b'\xca\xa0\x05' + struct.pack('<LhhhbbhhhHbb', 1769542005, 236, 211, 210, 44, 0, 10, 10, 300, 5000, 29, 0)
    # len is 3 + 22 = 25. Still too short (min 26).
    data += b'EXTRA' # Total 30.
    parsed = parse_batch_readings(data)
    assert len(parsed) == 1
    assert parsed[0]["BatchVersion"] == 5

def test_parse_batch_truncated_second_packet():
    """Test when second packet in batch is truncated."""
    reading0 = b'\xca\xa0\x00' + struct.pack('<LhhhbbhhhHbb', 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1) + b'\x01'
    # Start of second packet but truncated
    data = reading0 + b'\xca\xa0\x00' + b'ABC' # Passes initial magic/ver check but fails unpack
    parsed = parse_batch_readings(data)
    assert len(parsed) == 1

def test_parse_batch_struct_error():
    """Force struct error by making data look longer than it is."""
    # Magic is CA A0 03 (Ver 3). Body wants 22 bytes.
    # Header is 3. 3 + 22 = 25. If len is exactly 25, it passes len < 26? No.
    # If len is 26, but we only have 1 byte after header.
    # wait, struct.unpack_from(fmt, data, offset) will raise if data[offset:] is too short for fmt.
    data = b'\xca\xa0\x00' + b'A' * 23 # Total 26. Offset 3. unpack_from wants 22. 23 avail. Success.
    data = b'\xca\xa0\x00' + (b'A' * 21) + b'X' + b'Y' # Total 26. Offset 3.
    # To fail, offset 3 + 22 = 25. 26 - 3 = 23 avail.
    # If I pass exactly 24 bytes, it fails the `len < 26` early.
    # Solution: use 26 bytes but start second packet early?
    # No, struct.unpack_from is called on the WHOLE readings buffer.
    # If len(readings) is 26, and offset is 3, then data[3:] is 23 bytes.
    # struct '<LhhhbbhhhHbb' is 22 bytes. It will SUCCEED.
    # To fail, we need data[3:] to be < 22 bytes. But then len(readings) would be < 25.
    # And len < 26 triggers at start.

    # WAIT! ver 0 needs 1 more byte at end. ver 1 needs 3. ver 3 needs 8.
    # If we have 26 bytes, Ver 3 header (3) + body (22) = 25. 1 byte left.
    # But Ver 3 wants 8 bytes at 129!
    data = b'\xca\xa0\x03' + struct.pack('<LhhhbbhhhHbb', 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1) + b'A'
    # This will fail at line 129: struct.unpack_from('<hh3sB', readings, offset).
    # But there is no try/except there! I should add it.
    assert parse_batch_readings(data) == [] # Should fail gracefully or I fix code
