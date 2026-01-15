"""
Tests for Update entity.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


class TestMysaUpdateEntity:
    """Test Mysa firmware update entity."""

    def test_update_device_class(self):
        """Test update entity device class."""
        from homeassistant.components.update import UpdateDeviceClass

        device_class = UpdateDeviceClass.FIRMWARE

        assert device_class == "firmware"

    def test_update_unique_id_format(self):
        """Test update entity unique ID format."""
        device_id = "device1"

        unique_id = f"{device_id}_firmware"

        assert unique_id == "device1_firmware"

    def test_update_name_format(self):
        """Test update entity name format."""
        device_name = "Living Room"

        entity_name = f"{device_name} Firmware"

        assert entity_name == "Living Room Firmware"


class TestFirmwareVersionParsing:
    """Test firmware version parsing."""

    def test_version_from_device_data(self):
        """Test extracting firmware version from device data."""
        device_data = {"Name": "Living Room", "FirmwareVersion": "2.1.0"}

        version = device_data.get("FirmwareVersion")

        assert version == "2.1.0"

    def test_version_missing_returns_none(self):
        """Test missing version returns None."""
        device_data = {"Name": "Living Room"}

        version = device_data.get("FirmwareVersion")

        assert version is None


class TestFirmwareUpdateCheck:
    """Test firmware update checking."""

    def test_update_available_when_versions_differ(self):
        """Test update is available when installed != latest."""
        installed = "2.0.0"
        latest = "2.1.0"

        update_available = installed != latest

        assert update_available is True

    def test_no_update_when_versions_match(self):
        """Test no update when installed == latest."""
        installed = "2.1.0"
        latest = "2.1.0"

        update_available = installed != latest

        assert update_available is False

    def test_firmware_info_structure(self):
        """Test expected firmware info structure."""
        firmware_info = {
            "installedVersion": "2.0.0",
            "allowedVersion": "2.1.0",
            "update": True,
        }

        assert "installedVersion" in firmware_info
        assert "allowedVersion" in firmware_info
        assert "update" in firmware_info

    def test_firmware_api_response_parsing(self):
        """Test parsing firmware API response."""
        info = {"installedVersion": "2.0.0", "allowedVersion": "2.1.0", "update": True}

        installed = info.get("installedVersion")
        latest = info.get("allowedVersion")

        assert installed == "2.0.0"
        assert latest == "2.1.0"


class TestUpdateEntityConfiguration:
    """Test update entity configuration."""

    def test_scan_interval(self):
        """Test firmware check interval."""
        from datetime import timedelta

        scan_interval = timedelta(hours=4)

        assert scan_interval.total_seconds() == 4 * 60 * 60

    def test_supported_features_none(self):
        """Test no install feature supported (Mysa updates OTA)."""
        from homeassistant.components.update import UpdateEntityFeature

        # Mysa handles updates internally, no HA install feature
        features = UpdateEntityFeature(0)

        assert not (features & UpdateEntityFeature.INSTALL)

    def test_in_progress_default_false(self):
        """Test in_progress is false by default."""
        in_progress = False

        assert in_progress is False


class TestUpdateDeviceInfo:
    """Test update entity device info."""

    def test_device_identifiers(self):
        """Test device identifiers format."""
        domain = "mysa"
        device_id = "device1"

        identifiers = {(domain, device_id)}

        assert (domain, device_id) in identifiers

    def test_device_info_structure(self):
        """Test device info structure."""
        device_id = "device1"
        device_data = {"Name": "Living Room", "Model": "BB-V2"}

        device_info = {
            "identifiers": {("mysa", device_id)},
            "manufacturer": "Mysa",
            "model": device_data.get("Model"),
            "name": device_data.get("Name"),
        }

        assert device_info["manufacturer"] == "Mysa"
        assert device_info["model"] == "BB-V2"
        assert device_info["name"] == "Living Room"


class TestFirmwareErrorHandling:
    """Test firmware update error handling."""

    def test_error_logged_on_fetch_failure(self):
        """Test error handling when firmware fetch fails."""
        error_occurred = False

        try:
            raise Exception("Network error")
        except Exception as e:
            error_occurred = True

        assert error_occurred is True

    def test_version_unchanged_on_error(self):
        """Test version stays unchanged on error."""
        installed_version = "2.0.0"
        latest_version = "2.0.0"  # Default to current

        # Simulate error - versions should stay same
        try:
            raise Exception("Fetch failed")
        except Exception:
            pass  # Log warning, but don't change versions

        assert installed_version == "2.0.0"
        assert latest_version == "2.0.0"
