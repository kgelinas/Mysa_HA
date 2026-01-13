"""Tests for System Health."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from custom_components.mysa.const import DOMAIN
from custom_components.mysa.system_health import system_health_info, async_register


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
        mock_api._session = MagicMock()  # Session exists = connected
        mock_api.devices = {"device1": {}, "device2": {}}
        mock_api._mqtt_task = MagicMock()
        mock_api._mqtt_task.done.return_value = False  # Task running

        hass.data[DOMAIN] = {"test_entry": {"api": mock_api}}

        result = await system_health_info(hass)

        assert result["api_connected"] is True
        assert result["devices"] == 2
        assert result["mqtt_listener"] == "Running"

    @pytest.mark.asyncio
    async def test_system_health_mqtt_stopped(self, hass):
        """Test system health when MQTT listener is stopped."""
        mock_api = MagicMock()
        mock_api._session = MagicMock()
        mock_api.devices = {"device1": {}}
        mock_api._mqtt_task = MagicMock()
        mock_api._mqtt_task.done.return_value = True  # Task completed/stopped

        hass.data[DOMAIN] = {"test_entry": {"api": mock_api}}

        result = await system_health_info(hass)

        assert result["mqtt_listener"] == "Stopped"

    @pytest.mark.asyncio
    async def test_system_health_no_mqtt_task(self, hass):
        """Test system health when MQTT task is None."""
        mock_api = MagicMock()
        mock_api._session = MagicMock()
        mock_api.devices = {}
        mock_api._mqtt_task = None

        hass.data[DOMAIN] = {"test_entry": {"api": mock_api}}

        result = await system_health_info(hass)

        assert result["mqtt_listener"] == "Stopped"
