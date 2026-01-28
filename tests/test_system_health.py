"""Tests for System Health."""

from unittest.mock import MagicMock, patch

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
