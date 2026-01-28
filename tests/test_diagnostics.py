"""Tests for Mysa diagnostics."""

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.mysa.const import DOMAIN
from custom_components.mysa.diagnostics import async_get_config_entry_diagnostics
from tests.conftest import MockConfigEntry


@pytest.mark.asyncio
async def test_diagnostics(hass: HomeAssistant):
    """Test diagnostics."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "test-user@example.com",
            CONF_PASSWORD: "secret-password",
        },
        entry_id="test_entry_id",
    )
    entry.add_to_hass(hass)

    # Mock API
    api = MagicMock()
    api.devices = {"device1": {"Name": "Test Device"}}
    api.states = {"device1": {"temp": 21}}
    api.homes = [{"Name": "Test Home"}]
    api.upgraded_lite_devices = ["device2"]
    api.estimated_max_current = 10

    hass.data[DOMAIN] = {
        entry.entry_id: {
            "api": api,
        }
    }

    # Mock runtime_data
    mock_data = MagicMock()
    mock_data.api = api
    entry.runtime_data = mock_data

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["devices"] == {"device1": {"Name": "Test Device"}}
    assert result["states"] == {"device1": {"temp": 21}}
    assert result["homes"] == [{"Name": "Test Home"}]
    assert result["upgraded_lite_devices"] == ["device2"]
    assert result["estimated_max_current"] == 10

    # Check redaction
    entry_dict = result["entry"]
    assert entry_dict["data"][CONF_USERNAME] == "**REDACTED**"
    assert entry_dict["data"][CONF_PASSWORD] == "**REDACTED**"
