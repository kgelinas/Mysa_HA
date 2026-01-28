"""Tests for the Mysa Extended integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.mysa.const import DOMAIN as MYSA_DOMAIN
from custom_components.mysa_extended import (
    async_service_downgrade_lite,
    async_service_killer_ping,
    async_service_upgrade_lite,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)


@pytest.mark.asyncio
async def test_async_setup(hass: HomeAssistant):
    """Test async_setup registers services."""
    result = await async_setup(hass, {})

    assert result is True
    # Verify services are registered
    assert hass.services.has_service("mysa_extended", "upgrade_lite_device")
    assert hass.services.has_service("mysa_extended", "downgrade_lite_device")
    assert hass.services.has_service("mysa_extended", "killer_ping")

    # Call again - should not error (guard prevents duplicate registration)
    result2 = await async_setup(hass, {})
    assert result2 is True


@pytest.mark.asyncio
async def test_async_setup_entry(hass: HomeAssistant):
    """Test async_setup_entry registers services."""
    mock_entry = MagicMock()
    result = await async_setup_entry(hass, mock_entry)

    assert result is True
    assert hass.services.has_service("mysa_extended", "upgrade_lite_device")

    # Call again - should not error
    result2 = await async_setup_entry(hass, mock_entry)
    assert result2 is True


@pytest.mark.asyncio
async def test_async_unload_entry(hass: HomeAssistant):
    """Test async_unload_entry."""
    mock_entry = MagicMock()
    result = await async_unload_entry(hass, mock_entry)
    assert result is True


@pytest.mark.asyncio
async def test_upgrade_lite_device_success(hass: HomeAssistant):
    """Test successful upgrade of lite device and option sync."""
    # Mock API
    mock_api = MagicMock()
    mock_api.async_upgrade_lite_device = AsyncMock(return_value=True)

    # Mock Config Entry
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.options = {}

    # Setup hass data
    hass.data[MYSA_DOMAIN] = {"test_entry": {"api": mock_api}}

    # Mock device registry
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
        patch.object(hass.config_entries, "async_update_entry") as mock_update,
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        await async_service_upgrade_lite(call, hass)

        # Verify API method was called
        mock_api.async_upgrade_lite_device.assert_called_once_with("device_123")

        # Verify options were updated
        mock_update.assert_called_once()
        args, kwargs = mock_update.call_args
        assert kwargs["options"]["upgraded_lite_devices"] == ["device_123"]


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_downgrade_lite_device_success(hass: HomeAssistant):
    """Test successful downgrade of device and option sync."""
    # Mock API
    mock_api = MagicMock()
    mock_api.async_downgrade_lite_device = AsyncMock(return_value=True)

    # Mock Config Entry
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"
    mock_entry.options = {"upgraded_lite_devices": ["device_123"]}

    # Setup hass data
    hass.data[MYSA_DOMAIN] = {"test_entry": {"api": mock_api}}

    # Mock device registry
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
        patch.object(hass.config_entries, "async_update_entry") as mock_update,
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        await async_service_downgrade_lite(call, hass)

        # Verify API method was called
        mock_api.async_downgrade_lite_device.assert_called_once_with("device_123")

        # Verify options were updated (removed)
        mock_update.assert_called_once()
        args, kwargs = mock_update.call_args
        assert kwargs["options"]["upgraded_lite_devices"] == []


@pytest.mark.asyncio
async def test_upgrade_lite_device_no_device(hass: HomeAssistant):
    """Test upgrade when device not found."""
    mock_device_registry = MagicMock()
    mock_device_registry.async_get.return_value = None

    with patch(
        "homeassistant.helpers.device_registry.async_get",
        return_value=mock_device_registry,
    ):
        call = MagicMock()
        call.data = {"device_id": "invalid_device"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_upgrade_lite(call, hass)
        assert excinfo.value.translation_key == "device_not_found"


@pytest.mark.asyncio
async def test_upgrade_lite_device_no_mysa_integration(hass: HomeAssistant):
    """Test upgrade when base mysa integration not found."""
    # Mock device registry
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    # hass.data[MYSA_DOMAIN] is empty
    hass.data[MYSA_DOMAIN] = {}

    with patch(
        "homeassistant.helpers.device_registry.async_get",
        return_value=mock_device_registry,
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_upgrade_lite(call, hass)
        assert excinfo.value.translation_key == "mysa_integration_not_found_for_device"


@pytest.mark.asyncio
async def test_upgrade_lite_device_api_failure(hass: HomeAssistant):
    """Test upgrade when API returns failure."""
    mock_api = MagicMock()
    mock_api.async_upgrade_lite_device = AsyncMock(return_value=False)

    # Mock Config Entry
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"

    hass.data[MYSA_DOMAIN] = {"test_entry": {"api": mock_api}}

    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_upgrade_lite(call, hass)
        assert excinfo.value.translation_key == "upgrade_failed"


@pytest.mark.asyncio
async def test_service_downgrade_no_device(hass: HomeAssistant):
    """Test downgrade when device not found."""
    mock_device_registry = MagicMock()
    mock_device_registry.async_get.return_value = None

    with patch(
        "homeassistant.helpers.device_registry.async_get",
        return_value=mock_device_registry,
    ):
        call = MagicMock()
        call.data = {"device_id": "invalid_device"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_downgrade_lite(call, hass)
        assert excinfo.value.translation_key == "device_not_found"


@pytest.mark.asyncio
async def test_service_downgrade_no_mysa_integration(hass: HomeAssistant):
    """Test downgrade when base mysa integration not found."""
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    hass.data[MYSA_DOMAIN] = {}

    with patch(
        "homeassistant.helpers.device_registry.async_get",
        return_value=mock_device_registry,
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_downgrade_lite(call, hass)
        assert excinfo.value.translation_key == "mysa_integration_not_found_for_device"


@pytest.mark.asyncio
async def test_service_upgrade_integration_not_loaded(hass: HomeAssistant):
    """Test upgrade when Mysa integration is not loaded."""
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    # Identifiers match but no config entry loaded yet
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    # Ensure MYSA_DOMAIN is missing from hass.data
    if MYSA_DOMAIN in hass.data:
        hass.data.pop(MYSA_DOMAIN)

    with patch(
        "homeassistant.helpers.device_registry.async_get",
        return_value=mock_device_registry,
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_upgrade_lite(call, hass)
        assert excinfo.value.translation_key == "mysa_integration_not_loaded"


@pytest.mark.asyncio
async def test_service_upgrade_api_not_initialized(hass: HomeAssistant):
    """Test upgrade when API is not in hass.data."""
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    # Entry exists but API is missing
    hass.data[MYSA_DOMAIN] = {"test_entry": {"loaded": True}}
    mock_entry = MagicMock(entry_id="test_entry")

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_upgrade_lite(call, hass)
        assert excinfo.value.translation_key == "mysa_api_not_initialized"


@pytest.mark.asyncio
async def test_service_downgrade_api_not_initialized(hass: HomeAssistant):
    """Test downgrade when API is not in hass.data."""
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    hass.data[MYSA_DOMAIN] = {"test_entry": {"loaded": True}}
    mock_entry = MagicMock(entry_id="test_entry")

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_downgrade_lite(call, hass)
        assert excinfo.value.translation_key == "mysa_api_not_initialized"


@pytest.mark.asyncio
async def test_downgrade_api_failure(hass: HomeAssistant):
    """Test downgrade when API returns failure."""
    mock_api = MagicMock()
    mock_api.async_downgrade_lite_device = AsyncMock(return_value=False)

    hass.data[MYSA_DOMAIN] = {"test_entry": {"api": mock_api}}
    mock_entry = MagicMock(entry_id="test_entry")

    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_downgrade_lite(call, hass)
        assert excinfo.value.translation_key == "downgrade_failed"


@pytest.mark.asyncio
async def test_upgrade_generic_exception(hass: HomeAssistant):
    """Test upgrade handles generic exceptions."""
    with patch(
        "homeassistant.helpers.device_registry.async_get",
        side_effect=ValueError("Boom"),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_upgrade_lite(call, hass)
        assert excinfo.value.translation_key == "upgrade_error"


@pytest.mark.asyncio
async def test_downgrade_generic_exception(hass: HomeAssistant):
    """Test downgrade handles generic exceptions."""
    with patch(
        "homeassistant.helpers.device_registry.async_get",
        side_effect=ValueError("Boom"),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_downgrade_lite(call, hass)
        assert excinfo.value.translation_key == "downgrade_error"


@pytest.mark.asyncio
async def test_killer_ping_success(hass: HomeAssistant):
    """Test successful killer ping."""
    mock_api = MagicMock()
    mock_api.async_send_killer_ping = AsyncMock(return_value=True)

    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry"

    hass.data[MYSA_DOMAIN] = {"test_entry": {"api": mock_api}}

    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        await async_service_killer_ping(call, hass)
        mock_api.async_send_killer_ping.assert_called_once_with("device_123")


@pytest.mark.asyncio
async def test_killer_ping_device_not_found(hass: HomeAssistant):
    """Test killer ping with device not found."""
    mock_device_registry = MagicMock()
    mock_device_registry.async_get.return_value = None

    with patch(
        "homeassistant.helpers.device_registry.async_get",
        return_value=mock_device_registry,
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_killer_ping(call, hass)
        assert excinfo.value.translation_key == "device_not_found"


@pytest.mark.asyncio
async def test_killer_ping_mysa_not_found(hass: HomeAssistant):
    """Test killer ping when mysa integration not found."""
    hass.data[MYSA_DOMAIN] = {}

    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"other_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    with patch(
        "homeassistant.helpers.device_registry.async_get",
        return_value=mock_device_registry,
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_killer_ping(call, hass)
        assert excinfo.value.translation_key == "mysa_integration_not_found_for_device"


@pytest.mark.asyncio
async def test_killer_ping_api_not_initialized(hass: HomeAssistant):
    """Test killer ping when API not initialized."""
    hass.data[MYSA_DOMAIN] = {"test_entry": {"loaded": True}}
    mock_entry = MagicMock(entry_id="test_entry")

    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_killer_ping(call, hass)
        assert excinfo.value.translation_key == "mysa_api_not_initialized"


@pytest.mark.asyncio
async def test_killer_ping_api_failure(hass: HomeAssistant):
    """Test killer ping when API returns failure."""
    mock_api = MagicMock()
    mock_api.async_send_killer_ping = AsyncMock(return_value=False)

    hass.data[MYSA_DOMAIN] = {"test_entry": {"api": mock_api}}
    mock_entry = MagicMock(entry_id="test_entry")

    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_killer_ping(call, hass)
        assert excinfo.value.translation_key == "killer_ping_failed"


@pytest.mark.asyncio
async def test_killer_ping_generic_exception(hass: HomeAssistant):
    """Test killer ping handles generic exceptions."""
    with patch(
        "homeassistant.helpers.device_registry.async_get",
        side_effect=ValueError("Boom"),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_killer_ping(call, hass)
        assert excinfo.value.translation_key == "killer_ping_error"


@pytest.mark.asyncio
async def test_upgrade_lite_device_invalid_data(hass: HomeAssistant):
    """Test upgrade when Mysa data is invalid (not a dict)."""
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(MYSA_DOMAIN, "device_123")}
    mock_device_entry.config_entries = {"test_entry"}
    mock_device_registry.async_get.return_value = mock_device_entry

    # Invalid data (not a dict)
    hass.data[MYSA_DOMAIN] = {"test_entry": "invalid_string"}
    mock_entry = MagicMock(entry_id="test_entry")

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get",
            return_value=mock_device_registry,
        ),
        patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry),
    ):
        call = MagicMock()
        call.data = {"device_id": "ha_device_id"}

        with pytest.raises(HomeAssistantError) as excinfo:
            await async_service_upgrade_lite(call, hass)
        assert excinfo.value.translation_key == "mysa_data_invalid"
