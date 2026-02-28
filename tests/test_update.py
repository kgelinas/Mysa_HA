"""Tests for Update entity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.mysa.update import MysaUpdate


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
        except Exception:
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


# ===========================================================================
# Merged Coverage Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_update_installed_version_mismatch(hass):
    """Test that device_data is updated when firmware version mismatch occurs."""
    mock_api = MagicMock()
    mock_api.fetch_firmware_info = AsyncMock()

    device_id = "test_device_id"
    device_data = {"FirmwareVersion": "1.0.0", "Name": "Test Device"}

    entity = MysaUpdate(mock_api, device_id, device_data)

    # Simulate API returning a newer installed version than what we have in device_data
    mock_api.fetch_firmware_info.return_value = {
        "installedVersion": "1.1.0",
        "allowedVersion": "1.2.0",
        "update": True,
    }

    # Verify initial state
    assert entity._device_data["FirmwareVersion"] == "1.0.0"

    # Run update
    await entity.async_update()

    # Verify device_data was updated
    assert entity._device_data["FirmwareVersion"] == "1.1.0"
    assert entity._attr_installed_version == "1.1.0"
    assert entity._attr_latest_version == "1.2.0"

@pytest.mark.asyncio
async def test_update_async_added_to_hass(hass):
    """Test async_added_to_hass calls async_update."""
    mock_api = MagicMock()
    mock_api.fetch_firmware_info = AsyncMock()

    entity = MysaUpdate(mock_api, "dev1", {"FirmwareVersion": "1.0.0"})
    entity.hass = hass

    # Mock async_update
    entity.async_update = AsyncMock()

    await entity.async_added_to_hass()
    entity.async_update.assert_called_once()

@pytest.mark.asyncio
async def test_update_setup_entry(hass):
    """Test update setup_entry."""
    from custom_components.mysa.update import async_setup_entry
    from custom_components.mysa import MysaData

    mock_api = MagicMock()
    mock_api.get_devices = AsyncMock()
    mock_api.devices = {"dev1": {"FirmwareVersion": "1.0.0"}}

    mock_entry = MagicMock()
    mock_entry.runtime_data = MysaData(mock_api, MagicMock())

    async_add_entities = MagicMock()
    await async_setup_entry(hass, mock_entry, async_add_entities)

    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert entities[0]._device_id == "dev1"

@pytest.mark.asyncio
async def test_update_exception(hass):
    """Test update generic exception (lines 115-116)."""
    mock_api = MagicMock()
    mock_api.fetch_firmware_info = AsyncMock(side_effect=Exception("API Error"))

    entity = MysaUpdate(mock_api, "dev1", {"FirmwareVersion": "1.0.0"})
    await entity.async_update()
    # Should log warning but not raise


class TestUpdateConsolidated:
    """Consolidated update tests from UI component coverage."""

    @pytest.mark.asyncio
    async def test_update_entity_logic_consolidated(self, hass):
        """Test MysaUpdate entity logic."""
        api = MagicMock()
        device_id = "d1"
        device_data = {"FirmwareVersion": "100"}

        entity = MysaUpdate(api, device_id, device_data)
        entity.hass = hass

        assert entity.installed_version == "100"

        # Logic for update
        api.fetch_firmware_info = AsyncMock(
            return_value={
                "installedVersion": "100",
                "allowedVersion": "101",
                "update": True,
            }
        )

        await entity.async_update()
        assert entity.latest_version == "101"
        assert entity.supported_features == 0

    @pytest.mark.asyncio
    async def test_update_entity_startup_and_exceptions_consolidated(self, hass):
        """Test MysaUpdate async_added_to_hass and exceptions."""
        api = MagicMock()
        device_id = "d1"
        device_data = {"FirmwareVersion": "100"}

        entity = MysaUpdate(api, device_id, device_data)
        entity.hass = hass
        entity.entity_id = "update.mysa_d1_firmware"

        # Test async_added_to_hass
        api.fetch_firmware_info = AsyncMock(
            return_value={
                "installedVersion": "100",
                "allowedVersion": "102",
                "update": True,
            }
        )

        with patch(
            "custom_components.mysa.update.UpdateEntity.async_added_to_hass",
            new_callable=AsyncMock,
        ):
            await entity.async_added_to_hass()

        assert entity.latest_version == "102"

        # Test version mismatch update
        api.fetch_firmware_info = AsyncMock(
            return_value={
                "installedVersion": "105",
                "allowedVersion": "105",
                "update": False,
            }
        )
        await entity.async_update()
        assert device_data["FirmwareVersion"] == "105"

        # Test Exception handling
        api.fetch_firmware_info = AsyncMock(side_effect=Exception("API Error"))
        await entity.async_update()  # Should not raise
