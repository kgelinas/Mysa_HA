from custom_components.mysa.system_health import system_health_info
"""Tests for System Health."""

import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from custom_components.mysa.const import DOMAIN
from custom_components.mysa.system_health import async_register, system_health_info


class TestSystemHealth:
    """Test System Health."""

    def test_async_register(self, hass):
        """Test async_register registers the info callback."""
        mock_register = MagicMock()

        async_register(hass, mock_register)

        mock_register.async_register_info.assert_called_once_with(system_health_info)

    @pytest.mark.asyncio
    async def test_system_health_no_data(self, hass):
        """Test system health when no integration data exists."""
        hass.data = {}

        result = await system_health_info(hass)

        assert result["api_connected"] is False
        assert result["devices"] == 0
        assert result["mqtt_listener"] == "Not running"

    @pytest.mark.asyncio
    async def test_system_health_with_api(self, hass):
        """Test system health with connected API."""
        mock_api = MagicMock()
        mock_api.is_connected = True
        mock_api.devices = {"device1": {}, "device2": {}}
        mock_api.is_mqtt_running = True
        mock_api.mqtt_status = "Running"

        hass.data[DOMAIN] = {"test_entry": {"api": mock_api}}

        result = await system_health_info(hass)

        assert result["api_connected"] is True
        assert result["devices"] == 2
        assert result["mqtt_listener"] == "Running"

    @pytest.mark.asyncio
    async def test_system_health_mqtt_stopped(self, hass):
        """Test system health when MQTT listener is stopped."""
        mock_api = MagicMock()
        mock_api.is_connected = True
        mock_api.devices = {"device1": {}}
        mock_api.is_mqtt_running = False
        mock_api.mqtt_status = "Stopped"

        hass.data[DOMAIN] = {"test_entry": {"api": mock_api}}

        result = await system_health_info(hass)

        assert result["mqtt_listener"] == "Stopped"

    @pytest.mark.asyncio
    async def test_system_health_no_mqtt_task(self, hass):
        """Test system health when MQTT task is None via property."""
        mock_api = MagicMock()
        mock_api.is_connected = True
        mock_api.devices = {}
        mock_api.is_mqtt_running = False
        mock_api.mqtt_status = "Stopped"

        hass.data[DOMAIN] = {"test_entry": {"api": mock_api}}

        result = await system_health_info(hass)

        assert result["mqtt_listener"] == "Stopped"

    @pytest.mark.asyncio
    async def test_system_health_fallback_invalid_runtime_data(self, hass):
        """Test fallback when runtime_data exists but lacks api attribute."""
        hass.data[DOMAIN] = {}

        mock_entry = MagicMock()
        # runtime_data exists but is an empty object (no api attr)
        mock_entry.runtime_data = object()

        with patch(
            "custom_components.mysa.system_health.MysaApi", side_effect=ImportError
        ):
            # We patch config_entries.async_entries via hass object
            with patch.object(
                hass.config_entries, "async_entries", return_value=[mock_entry]
            ):
                result = await system_health_info(hass)

        assert result["api_connected"] is False

    @pytest.mark.asyncio
    async def test_system_health_fallback_success(self, hass):
        """Test fallback when runtime_data works correctly."""
        hass.data[DOMAIN] = {}

        mock_api = MagicMock()
        mock_api.is_connected = True
        mock_api.devices = {"device1": {}}
        mock_api.is_mqtt_running = True
        mock_api.mqtt_status = "Running"

        mock_entry = MagicMock()
        mock_entry.runtime_data.api = mock_api

        with patch(
            "custom_components.mysa.system_health.MysaApi", side_effect=ImportError
        ):
            # We patch config_entries.async_entries via hass object
            with patch.object(
                hass.config_entries, "async_entries", return_value=[mock_entry]
            ):
                result = await system_health_info(hass)

        assert result["api_connected"] is True
        assert result["devices"] == 1


class TestSystemHealthConsolidated:
    """Consolidated tests for system_health.py coverage."""

    @pytest.mark.asyncio
    async def test_system_health_consolidated(self, hass):
        """Cover system_health.py edge cases."""
        from custom_components.mysa.system_health import async_register, system_health_info

        # 1. async_register
        mock_reg = MagicMock()
        async_register(hass, mock_reg)
        mock_reg.async_register_info.assert_called_with(system_health_info)

        # 2. system_health_info - No API (Empty hass.data and entries)
        hass.data[DOMAIN] = {}
        with patch.object(hass.config_entries, "async_entries", return_value=[]):
            info = await system_health_info(hass)
            assert info["api_connected"] is False

        # 3. system_health_info - From hass.data
        api_mock = MagicMock()
        type(api_mock).is_connected = PropertyMock(return_value=True)
        api_mock.devices = {"d1": {}}
        type(api_mock).is_mqtt_running = PropertyMock(return_value=True)
        type(api_mock).mqtt_status = PropertyMock(return_value="Running")
        hass.data[DOMAIN] = {"entry1": {"api": api_mock}}
        info = await system_health_info(hass)
        assert info["api_connected"] is True
        assert info["devices"] == 1
        assert info["mqtt_listener"] == "Running"

        # 4. system_health_info - From runtime_data
        hass.data[DOMAIN] = {}
        mock_entry = MagicMock()
        # Ensure it's not a PropertyMock that raises AttributeError for this step
        mock_entry.runtime_data = MagicMock()
        mock_entry.runtime_data.api = api_mock
        with patch.object(hass.config_entries, "async_entries", return_value=[mock_entry]):
            info = await system_health_info(hass)
            assert info["api_connected"] is True

        # 5. system_health_info - AttributeError fallback
        mock_entry.runtime_data = MagicMock()
        # Mocking an attribute that doesn't exist to trigger AttributeError on api access
        del mock_entry.runtime_data.api
        with patch.object(hass.config_entries, "async_entries", return_value=[mock_entry]):
             info = await system_health_info(hass)
             assert info["api_connected"] is False

@pytest.mark.asyncio
async def test_system_health_info_enhanced(hass):
    """Test system_health_info uses the new mqtt_status."""
    from unittest.mock import PropertyMock, MagicMock
    from custom_components.mysa.mysa_api import MysaApi
    mock_api = MagicMock(spec=MysaApi)
    type(mock_api).mqtt_status = PropertyMock(return_value="Stale")
    type(mock_api).is_connected = PropertyMock(return_value=True)
    mock_api.devices = {"d1": {}}

    hass.data["mysa"] = {"entry_id": {"api": mock_api}}

    info = await system_health_info(hass)
    assert info["mqtt_listener"] == "Stale"
