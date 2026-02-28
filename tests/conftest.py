"""Pytest configuration for Mysa integration tests.

Shared fixtures and configuration for all tests.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# Mock pycognito globally ONLY if not in VCR record mode
MYSA_RECORD = os.environ.get("MYSA_RECORD", "0") == "1"
if not MYSA_RECORD:
    try:
        # Justification: Importing just to check if the module is available to conditionally mock it.
        import pycognito  # pylint: disable=unused-import
    except ImportError:
        sys.modules["pycognito"] = MagicMock()

import pytest
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Test directory paths (for reference, not for sys.path manipulation)
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)


# ===========================================================================
# Auto-use fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test directory."""
    yield


@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with (
        patch("homeassistant.components.persistent_notification.async_create"),
        patch("homeassistant.components.persistent_notification.async_dismiss"),
        patch("homeassistant.setup.async_process_deps_reqs", return_value=None),
        patch(
            "homeassistant.requirements.async_process_requirements", return_value=None
        ),
    ):
        yield


# ===========================================================================
# Config Entry fixtures
# ===========================================================================


@pytest.fixture
def mock_config_entry(hass):
    """Create a standard mock config entry."""
    from custom_components.mysa.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "username": "test@example.com",
            "password": "password123",
            "device_id": "test_device_id",
        },
        entry_id="test_entry_id",
        title="Mysa Integration",
    )
    entry.runtime_data = None
    entry.add_to_hass(hass)
    return entry


# ===========================================================================
# API fixtures
# ===========================================================================


@pytest.fixture
def mock_setup_entry():
    """Mock setting up a config entry."""
    with patch(
        "custom_components.mysa.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_mysa_api():
    """Mock MysaApi for config flow testing."""
    with patch("custom_components.mysa.config_flow.MysaApi") as mock_api_cls:
        mock_api = mock_api_cls.return_value
        mock_api.authenticate = AsyncMock(return_value=True)
        mock_api.get_devices = AsyncMock(return_value={})
        mock_api.start_mqtt_listener = AsyncMock()
        mock_api.stop_mqtt_listener = AsyncMock()
        mock_api.devices = {}
        yield mock_api


@pytest.fixture
def mock_api():
    """Create a fully mocked MysaApi instance."""
    from custom_components.mysa.mysa_api import MysaApi

    api = MagicMock(spec=MysaApi)
    api.authenticate = AsyncMock(return_value=True)
    api.get_devices = AsyncMock(
        return_value={
            "device1": {
                "id": "device1",
                "Name": "Living Room",
                "type": 4,
            }
        }
    )
    api.get_state = AsyncMock(
        return_value={
            "device1": {
                "temperature": 20.0,
                "setpoint": 21.0,
                "humidity": 45,
            }
        }
    )
    api.set_target_temperature = AsyncMock()
    api.set_hvac_mode = AsyncMock()
    api.start_mqtt_listener = AsyncMock()
    api.stop_mqtt_listener = AsyncMock()
    api.devices = api.get_devices.return_value
    api.device_caps = {}
    api.simulated_energy = False
    api.upgraded_lite_devices = []
    api._latest_timestamp = {}
    api._clock_skew = {}
    api._last_command_time = {}
    api._last_mqtt_poll_time = {}
    api.realtime = MagicMock()
    type(api).is_mqtt_running = PropertyMock(return_value=True)

    # Mock client and its async methods to prevent RuntimeWarnings
    api.client = MagicMock()
    api.client.fetch_homes = AsyncMock()
    api.client.get_state = AsyncMock(return_value={})
    api.client.async_request = AsyncMock()
    api.client.fetch_live_metrics = AsyncMock()
    api.client.fetch_device_settings = AsyncMock()
    api.client.fetch_smart_schedules = AsyncMock()

    return api


# ===========================================================================
# Coordinator fixtures
# ===========================================================================


@pytest.fixture
def mock_coordinator(hass, mock_config_entry):
    """Create a mock coordinator."""
    # DataUpdateCoordinator is imported at top level

    async def async_update():
        return {
            "device1": {
                "temperature": 20.0,
                "setpoint": 21.0,
            }
        }

    coordinator = DataUpdateCoordinator(
        hass,
        MagicMock(),
        name="mysa_test",
        update_method=async_update,
        config_entry=mock_config_entry,
    )
    return coordinator


# ===========================================================================
# VCR / E2E fixtures
# ===========================================================================


@pytest.fixture
def vcr_cassette_dir():
    """Return the cassette directory for VCR tests."""
    return os.path.join(TEST_DIR, "cassettes")


@pytest.fixture
async def mock_mqtt_broker():
    """Create a mock MQTT broker for testing."""
    from .mqtt_broker import MockMqttBroker

    broker = MockMqttBroker()
    await broker.start()
    yield broker
    await broker.stop()
